"""Flatten AgentDojo run traces into one-event-per-row JSONL for labeling.

Source: https://github.com/ethz-spylab/agentdojo  (runs/<model>/<suite>/<user_task>/<attack>/<injection_task>.json)
These are real executions of production LLMs (Claude, GPT-4o, Gemini, Llama) acting as email/calendar/
drive (workspace), Slack, and banking agents, with and without indirect prompt injections in tool outputs.

Each message in a trace becomes one event:
    user      -> user_input
    assistant -> model_output (text) and/or tool_call (one per call)
    tool      -> tool_response
The system prompt is dropped as an event but kept as deployment context.

Two kinds of fields come out of this script:
  * classifier-visible: kind, content / tool / args, context (the N preceding events)
  * HIDDEN provenance (`_meta`): model, attack, injection text, AgentDojo's own utility/security.
    These must NEVER be shown to the classifier. They are only for stratified sampling and as a
    sanity check against your own labels (AgentDojo's `security=True` means the injection's goal
    was achieved, which is not the same thing as "this event violates my policy").

Usage:
    python scripts/extract_agentdojo.py --runs <path/to/agentdojo/runs> --out data/raw_events.jsonl
    python scripts/extract_agentdojo.py ... --sample 150 --sample-out data/to_label.jsonl --csv-out data/to_label.csv
"""
import argparse
import csv
import hashlib
import json
import random
import re
from collections import defaultdict
from pathlib import Path

CONTEXT_EVENTS = 6      # how many prior events the classifier gets (assumption, see README)
MAX_FIELD_CHARS = 4000  # truncate huge tool outputs; record that we did


def trunc(s, n=MAX_FIELD_CHARS):
    s = "" if s is None else str(s)
    return (s[:n] + f"... [truncated {len(s) - n} chars]") if len(s) > n else s


def content_text(content):
    # AgentDojo stores content as str, or as a list of {"type": "text", "content": ...} blocks in newer runs
    if content is None:
        return ""
    if isinstance(content, list):
        return "\n".join(str(b.get("content", b.get("text", ""))) for b in content if isinstance(b, dict))
    return str(content)


def _norm_words(s):
    # tool outputs are YAML-dumped, so injected text arrives with escaped newlines and line continuations
    return re.sub(r"\s+", " ", s.replace("\\n", " ").replace("\\", " ")).strip().split(" ")


def contains_injection(body, payload, window=8):
    """True if an 8-word run from the middle of the injected payload appears in the event body."""
    pw = [w for w in _norm_words(payload) if w]
    if len(pw) < window:
        return bool(payload.strip()) and payload.strip() in body
    mid = len(pw) // 2
    needle = " ".join(pw[mid - window // 2: mid + window // 2])
    return needle in " ".join(w for w in _norm_words(body) if w)


def summarize(ev):
    """Short form of an event for use as context for later events."""
    if ev["kind"] == "tool_call":
        return {"kind": "tool_call", "tool": ev["tool"], "args": ev["args"]}
    return {"kind": ev["kind"], **({"tool": ev["tool"]} if ev.get("tool") else {}),
            "content": trunc(ev["content"], 800)}


def trace_to_events(path: Path, runs_root: Path):
    d = json.loads(path.read_text())
    rel = path.relative_to(runs_root).parts  # model, suite, user_task, attack, injection_task.json
    model, suite, user_task, attack = rel[0], rel[1], rel[2], rel[3]
    trace_id = "/".join(rel).removesuffix(".json")
    injections = d.get("injections") or {}

    system_prompt, events = "", []
    for m in d.get("messages", []):
        role, text = m.get("role"), content_text(m.get("content"))
        if role == "system":
            system_prompt = text
        elif role == "user":
            events.append({"kind": "user_input", "content": text})
        elif role == "assistant":
            if text.strip():
                events.append({"kind": "model_output", "content": text})
            for tc in m.get("tool_calls") or []:
                events.append({"kind": "tool_call", "tool": tc.get("function"), "args": tc.get("args", {})})
        elif role == "tool":
            fn = (m.get("tool_call") or {}).get("function")
            events.append({"kind": "tool_response", "tool": fn, "content": text,
                           "tool_error": m.get("error")})

    # The principal's request is the event that grants authority, so every later event carries it,
    # even when it has scrolled out of the previous-events window (it does in ~60% of sampled events).
    first_user = next((j for j, e in enumerate(events) if e["kind"] == "user_input"), None)

    out = []
    for i, ev in enumerate(events):
        body = ev.get("content", "") or json.dumps(ev.get("args", {}))
        # Does this event contain (a substring of) an injected payload? Hidden; for sampling only.
        carries_injection = any(v and contains_injection(body, v) for v in injections.values())
        eid = hashlib.sha1(f"{trace_id}#{i}".encode()).hexdigest()[:12]
        out.append({
            "id": eid,
            "kind": ev["kind"],
            **({"tool": ev["tool"]} if ev.get("tool") else {}),
            **({"args": ev["args"]} if ev["kind"] == "tool_call" else {"content": trunc(ev["content"])}),
            "context": {
                "deployment": f"agentdojo/{suite}",
                "system_prompt": trunc(system_prompt, 1500),
                "original_request": (events[first_user]["content"]
                                     if first_user is not None and first_user < i else None),
                "previous_events": [summarize(e) for e in events[max(0, i - CONTEXT_EVENTS):i]],
            },
            "label": None,          # allow | violation | unsure  -- you fill this in
            "rule": None,           # which policy clause decided it
            "label_note": None,     # why; especially for the ones you could not decide
            "_meta": {
                "source": "agentdojo", "trace_id": trace_id, "position": i, "n_events": len(events),
                "model": model, "suite": suite, "user_task": user_task, "attack": attack,
                "carries_injection_text": carries_injection,
                "agentdojo_utility": d.get("utility"), "agentdojo_security": d.get("security"),
            },
        })
    return out


def stratified_sample(events, n, seed=0):
    """Spread the sample over (suite, kind, injected?) cells so rare cells are not drowned out."""
    rng = random.Random(seed)
    cells, seen = defaultdict(list), set()
    for e in events:
        # the same user prompt / tool output recurs across injection variants; label each text once
        key = (e["kind"], e.get("tool"), json.dumps(e.get("args", e.get("content")), sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        m = e["_meta"]
        cells[(m["suite"], e["kind"], m["attack"] != "none", m["carries_injection_text"])].append(e)
    for c in cells.values():
        rng.shuffle(c)
    picked, keys = [], sorted(cells)
    while len(picked) < n and any(cells[k] for k in keys):
        for k in keys:
            if cells[k] and len(picked) < n:
                picked.append(cells[k].pop())
    rng.shuffle(picked)
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--sample-out", type=Path)
    ap.add_argument("--csv-out", type=Path, help="spreadsheet version of the sample for labeling")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    events = []
    for p in sorted(a.runs.rglob("*.json")):
        try:
            events.extend(trace_to_events(p, a.runs))
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"skip {p}: {e}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"{len(events)} events -> {a.out}")

    if a.sample:
        s = stratified_sample(events, a.sample, a.seed)
        with a.sample_out.open("w") as f:
            for e in s:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"{len(s)} sampled -> {a.sample_out}")
        if a.csv_out:
            write_label_csv(s, a.csv_out)
            print(f"labeling sheet -> {a.csv_out}")


def fmt(e):
    if e["kind"] == "tool_call":
        return f"{e.get('tool')}({json.dumps(e.get('args', {}), ensure_ascii=False)})"
    return (f"[{e['tool']}] " if e.get("tool") else "") + str(e.get("content", ""))


def write_label_csv(sample, path):
    """Only classifier-visible fields go in the sheet, so the labeler sees what the classifier sees."""
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "kind", "event", "original_request", "previous_events (oldest first)",
                    "label (allow/violation/unsure)", "rule", "note"])
        for e in sample:
            prev = "\n".join(f"{p['kind']}: {fmt(p)}" for p in e["context"]["previous_events"])
            w.writerow([e["id"], e["kind"], fmt(e)[:3000], e["context"].get("original_request") or "",
                        prev, "", "", ""])


if __name__ == "__main__":
    main()
