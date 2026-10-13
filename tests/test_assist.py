from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

anthropic = pytest.importorskip("anthropic", reason="install mobius[assist] to test --assist")
import httpx2  # noqa: E402  (installed with anthropic)

from mobius import assist  # noqa: E402
from mobius import foundry  # noqa: E402
from mobius import graph as mobius  # noqa: E402

OBJECTIVE = "Build an agent that wires money to vendors every Friday"


class FakeClient:
    def __init__(self, payload=None, *, stop_reason="end_turn", error=None):
        self.payload = payload if payload is not None else {"capabilities": [], "draft_answers": [], "follow_up_questions": []}
        self.stop_reason = stop_reason
        self.error = error
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        response = SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
            model=kwargs["model"],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
        )
        response._request_id = "req_test"
        return response


def isolate_runtime(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app / "history")
    monkeypatch.setattr(mobius, "DEFAULT_AGENT_SPEC_DIR", app / "agent_specs")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")


def test_request_uses_structured_output_fallbacks_and_the_default_model(monkeypatch):
    monkeypatch.delenv("MOBIUS_ASSIST_MODEL", raising=False)
    client = FakeClient()
    result = assist.request_suggestions(OBJECTIVE, "internal", {}, client=client)
    assert result["status"] == "ok"
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert OBJECTIVE in call["messages"][0]["content"]
    assert result["request_id"] == "req_test"
    assert result["usage"] == {"input_tokens": 1200, "output_tokens": 300}


def test_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MOBIUS_ASSIST_MODEL", "claude-sonnet-5-5")
    client = FakeClient()
    assist.request_suggestions(OBJECTIVE, None, {}, client=client)
    assert client.calls[0]["model"] == "claude-sonnet-5-5"


def test_secret_looking_input_is_never_sent():
    client = FakeClient()
    with pytest.raises(ValueError, match="secret-looking"):
        assist.request_suggestions("Build an agent; api_key=sk-abcdefghijklmnopqrstuvwxyz1234", None, {}, client=client)
    assert client.calls == []


def test_suggestions_are_cleaned_to_open_questions_and_known_actions():
    payload = {
        "capabilities": [
            {"action": "purchase_payment_trade", "evidence_quote": "wires money to vendors"},
            {"action": "teleport", "evidence_quote": "wires"},
        ],
        "draft_answers": [
            {"dimension": "trigger", "value": "Manual command."},
            {"dimension": "inputs", "value": "vendor list; invoice folder"},
            {"dimension": "goal", "value": "Pay vendors."},  # inferred from the sentence, not open
            {"dimension": "memory", "value": "password=hunter2hunter2hunter2"},  # secret-looking
        ],
        "follow_up_questions": [f"Question {n}?" for n in range(9)],
    }
    result = assist.request_suggestions(OBJECTIVE, None, {}, client=FakeClient(payload))
    assert result["capabilities"] == [{"action": "purchase_payment_trade", "evidence": "wires money to vendors"}]
    assert result["draft_answers"] == {"trigger": "Manual command.", "inputs": ["vendor list", "invoice folder"]}
    assert len(result["follow_up_questions"]) == assist.MAX_FOLLOW_UPS


@pytest.mark.parametrize(("stop_reason", "status"), [("refusal", "refused"), ("max_tokens", "truncated")])
def test_refusals_and_cutoffs_return_no_suggestions(stop_reason, status):
    payload = {"capabilities": [], "draft_answers": [{"dimension": "trigger", "value": "x"}], "follow_up_questions": []}
    result = assist.request_suggestions(OBJECTIVE, None, {}, client=FakeClient(payload, stop_reason=stop_reason))
    assert result["status"] == status
    assert result["draft_answers"] == {}


def _request():
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(("error", "status", "message"), [
    (anthropic.APIConnectionError(request=_request()), "failed", "could not reach"),
    (anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=_request()), body=None), "failed", "rate limited"),
    (anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=_request()), body=None), "failed", "credentials"),
    (anthropic.InternalServerError("boom", response=httpx2.Response(500, request=_request()), body=None), "failed", "500"),
    (TypeError("Could not resolve authentication method."), "unavailable", "ant auth login"),
])
def test_api_problems_never_raise(error, status, message):
    result = assist.request_suggestions(OBJECTIVE, None, {}, client=FakeClient(error=error))
    assert result["status"] == status
    assert message in result["error"]


def test_unrelated_type_errors_are_not_swallowed():
    with pytest.raises(TypeError, match="something else"):
        assist.request_suggestions(OBJECTIVE, None, {}, client=FakeClient(error=TypeError("something else")))


def test_missing_sdk_is_reported_not_raised(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    result = assist.request_suggestions(OBJECTIVE, None, {})
    assert result["status"] == "unavailable"
    assert "mobius[assist]" in result["error"]
    assert assist.made_network_call(result) is False


def test_model_findings_only_count_with_a_verbatim_quote():
    findings = [
        {"action": "shell_commands", "evidence": "runs scripts on the server"},  # not in the text
        {"action": "external_send", "evidence": "posts  the summary"},  # whitespace differs only
    ]
    assessment = foundry.assess_risk_sources(
        "Build an agent that posts the summary to the team channel", None, {}, model_findings=findings,
    )
    model_items = [item for item in assessment["actions"] if item["source_field"] == "model"]
    assert [item["canonical_action"] for item in model_items] == ["external_send"]
    assert "shell_commands" not in assessment["effective_authority"]


def test_the_model_cannot_lower_risk():
    # The model says nothing risky; the wording still makes this high risk.
    plain = foundry.assess_risk("Build an agent that wires money to vendors")
    with_model = foundry.assess_risk_sources("Build an agent that wires money to vendors", None, {}, model_findings=[])
    assert plain["level"] == with_model["level"] == "high"


def test_model_findings_add_risk_the_patterns_miss():
    objective = "Build an agent that settles vendor balances at month end"
    assert foundry.assess_risk(objective)["level"] == "low"
    raised = foundry.assess_risk_sources(
        objective, None, {}, model_findings=[{"action": "purchase_payment_trade", "evidence": "settles vendor balances"}],
    )
    assert raised["level"] == "high"
    assert raised["effective_authority"]["purchase_payment_trade"]["authority"] == "requested"


def test_assisted_run_records_suggestions_without_counting_them_as_answers(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    payload = {
        "capabilities": [{"action": "purchase_payment_trade", "evidence_quote": "wires money to vendors"}],
        "draft_answers": [{"dimension": "trigger", "value": "Manual command."}],
        "follow_up_questions": ["Which vendors are in scope?"],
    }
    result = assist.request_suggestions(OBJECTIVE, "internal", {}, client=FakeClient(payload))
    state = mobius.run_graph(OBJECTIVE, "internal", run_id="assisted", assist=result)

    trigger = state["foundry_intake"]["dimensions"]["trigger"]
    assert trigger["status"] == "suggested"
    assert trigger["suggested_value"] == "Manual command."
    assert "trigger" in state["foundry_intake"]["completeness"]["missing"]
    assert state["decision"] == "needs_interview"
    assert state["side_effects_performed"] == ["network: Anthropic API (--assist)"]

    suggested = json.loads(Path(state["suggested_answers_path"]).read_text())
    assert suggested["trigger"] == "Manual command."
    assert suggested["capabilities"] == ["purchase_payment_trade"]
    foundry.validate_answers(suggested)  # can be passed straight back with --answers-json

    brief = Path(state["brief_path"]).read_text()
    assert "## Suggested by model" in brief
    assert "Which vendors are in scope?" in brief
    assert state["suggested_answers_path"] in state["recommended_next_action"]

    spec = json.loads(Path(state["json_spec_path"]).read_text())
    assert spec["assist"]["status"] == "ok"
    history = json.loads(Path(state["run_history_path"]).read_text().splitlines()[-1])
    assert history["assist"] == {"status": "ok", "model": "claude-opus-5-5", "request_id": "req_test",
                                 "usage": {"input_tokens": 1200, "output_tokens": 300}}


def test_failed_assist_run_still_completes_and_says_so(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    result = assist.request_suggestions(OBJECTIVE, "internal", {}, client=FakeClient(error=anthropic.APIConnectionError(request=_request())))
    state = mobius.run_graph(OBJECTIVE, "internal", run_id="assist_failed", assist=result)
    assert state["decision"] == "needs_interview"
    assert not state.get("suggested_answers_path")
    assert "--assist` failed" in Path(state["brief_path"]).read_text()


def test_cli_assist_requires_an_agent_idea(monkeypatch, capsys):
    from mobius import cli

    monkeypatch.setattr("sys.argv", ["mobius", "Prepare a bounded local-only smoke test", "--assist"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "--assist only applies to agent ideas" in capsys.readouterr().err
