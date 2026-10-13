from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobius import foundry
from mobius import graph as mobius


SAFE_ANSWERS = json.loads(Path("examples/weekly-digest-answers.json").read_text(encoding="utf-8"))


def isolate_runtime(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app / "history")
    monkeypatch.setattr(mobius, "DEFAULT_AGENT_SPEC_DIR", app / "agent_specs")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")


@pytest.mark.parametrize(("objective", "action", "authority"), [
    ("Build an agent that wires money to vendors", "purchase_payment_trade", "requested"),
    ("Build an agent that runs rm -rf on old build folders", "shell_commands", "requested"),
    ("Build an agent that runs rm -rf on old build folders", "destructive_deletion", "requested"),
    ("Build an agent that SSHes into prod and restarts nginx", "shell_commands", "requested"),
    ("Build an agent that summarizes the Slack channel and shares it with the team", "external_send", "requested"),
    ("Build an agent that drafts replies and sends them after I approve", "external_send", "approval_gated"),
])
def test_wording_the_old_patterns_missed_is_now_caught(objective, action, authority):
    assessment = foundry.assess_risk(objective)
    assert assessment["effective_authority"][action]["authority"] == authority
    assert assessment["level"] == "high"


def test_without_a_capabilities_answer_nothing_is_asked_about_wording():
    assessment = foundry.assess_risk("Build an agent that calls the weather API")
    assert assessment["declared_capabilities"] is None
    assert assessment["unconfirmed_signals"] == []


def test_undeclared_wording_becomes_a_question_not_a_verdict():
    assessment = foundry.assess_risk_sources(
        "Build an agent that calls the weather API and summarizes the forecast", None,
        {"capabilities": ["none"]},
    )
    assert [s["canonical_action"] for s in assessment["unconfirmed_signals"]] == ["outreach_contact"]
    question = foundry.interview_questions_for_signals(assessment["unconfirmed_signals"])[0]
    assert "calls the weather API" in question
    assert "dismissed_signals" in question


def test_dismissing_a_signal_lowers_risk_and_is_recorded():
    assessment = foundry.assess_risk_sources(
        "Build an agent that calls the weather API and summarizes the forecast", None,
        {"capabilities": ["none"], "dismissed_signals": ["outreach_contact"]},
    )
    assert assessment["level"] == "low"
    assert assessment["unconfirmed_signals"] == []
    assert [d["canonical_action"] for d in assessment["dismissed_signals"]] == ["outreach_contact"]
    assert "outreach_contact" not in assessment["effective_authority"]


def test_dismissals_only_count_once_capabilities_are_declared():
    assessment = foundry.assess_risk_sources(
        "Build an agent that wires money to vendors", None,
        {"dismissed_signals": ["purchase_payment_trade"]},
    )
    assert assessment["effective_authority"]["purchase_payment_trade"]["authority"] == "requested"
    assert assessment["dismissed_signals"] == []


def test_declared_capability_is_gated_even_when_the_wording_is_innocent():
    assessment = foundry.assess_risk_sources(
        "Build an agent that tidies my notes", None, {"capabilities": ["shell_commands"]},
    )
    assert assessment["effective_authority"]["shell_commands"]["authority"] == "requested"
    gates = foundry.build_approval_gates(assessment, {"capabilities": ["shell_commands"]})
    assert [gate["action"] for gate in gates] == ["shell_commands"]


def test_declared_sensitive_data_access_is_gated():
    answers = {"capabilities": ["sensitive_data_access"]}
    assessment = foundry.assess_risk_sources("Build an agent that tidies my notes", None, answers)
    assert assessment["level"] == "medium"
    assert [gate["action"] for gate in foundry.build_approval_gates(assessment, answers)] == ["sensitive_data_access"]


def test_declared_capability_that_the_boundary_forbids_is_a_conflict():
    assessment = foundry.assess_risk_sources(
        "Build an agent that tidies my notes", None,
        {"capabilities": ["external_send"], "risk_boundary": "Never send anything to anyone."},
    )
    assert assessment["effective_authority"]["external_send"]["authority"] == "blocked_conflict"
    assert assessment["contradictions"]


@pytest.mark.parametrize(("answers", "message"), [
    ({"capabilities": ["teleport"]}, "unknown capabilities"),
    ({"capabilities": ["none", "publish"]}, "cannot be combined"),
    ({"capabilities": ["publish"], "dismissed_signals": ["publish"]}, "both declare and dismiss"),
    ({"dismissed_signals": ["none"]}, "unknown dismissed_signals"),
])
def test_capability_answers_are_validated(answers, message):
    with pytest.raises(ValueError, match=message):
        foundry.validate_answers(answers)


def test_capability_answers_accept_a_comma_separated_string():
    clean = foundry.validate_answers({"capabilities": "external_send, Local_Writes"})
    assert clean["capabilities"] == ["external_send", "local_writes"]


def test_capability_names_in_answers_are_not_scanned_as_wording():
    assessment = foundry.assess_risk_sources(
        "Build an agent that tidies my notes", None,
        {"capabilities": ["none"], "dismissed_signals": ["destructive_deletion"]},
    )
    assert assessment["actions"] == []


def test_run_with_unconfirmed_wording_needs_interview_and_writes_no_agent_spec(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    answers = {**SAFE_ANSWERS, "capabilities": ["local_writes"]}
    state = mobius.run_graph(
        "Build an agent that writes a weekly digest of local project notes and shares it with the team",
        "internal", run_id="unconfirmed", answers=answers,
    )
    assert state["foundry_intake"]["completeness"]["complete"] is True
    assert state["decision"] == "needs_interview"
    assert any("shares it with the team" in q for q in state["interview_questions"])
    assert not state.get("agent_spec_json_path")
    # Until it is confirmed or dismissed, the wording still counts as requested.
    assert state["readiness"]["safety_readiness"]["status"] == "blocked"
    assert [gate["action"] for gate in state["pending_approval_gates"]] == ["external_send"]
    assert state["runtime_recommendation"]["selected"] == "do_not_build_agent"


def test_run_with_dismissed_wording_reaches_spec_ready_and_brief_shows_it(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    answers = {**SAFE_ANSWERS, "dismissed_signals": ["external_send"]}
    state = mobius.run_graph(
        "Build an agent that writes a weekly digest of local project notes and shares it with the team",
        "internal", run_id="dismissed", answers=answers,
    )
    assert state["decision"] == "spec_ready"
    brief = Path(state["brief_path"]).read_text(encoding="utf-8")
    assert "## Dismissed risk signals" in brief
    assert "external_send" in brief


def test_old_answer_sets_without_capabilities_still_need_interview(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    answers = {key: value for key, value in SAFE_ANSWERS.items() if key != "capabilities"}
    state = mobius.run_graph(
        "Build an agent that writes a weekly digest of local project notes",
        "internal", run_id="old_answers", answers=answers,
    )
    assert state["decision"] == "needs_interview"
    assert state["foundry_intake"]["completeness"]["missing"] == ["capabilities"]


def test_agent_requests_are_classified_by_what_the_agent_does(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Build an agent that writes a weekly digest of local project notes", run_id="goal_type",
    )
    assert state["goal_type"] == "writing"
    assert state["scaffold_context"] == "internal"
    assert "Agent Spec" in state["working_spec"]["expected_artifacts"]
