import { useEffect, useState } from "react";
import "./App.css";

const KINDS = ["user_input", "model_output", "tool_call", "tool_response"];

// Dev-split cases used in the write-up and video. See DEMO_CASEBOOK.md and CORNER_CASES.md.
const DEMO_CASES = [
  ["bd14d7cb07a1", "Resolving a channel from tool data (should allow)"],
  ["c3069d488663", "Agent adopts a webpage's injected instruction (violation)"],
  ["546fd18131d6", "Agent refuses an injection: known false block"],
  ["7b92efe0b615", "Corner case 1: injected channel name, user-named target"],
  ["f254cfc20a9b", "Corner case 1: injected channel name, agent-chosen target"],
  ["aabec1d3e16d", "Corner case 2: IBANs in a banking tool response"],
  ["807351d1700f", "Lookalike domain luesparrowtech.com"],
];

export default function App() {
  const [text, setText] = useState('{\n  "kind": "user_input",\n  "content": "Summarize my unread emails."\n}');
  const [samples, setSamples] = useState({});
  const [reference, setReference] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/samples").then((r) => (r.ok ? r.json() : [])).then((list) => {
      setSamples(Object.fromEntries(list.map((s) => [s.id, s])));
    }).catch(() => setSamples({}));
  }, []);

  function loadSample(id) {
    setResult(null); setError("");
    const sample = samples[id];
    if (!sample) { setReference(null); return; }
    const { id: _id, reference_label, reference_rule, ...event } = sample;
    setReference({ id, label: reference_label, rule: reference_rule });
    setText(JSON.stringify(event, null, 2));
  }

  async function classify(event) {
    event.preventDefault();
    setError(""); setResult(null); setBusy(true);
    try {
      const current = JSON.parse(text);
      if (!current || Array.isArray(current) || !KINDS.includes(current.kind)) {
        throw new Error("Include a valid event kind: " + KINDS.join(", ") + ".");
      }
      const response = await fetch("/api/classify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event: current }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Classification failed. Please check the event and try again.");
      if (!["allow", "violation", "escalate"].includes(body.verdict)) throw new Error("The classifier returned an invalid response.");
      setResult(body);
    } catch (err) {
      setError(err instanceof SyntaxError ? "Enter valid JSON for a single event." : err.message);
    } finally {
      setBusy(false);
    }
  }

  const available = DEMO_CASES.filter(([id]) => samples[id]);

  return (
    <main>
      <header>
        <p className="eyebrow">Policy Classifier</p>
        <h1>Event classifier</h1>
        <p>Check one agent event against the organization's policy (policy v1.1).</p>
      </header>
      <form onSubmit={classify}>
        {available.length > 0 && <>
          <label htmlFor="sample">Demo case (dev split)</label>
          <select id="sample" defaultValue="" disabled={busy} onChange={(e) => loadSample(e.target.value)}>
            <option value="">Custom event…</option>
            {available.map(([id, title]) => <option key={id} value={id}>{id}: {title}</option>)}
          </select>
        </>}
        <label htmlFor="event">Current event</label>
        <p id="event-help" className="hint">Enter one JSON object. Use kind: user_input, model_output, tool_call, or tool_response. Optional context: original_request, system_prompt, previous_events.</p>
        <textarea id="event" aria-describedby="event-help" value={text}
          onChange={(e) => { setText(e.target.value); setResult(null); setError(""); setReference(null); }}
          spellCheck={false} disabled={busy} required />
        <button type="submit" disabled={busy}>{busy ? "Classifying..." : "Classify Event"}</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      <div aria-live="polite" aria-busy={busy}>
        {result && <section className={`result ${result.verdict}`} aria-label="Classification result">
          <p className="eyebrow">Verdict</p>
          <h2>{result.verdict}</h2>
          <dl>
            {reference && <><dt>Reference label ({reference.id})</dt>
              <dd className={reference.label === result.verdict ? "match" : "mismatch"}>
                {reference.label}{reference.rule ? ` / ${reference.rule}` : ""}{reference.label === result.verdict ? " (agrees)" : " (disagrees)"}
              </dd></>}
            <dt>Applicable rule</dt>
            <dd>{result.rules?.length ? result.rules.join(", ") : result.primary_rule || "None identified"}</dd>
            <dt>Explanation</dt>
            <dd>{result.rationale}</dd>
            {result.evidence && <><dt>Evidence</dt><dd>{result.evidence}</dd></>}
            {result.missing_fact && <><dt>Missing information</dt><dd>{result.missing_fact}</dd></>}
          </dl>
        </section>}
      </div>
    </main>
  );
}
