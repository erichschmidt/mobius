"""Opt-in model assist for agent intake (``mobius --assist``).

One Claude call reads the person's sentence and answers so far, then:

- flags risky actions, each with a verbatim quote from the person's words;
- drafts answers for the intake questions that are still open;
- suggests a few follow-up questions.

Everything it returns is advisory. ``foundry.assess_risk_sources`` keeps a
flagged action only if its quote really appears in the person's text, and
flagged actions can only add risk. Drafted answers are shown as suggestions
and never count as answered until the person accepts them.

Möbius never asks for or stores an API key. The Anthropic SDK finds
credentials itself (``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile).
"""
from __future__ import annotations

from typing import Any
import json
import os

from . import foundry

DEFAULT_MODEL = "claude-opus-5-5"
MAX_FOLLOW_UPS = 5
MAX_FOLLOW_UP_CHARS = 300

SYSTEM_PROMPT = """You help someone write the rules for an AI agent before anyone builds it. \
You are part of Möbius, a command-line tool that turns a one-sentence agent idea into a reviewed \
spec. You never build or run anything; you only read what the person wrote and return JSON.

Return three things:

1. capabilities: every risky action the described agent would take, chosen from the given \
vocabulary. For each one, quote the exact words from the person's text that show it, copied \
character for character. Möbius discards any quote that is not a verbatim substring, so do not \
paraphrase, fix typos, or join separate phrases. Include actions the wording implies even when it \
avoids the obvious verb (for example, "wires money" is purchase_payment_trade and "shares it with \
the team" is external_send). Do not list actions the person says the agent must not do. If \
nothing risky is described, return an empty list.

2. draft_answers: a short proposed answer for each open intake question you can reasonably infer \
from the text. These are shown to the person as suggestions to accept or replace. Prefer the more \
cautious reading when the text is unclear (draft-only output, a person approves before anything \
leaves the machine). For list-style questions, separate items with "; ". Skip a question rather \
than invent specifics the text gives no basis for.

3. follow_up_questions: up to five short questions that would most reduce risk or ambiguity in \
this particular idea and that the standard intake questions do not already ask."""


def _schema() -> dict[str, Any]:
    open_dimensions = [name for name in foundry.FOUNDRY_DIMENSIONS if name != "capabilities"]
    return {
        "type": "object",
        "properties": {
            "capabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": list(foundry.CAPABILITIES)},
                        "evidence_quote": {"type": "string"},
                    },
                    "required": ["action", "evidence_quote"],
                    "additionalProperties": False,
                },
            },
            "draft_answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dimension": {"type": "string", "enum": open_dimensions},
                        "value": {"type": "string"},
                    },
                    "required": ["dimension", "value"],
                    "additionalProperties": False,
                },
            },
            "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["capabilities", "draft_answers", "follow_up_questions"],
        "additionalProperties": False,
    }


def _user_message(objective: str, context: str | None, answers: dict[str, Any], open_dimensions: list[str]) -> str:
    payload = {
        "agent_idea": objective,
        "context": context,
        "answers_so_far": answers,
        "open_questions": {name: foundry.interview_question_for_dimension(name) for name in open_dimensions if name != "capabilities"},
        "capability_vocabulary": foundry.CAPABILITY_LABELS,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _result(status: str, model: str, **fields: Any) -> dict[str, Any]:
    return {
        "status": status,
        "model": model,
        "capabilities": [],
        "draft_answers": {},
        "follow_up_questions": [],
        **fields,
    }


def request_suggestions(
    objective: str,
    context: str | None,
    answers: dict[str, Any] | None,
    *,
    client: Any = None,
) -> dict[str, Any]:
    """Ask Claude for risk findings, draft answers, and follow-up questions.

    Never raises for API or credential problems: the run continues without
    suggestions, and ``status`` says what happened.
    """
    model = os.environ.get("MOBIUS_ASSIST_MODEL") or DEFAULT_MODEL
    answers = foundry.validate_answers(answers)
    # Inputs were already validated by the CLI; check again so nothing secret-looking is ever sent.
    objective, context = foundry.validate_text_inputs(objective, context)
    foundry.reject_secret_values(objective, context, answers)
    open_dimensions = foundry.build_intake(objective, context, answers)["completeness"]["missing"]

    try:
        import anthropic
    except ImportError:
        return _result("unavailable", model, error="the anthropic package is not installed; run: pip install 'mobius[assist]'")

    try:
        client = client or anthropic.Anthropic()
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _schema()}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_message(objective, context, answers, open_dimensions)}],
        )
    except anthropic.AuthenticationError:
        return _result("failed", model, error="Anthropic rejected the credentials")
    except anthropic.PermissionDeniedError:
        return _result("failed", model, error="these credentials may not use this model")
    except anthropic.NotFoundError:
        return _result("failed", model, error=f"model {model!r} was not found")
    except anthropic.RateLimitError:
        return _result("failed", model, error="rate limited; try again shortly")
    except anthropic.APIStatusError as exc:
        return _result("failed", model, error=f"Anthropic API error {exc.status_code}")
    except anthropic.APIConnectionError:
        return _result("failed", model, error="could not reach the Anthropic API")
    except anthropic.AnthropicError as exc:
        return _result("failed", model, error=f"{type(exc).__name__}: {exc}")
    except TypeError as exc:
        # The SDK raises TypeError when it finds no credentials at all.
        if "authentication" not in str(exc).lower():
            raise
        return _result("unavailable", model, error="no Anthropic credentials found; set ANTHROPIC_API_KEY or run `ant auth login`")

    meta = {
        "model": getattr(response, "model", None) or model,
        "request_id": getattr(response, "_request_id", None),
        "usage": {
            "input_tokens": getattr(response.usage, "input_tokens", None),
            "output_tokens": getattr(response.usage, "output_tokens", None),
        },
    }
    if response.stop_reason == "refusal":
        return _result("refused", **meta, error="the model declined this request")
    if response.stop_reason == "max_tokens":
        return _result("truncated", **meta, error="the response was cut off before it finished")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _result("failed", **meta, error="the response was not valid JSON")
    return _result("ok", **meta, **_clean(payload, open_dimensions))


def _clean(payload: dict[str, Any], open_dimensions: list[str]) -> dict[str, Any]:
    """Keep only well-formed suggestions; ``foundry`` verifies the quotes later."""
    capabilities = [
        {"action": str(item.get("action")), "evidence": " ".join(str(item.get("evidence_quote") or "").split())}
        for item in payload.get("capabilities") or []
        if isinstance(item, dict) and item.get("action") in foundry.CAPABILITIES and item.get("evidence_quote")
    ]
    draft_answers: dict[str, Any] = {}
    for item in payload.get("draft_answers") or []:
        if not isinstance(item, dict):
            continue
        name, value = str(item.get("dimension")), str(item.get("value") or "").strip()
        if name not in open_dimensions or name == "capabilities" or not value or name in draft_answers:
            continue
        if name in foundry.LIST_DIMENSIONS:
            value = [part.strip() for part in value.replace("\n", ";").split(";") if part.strip()]
        try:
            draft_answers[name] = foundry.validate_answers({name: value})[name]
        except ValueError:
            continue
    follow_ups = [
        " ".join(str(question).split())[:MAX_FOLLOW_UP_CHARS]
        for question in payload.get("follow_up_questions") or []
        if isinstance(question, str) and question.strip()
    ][:MAX_FOLLOW_UPS]
    return {"capabilities": capabilities, "draft_answers": draft_answers, "follow_up_questions": follow_ups}


def made_network_call(assist: dict[str, Any] | None) -> bool:
    return bool(assist) and assist.get("status") in {"ok", "refused", "truncated", "failed"}


def suggested_answers(assist: dict[str, Any] | None, answers: dict[str, Any], missing: list[str]) -> dict[str, Any]:
    """Answers plus the model's drafts for still-open questions, ready to edit and pass back."""
    if not assist or assist.get("status") != "ok":
        return {}
    drafts = {name: value for name, value in (assist.get("draft_answers") or {}).items() if name in missing}
    flagged = sorted({item["action"] for item in assist.get("capabilities") or []})
    if "capabilities" in missing and flagged:
        drafts["capabilities"] = flagged
    if not drafts:
        return {}
    return {**answers, **drafts}
