from __future__ import annotations

from pathlib import Path

from mobius import graph as mobius


def test_graph_node_order_contains_core_governance_steps():
    assert mobius.GRAPH_NODE_ORDER[:5] == [
        "intake_objective",
        "classify_goal",
        "define_goal_rubric",
        "reason_about_scaffold",
        "build_working_spec",
    ]
    assert "build_approval_packet" in mobius.GRAPH_NODE_ORDER
    assert "record_run_history" == mobius.GRAPH_NODE_ORDER[-1]
    assert mobius.GRAPH_NODE_ORDER.index("write_report") < mobius.GRAPH_NODE_ORDER.index("record_run_history")


def test_doctor_passes_in_repo_export():
    result = mobius.run_doctor()
    assert result["status"] == "pass", result
    assert result["checks"]["app_root_safety"] == "pass"
    assert result["checks"]["worker_command_safety"] == "pass"


def test_doctor_does_not_access_legacy_fixed_tmp_path(monkeypatch):
    legacy_probe = Path("/tmp/mobius_doctor_outside.txt")
    real_write_text = Path.write_text
    real_unlink = Path.unlink

    def guarded_write_text(path, *args, **kwargs):
        assert path != legacy_probe, "doctor must not write the legacy fixed /tmp probe"
        return real_write_text(path, *args, **kwargs)

    def guarded_unlink(path, *args, **kwargs):
        assert path != legacy_probe, "doctor must not unlink the legacy fixed /tmp probe"
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "unlink", guarded_unlink)
    result = mobius.run_doctor()
    assert result["status"] == "pass", result


def test_local_worker_rejects_shell_chaining(tmp_path, monkeypatch):
    app_root = tmp_path / ".mobius"
    app_root.mkdir()
    monkeypatch.setattr(mobius, "APP_DIR", app_root)

    result = mobius.run_local_worker_commands(
        ["python3 -m pytest --version; printf MOBIUS_PREFIX_BYPASS"],
        app_root,
        max_commands=1,
        timeout_seconds=30,
    )

    assert result["status"] == "blocked"
    assert result["runs"][0]["allowed"] is False
    assert "MOBIUS_PREFIX_BYPASS" not in result["runs"][0].get("stdout_tail", "")

    blocked_state = mobius.execute_local_worker_adapter({
        "mode": "bounded_control_loop",
        "execute_local": True,
        "worker_commands": ["python3 -m pytest --version; printf MOBIUS_PREFIX_BYPASS"],
        "budget_policy": {"max_worker_runs": 1, "max_minutes": 1},
        "side_effects_performed": [],
    })
    assert blocked_state["local_worker_result"]["status"] == "blocked"
    assert blocked_state.get("side_effects_performed") == []

    (app_root / "probe.py").write_text("value = 1\n")
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("PYTHONPATH", "/tmp/untrusted-pythonpath")
    valid = mobius.run_local_worker_commands(
        ["python3 -m py_compile probe.py"],
        app_root,
        max_commands=1,
        timeout_seconds=30,
    )
    assert valid["status"] == "pass"
    assert valid["runs"][0]["allowed"] is True

    escaped = mobius.run_local_worker_commands(
        ["python3 -m py_compile ../outside.py"],
        app_root,
        max_commands=1,
        timeout_seconds=30,
    )
    assert escaped["status"] == "blocked"


def test_legacy_execution_records_actual_side_effects(tmp_path, monkeypatch):
    app_root = tmp_path / ".mobius"
    app_root.mkdir()
    target = app_root / "target.txt"
    target.write_text("before")
    monkeypatch.setattr(mobius, "APP_DIR", app_root)

    result = mobius.apply_approved_patch({
        "mode": "bounded_control_loop",
        "execute_patch": True,
        "propose_patch": False,
        "side_effects_performed": [],
        "patch_request": {
            "file_path": str(target),
            "old_string": "before",
            "new_string": "after",
        },
    })

    assert target.read_text() == "after"
    assert result["single_change_patch_result"]["status"] == "pass"
    assert result["side_effects_performed"] == ["single_change_patch"]


def test_basic_run_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(mobius, "APP_DIR", tmp_path / ".mobius")
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", tmp_path / ".mobius" / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", tmp_path / ".mobius" / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", tmp_path / ".mobius" / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", tmp_path / ".mobius" / "history")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", tmp_path / ".mobius" / "history" / "runs.jsonl")
    state = mobius.run_graph("Prepare a bounded local-only smoke test", "internal", run_id="pytest_smoke")
    assert state["decision"] in {"spec_ready", "ready_to_execute", "needs_interview", "human_approval_required"}
    assert Path(state["report_path"]).exists()
    assert Path(state["json_spec_path"]).exists()
    assert Path(state["checkpoint_path"]).exists()


def test_quality_review_spec_ready_high_score_passes():
    state = {
        "mode": "bounded_control_loop",
        "working_spec": {
            "objective": "x", "goal_type": "code", "scaffold_context": "internal",
            "recommended_stack": "python", "scaffold_rationale": "r", "non_goals": "none",
        },
        "success_criteria": True, "verifier_plan": True, "budget_policy": True,
        "execution_loop": True, "json_spec_path": "s.json", "checkpoint_path": "c.json",
        "patch_evaluation": True, "decision": "spec_ready",
    }
    out = mobius.quality_review_spec(state)
    assert out["quality_score"] >= 80
    assert out["quality_status"] == "pass"


def test_quality_review_spec_ready_low_score_needs_revision():
    state = {
        "mode": "bounded_control_loop",
        "working_spec": {"objective": "x"},  # minimal -> low score
        "decision": "spec_ready",
    }
    out = mobius.quality_review_spec(state)
    assert out["quality_score"] < 80
    assert out["quality_status"] == "needs_revision"


def test_quality_review_spec_non_ready_decision_is_not_evaluated_even_with_high_score():
    # Regression: any decision other than ready_to_execute used to report "pass"
    # regardless of score, masking low-quality or unevaluated specs.
    high_score_state = {
        "mode": "bounded_control_loop",
        "working_spec": {
            "objective": "x", "goal_type": "code", "scaffold_context": "internal",
            "recommended_stack": "python", "scaffold_rationale": "r", "non_goals": "none",
        },
        "success_criteria": True, "verifier_plan": True, "budget_policy": True,
        "execution_loop": True, "json_spec_path": "s.json", "checkpoint_path": "c.json",
        "patch_evaluation": True, "decision": "needs_interview",
    }
    for decision in ("needs_interview", "human_approval_required"):
        state = dict(high_score_state, decision=decision)
        out = mobius.quality_review_spec(state)
        assert out["quality_status"] == "not_evaluated", f"decision={decision}"


def test_quality_review_spec_foundry_path_still_passes():
    state = {
        "mode": "foundry_spec_only",
        "foundry_intake": {"completeness": {"complete": True}},
        "risk_assessment": {"actions": []},
        "agent_spec_json_path": "a.json", "agent_spec_markdown_path": "a.md",
        "execution_authorized": False,
    }
    out = mobius.quality_review_spec(state)
    assert out["quality_status"] == "pass"
    assert out["quality_score"] >= 80

