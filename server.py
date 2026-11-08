"""API for the React demo. Serves the built page from web/dist."""
import logging
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from classifier.core import ClassifierError, classify, load_policy, inference_config, VERDICTS
from eval.run_eval import load_dataset, event_for_case

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Policy Event Classifier")
logger = logging.getLogger(__name__)


class Req(BaseModel):
    event: dict
    model: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"^\S+$")
    provider: Literal["groq", "gemini", "ollama"] | None = None
    context: int = Field(default=6, ge=0, le=20)


@app.get("/api/samples")
def samples():
    # Dev cases only (test stays held out). The reference label is shown beside the verdict in the demo.
    return [{"id": case["id"], "reference_label": case["label"], "reference_rule": case["rule_id"],
             **event_for_case(case, "all")} for case in load_dataset()]


@app.get("/api/policy")
def policy():
    settings = inference_config()
    text = load_policy()
    return {"policy": text, "policy_file": os.getenv("POLICY_FILE", "policy_v1_1.md"), "default_model": settings["model"],
            "default_provider": settings["provider"], "default_context": 6,
            "inference_parameters": settings["parameters"]}


@app.get("/api/runtime")
def runtime():
    """Read-only backend configuration; no inference or model discovery."""
    return policy()


@app.post("/api/classify")
def do_classify(req: Req):
    if req.event.get("kind") not in ("user_input", "model_output", "tool_call", "tool_response"):
        raise HTTPException(400, "event.kind must be user_input, model_output, tool_call or tool_response")
    try:
        settings = inference_config(req.provider, req.model)
        text = load_policy()
        result = classify(req.event, model=settings["model"], n_context=req.context, provider=settings["provider"], policy_text=text)
        if result.get("verdict") not in VERDICTS:
            raise ClassifierError("The model returned invalid classification JSON. Try again or inspect the model/output settings.", code="parse_error")
        result.update(context=req.context)
        return result
    except ClassifierError as exc:
        raise HTTPException(exc.status_code, str(exc), headers={"X-Classifier-Error": exc.code}) from None
    except ValueError:
        raise HTTPException(400, "Invalid event structure or classification options.") from None
    except Exception:
        logger.error("Unexpected classification failure")
        raise HTTPException(500, "Classification failed unexpectedly. Check backend configuration and server logs.") from None


if (ROOT / "web/dist").exists():
    app.mount("/", StaticFiles(directory=ROOT / "web/dist", html=True), name="web")
