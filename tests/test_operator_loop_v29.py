from __future__ import annotations

from pathlib import Path

from mobius import foundry
from mobius import graph as mobius
from mobius import reporting


def isolate_runtime(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app / "history")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")


def test_foundry_interview_questions_are_human_readable():
    questions = foundry.interview_questions_for_dimensions(["trigger", "human_gate", "outputs"])
    assert all("Foundry intake dimension" not in q for q in questions)
    assert any("start" in q.lower() for q in questions)
    assert any("approve" in q.lower() for q in questions)


def test_approval_gate_questions_are_human_readable():
    gate = {"action": "external_send", "status": "pending"}
    question = foundry.interview_question_for_gate(gate["action"])
    assert "external_send" not in question
    assert "sign-off" in question.lower() or "approve" in question.lower()


def test_smoke_run_trace_omits_advisory_contract_sections(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph("Prepare a bounded local-only smoke test", "internal", run_id="pytest_v29_smoke")
    report_text = Path(state["report_path"]).read_text()
    assert "## Working Spec" in report_text
    assert "## Deep Agent Harness Contract" not in report_text
    assert "## Artifact Router" not in report_text
    assert "## Intake" not in report_text
    assert len(report_text.splitlines()) < 250


def test_agent_request_trace_includes_foundry_and_human_questions(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Build an agent that reviews my inbox and emails customers about overdue invoices",
        "client_work",
        run_id="pytest_v29_foundry",
    )
    report_text = Path(state["report_path"]).read_text()
    brief_text = Path(state["brief_path"]).read_text()
    assert "## Intake" in report_text
    assert "## Action-Aware Risk Assessment" in report_text
    assert state["interview_questions"]
    assert all("Foundry intake dimension" not in q for q in state["interview_questions"])
    assert "sign-off" in brief_text.lower() or "approve" in brief_text.lower()


def test_reporting_helpers_match_specialized_objectives():
    v22_state = {
        "artifact_router": {"artifact_class": "launch_package", "required_outputs": ["html_dashboard"]},
        "sectioned_artifact_pipeline": {"enabled": True},
        "interactive_dashboard_contract": {"enabled": True},
    }
    assert reporting.include_v22_contracts(v22_state)

    v23_state = {"objective": "Explore the deepagents repo", "deep_agent_harness_contract": {}}
    assert reporting.include_v23_contracts(v23_state)

    governance_state = {"artifact_contract": {"mode": "interview_to_artifact"}}
    assert reporting.include_artifact_governance(governance_state)
