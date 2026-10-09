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
    assert result["checks"]["artifact_root_safety"] == "pass"


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



def test_spec_pipeline_has_no_execution_steps():
    # Möbius writes specs and stops: no step may run commands or edit files.
    banned = ("patch", "rollback", "worker", "keep_going", "change_set", "execute")
    assert not [node for node in mobius.GRAPH_NODE_ORDER if any(word in node for word in banned)]
    for name in ("apply_single_change_patch", "run_local_worker_commands", "run_keep_going_loop"):
        assert not hasattr(mobius, name)


def test_cli_offers_no_execution_flags(capsys, monkeypatch):
    import pytest
    from mobius import cli

    monkeypatch.setattr("sys.argv", ["mobius", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    help_text = capsys.readouterr().out
    for flag in ("--execute", "--patch", "--keep-going", "--bounded-loop", "--self-patch",
                 "--worker-command", "--rollback", "--change-set", "--foundry"):
        assert flag not in help_text
    assert "--agent-intake" in help_text
