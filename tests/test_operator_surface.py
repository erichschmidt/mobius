from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobius import graph as mobius
from mobius import operator_surface


def isolate_runtime(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app / "history")
    monkeypatch.setattr(mobius, "DEFAULT_AGENT_SPEC_DIR", app / "agent_specs")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")


def test_operator_brief_is_short_and_names_the_next_move():
    text = operator_surface.render_operator_brief({
        "run_id": "brief_case",
        "decision": "needs_interview",
        "risk_level": "low",
        "quality_status": "not_evaluated",
        "quality_score": 40,
        "mode": "bounded_control_loop",
        "goal_type": "code",
        "scaffold_context": "internal",
        "objective": "Prepare a bounded local-only smoke test",
        "interview_questions": ["What is the stop condition?"],
        "pending_approval_gates": [],
        "brief_path": "/tmp/brief.md",
        "report_path": "/tmp/trace.md",
        "json_spec_path": "/tmp/spec.json",
    })
    lines = text.splitlines()
    assert len(lines) <= operator_surface.OPERATOR_BRIEF_MAX_LINES
    assert "**Decision:** `needs_interview`" in text
    assert "Do next" in text
    assert "Answer the interview questions" in text
    assert "record-outcome brief_case" in text


def test_run_writes_brief_and_trace(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Prepare a bounded local-only smoke test",
        "internal",
        run_id="pytest_brief",
    )
    brief = Path(state["brief_path"])
    trace = Path(state["report_path"])
    assert brief.exists()
    assert trace.exists()
    assert brief.name == "pytest_brief_brief.md"
    assert trace.name == "pytest_brief_mobius_spec.md"
    brief_text = brief.read_text(encoding="utf-8")
    assert len(brief_text.splitlines()) <= operator_surface.OPERATOR_BRIEF_MAX_LINES
    assert "Do next" in brief_text
    assert state["recommended_next_action"]
    summary = json.loads(mobius.summarize_for_cli(state))
    assert summary["brief_path"] == state["brief_path"]
    assert summary["decision"] == state["decision"]
    assert summary["recommended_next_action"]
    assert set(summary) <= {
        "decision", "risk_level", "run_id", "mode", "execution_authorized",
        "recommended_next_action", "interview_questions", "pending_approval_gates",
        "intake_complete", "missing", "runtime", "brief_path", "checkpoint_path",
        "agent_spec",
    }


def test_record_outcome_and_learning_report(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Prepare a bounded local-only smoke test",
        "internal",
        run_id="pytest_outcome",
    )
    recorded = operator_surface.record_outcome(
        state["run_id"],
        "accepted",
        "used the brief",
        history_dir=mobius.DEFAULT_HISTORY_DIR,
        app_dir=mobius.APP_DIR,
    )
    assert recorded["status"] == "recorded"
    assert recorded["outcome"] == "accepted"
    outcomes_path = Path(recorded["outcomes_path"])
    assert outcomes_path.exists()
    rows = [json.loads(line) for line in outcomes_path.read_text(encoding="utf-8").splitlines() if line]
    assert rows[-1]["run_id"] == "pytest_outcome"
    assert rows[-1]["note"] == "used the brief"

    report = operator_surface.build_learning_report(
        history_dir=mobius.DEFAULT_HISTORY_DIR,
        app_dir=mobius.APP_DIR,
    )
    assert report["status"] == "ok"
    assert report["matched"] == 1
    assert report["by_outcome"]["accepted"] == 1
    assert report["unmatched_runs"] == []
    goal_bucket = report["by_goal_type"][state["goal_type"]]
    assert goal_bucket["n"] == 1
    assert goal_bucket["acceptance_rate"] == 1.0
    assert report["by_scaffold_context"][state["scaffold_context"]]["n"] == 1


def test_learning_report_uses_latest_outcome_per_run(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    mobius.run_graph("Prepare a bounded local-only smoke test", "internal", run_id="flip")
    operator_surface.record_outcome("flip", "rejected", "too vague", history_dir=mobius.DEFAULT_HISTORY_DIR, app_dir=mobius.APP_DIR)
    operator_surface.record_outcome("flip", "accepted", "fixed questions", history_dir=mobius.DEFAULT_HISTORY_DIR, app_dir=mobius.APP_DIR)
    report = operator_surface.build_learning_report(history_dir=mobius.DEFAULT_HISTORY_DIR, app_dir=mobius.APP_DIR)
    assert report["outcomes_total"] == 2
    assert report["matched"] == 1
    assert report["by_outcome"]["accepted"] == 1
    assert report["by_outcome"]["rejected"] == 0
    assert report["rejection_notes"] == []


def test_record_outcome_rejects_bad_values(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        operator_surface.record_outcome("ok_run", "ship-it", history_dir=mobius.DEFAULT_HISTORY_DIR, app_dir=mobius.APP_DIR)
    with pytest.raises(ValueError):
        operator_surface.record_outcome("../escape", "accepted", history_dir=mobius.DEFAULT_HISTORY_DIR, app_dir=mobius.APP_DIR)


def test_record_outcome_rejects_symlink_history(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    history = mobius.DEFAULT_HISTORY_DIR
    history.mkdir(parents=True)
    real = tmp_path / "outside.jsonl"
    real.write_text("")
    link = history / "outcomes.jsonl"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        operator_surface.record_outcome("ok_run", "accepted", history_dir=history, app_dir=mobius.APP_DIR)


def test_quality_non_ready_still_not_pass():
    out = mobius.quality_review_spec({
        "mode": "bounded_control_loop",
        "working_spec": {
            "objective": "x", "goal_type": "code", "scaffold_context": "internal",
            "recommended_stack": "python", "scaffold_rationale": "r", "non_goals": "none",
        },
        "success_criteria": True, "verifier_plan": True, "budget_policy": True,
        "execution_loop": True, "json_spec_path": "s.json", "checkpoint_path": "c.json",
        "patch_evaluation": True, "decision": "needs_interview",
    })
    assert out["quality_status"] == "not_evaluated"
