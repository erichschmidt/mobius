from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobius import foundry
from mobius import graph as mobius


COMPLETE_SAFE_ANSWERS = {
    "goal": "Create a weekly digest of local project status.",
    "trigger": "Manual command every Friday.",
    "inputs": ["local JSON status files"],
    "outputs": ["local Markdown digest"],
    "tools": ["read-only filesystem"],
    "memory": "Store only the latest digest in the project folder.",
    "cadence": "weekly",
    "human_gate": "No external actions; review the local draft manually.",
    "risk_boundary": "Never send, publish, purchase, or access credentials.",
    "success_criteria": ["Digest contains every active project."],
    "verification_plan": ["Run fixture-based tests and read back the Markdown."],
    "registration_path": "docs/agents/weekly-digest.md",
}


def isolate_runtime(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app / "history")
    monkeypatch.setattr(mobius, "DEFAULT_AGENT_SPEC_DIR", app / "agent_specs")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")


def test_action_aware_risk_does_not_turn_prohibitions_into_requests():
    assessment = foundry.assess_risk(
        "Build an agent that must not send email, never publish publicly, and does not purchase anything."
    )
    requested = {item["action"] for item in assessment["actions"] if item["disposition"] == "requested"}
    prohibited = {item["action"] for item in assessment["actions"] if item["disposition"] == "prohibited"}
    assert requested == set()
    assert prohibited >= {"external_send", "publish", "purchase_payment_trade"}
    assert assessment["level"] == "low"


def test_affirmative_and_mixed_actions_have_evidence_and_pending_gates():
    assessment = foundry.assess_risk(
        "Send the approved digest by email and publish it, but never purchase anything or access credentials. "
        "Ask before changing production records."
    )
    pairs = {(item["action"], item["disposition"]) for item in assessment["actions"]}
    assert ("external_send", "requested") in pairs
    assert ("publish", "requested") in pairs
    assert ("purchase_payment_trade", "prohibited") in pairs
    assert ("credentials_secrets", "prohibited") in pairs
    assert ("production_changes", "approval_gated") in pairs
    assert all(item["evidence"] for item in assessment["actions"])
    gates = foundry.build_approval_gates(assessment, {})
    pending = {gate["action"] for gate in gates if gate["status"] == "pending"}
    assert pending >= {"external_send", "publish", "production_changes"}


def test_risk_precedes_foundry_contract_and_history_follows_report():
    assert mobius.GRAPH_NODE_ORDER.index("detect_risk_and_ambiguity") < mobius.GRAPH_NODE_ORDER.index("build_agent_foundry_contract")
    assert mobius.GRAPH_NODE_ORDER.index("quality_review_spec") < mobius.GRAPH_NODE_ORDER.index("write_report")
    assert mobius.GRAPH_NODE_ORDER.index("write_report") < mobius.GRAPH_NODE_ORDER.index("record_run_history")


def test_incomplete_intake_needs_interview_and_writes_no_completed_agent_spec(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph("Build an agent that summarizes local notes", "internal", run_id="incomplete")
    assert state["decision"] == "needs_interview"
    intake = state["foundry_intake"]
    assert intake["completeness"]["missing"]
    assert {item["status"] for item in intake["dimensions"].values()} <= {"answered", "inferred", "missing"}
    assert not state.get("agent_spec_json_path")
    assert not list((tmp_path / ".mobius" / "agent_specs").glob("*"))
    assert state["readiness"]["verification_evidence"]["status"] != "pass"


def test_complete_safe_intake_writes_standalone_specs_and_one_runtime(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Build a weekly agent that creates a local project digest and never sends or publishes it",
        "internal",
        run_id="safe_complete",
        answers=COMPLETE_SAFE_ANSWERS,
    )
    assert state["foundry_intake"]["completeness"]["complete"] is True
    assert state["decision"] == "spec_ready"
    json_path = Path(state["agent_spec_json_path"])
    markdown_path = Path(state["agent_spec_markdown_path"])
    assert json_path.parent.name == "agent_specs" and json_path.exists()
    assert markdown_path.parent.name == "agent_specs" and markdown_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["schema_version"] == "mobius.agent_spec.v1.0"
    assert payload["risk_assessment"]["level"] in {"low", "medium", "high"}
    assert payload["runtime"]["selected"] in foundry.RUNTIME_OPTIONS
    assert set(payload["runtime"]) >= {"selected", "reasons"}
    assert "# Agent Spec:" in markdown_path.read_text()
    assert state["readiness"]["verification_evidence"]["status"] != "pass"


def test_complete_risky_intake_exposes_pending_gate_and_blocked_readiness(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    answers = {**COMPLETE_SAFE_ANSWERS, "outputs": ["email to customers"], "human_gate": "Ask me before every send"}
    state = mobius.run_graph(
        "Build an agent to send a customer email every Friday",
        "internal",
        run_id="risky_complete",
        answers=answers,
    )
    assert state["decision"] == "human_approval_required"
    assert {gate["action"] for gate in state["pending_approval_gates"]} == {"external_send"}
    assert state["readiness"]["safety_readiness"]["status"] == "blocked"
    assert state["readiness"]["operational_readiness"]["status"] == "blocked"
    assert state["runtime_recommendation"]["selected"] == "do_not_build_agent"
    assert Path(state["agent_spec_json_path"]).exists()


def test_resume_checkpoint_merges_answers_and_completes(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    first = mobius.run_graph(
        "Build an agent that creates a local weekly digest",
        "internal",
        run_id="resume_intake",
        answers={"goal": COMPLETE_SAFE_ANSWERS["goal"], "trigger": COMPLETE_SAFE_ANSWERS["trigger"]},
    )
    remaining = {key: value for key, value in COMPLETE_SAFE_ANSWERS.items() if key not in {"goal", "trigger"}}
    resumed = mobius.run_graph(
        "",
        answers=remaining,
        resume_checkpoint=first["checkpoint_path"],
    )
    assert resumed["decision"] == "spec_ready"
    assert resumed["foundry_intake"]["completeness"]["complete"] is True
    assert resumed["answers"]["goal"] == COMPLETE_SAFE_ANSWERS["goal"]
    assert resumed["answers"]["outputs"] == COMPLETE_SAFE_ANSWERS["outputs"]
    assert resumed["resumed_from_checkpoint"] == first["checkpoint_path"]


def test_history_contains_final_foundry_fields_and_existing_artifacts_remain(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Build a weekly agent that writes a local digest",
        "internal",
        run_id="history_v25",
        answers=COMPLETE_SAFE_ANSWERS,
    )
    history = json.loads(Path(state["run_history_path"]).read_text().splitlines()[-1])
    assert history["product_version"] == "1.0"
    assert history["report_path"] == state["report_path"]
    assert history["json_spec_path"] == state["json_spec_path"]
    assert history["checkpoint_path"] == state["checkpoint_path"]
    assert history["agent_spec_paths"]["json"] == state["agent_spec_json_path"]
    assert history["runtime_recommendation"] == state["runtime_recommendation"]
    assert history["readiness"] == state["readiness"]
    assert history["approval_gates"] == state["approval_gates"]

    legacy = mobius.run_graph("Prepare a bounded local-only smoke test", "internal", run_id="legacy")
    assert Path(legacy["report_path"]).exists()
    assert Path(legacy["json_spec_path"]).exists()
    assert Path(legacy["checkpoint_path"]).exists()
    assert legacy["agent_foundry_contract"]["status"] == "available"


def test_cli_summary_exposes_foundry_decision_surface(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Build an agent that creates a local weekly digest",
        "internal",
        run_id="summary",
        answers=COMPLETE_SAFE_ANSWERS,
    )
    summary = json.loads(mobius.summarize_for_cli(state))
    assert summary["decision"] == "spec_ready"
    assert summary["intake_complete"] is True
    assert summary["runtime"] in foundry.RUNTIME_OPTIONS
    assert summary["pending_approval_gates"] == []
    assert Path(summary["agent_spec"]).exists()


def test_cross_field_conflict_preserves_provenance_and_blocks():
    answers = {**COMPLETE_SAFE_ANSWERS, "outputs": ["Email the customer"]}
    assessment = foundry.assess_risk_sources("Build an agent. Never send anything.", None, answers)
    occurrences = [item for item in assessment["actions"] if item["canonical_action"] == "external_send"]
    assert {item["classification"] for item in occurrences} >= {"requested", "prohibited"}
    assert {item["source_field"] for item in occurrences} >= {"objective", "answers.outputs"}
    assert assessment["effective_authority"]["external_send"]["authority"] == "blocked_conflict"
    assert assessment["contradictions"]
    assert assessment["level"] == "high"


def test_nothing_is_sent_or_published_is_prohibited_not_requested():
    assessment = foundry.assess_risk_sources(
        "Build an agent that writes a weekly digest of local project notes",
        "internal",
        {
            **COMPLETE_SAFE_ANSWERS,
            "human_gate": "A person reads the local draft. Nothing is sent or published.",
            "risk_boundary": "Never send, publish, purchase, access credentials, or change production systems.",
        },
    )
    publish = [item for item in assessment["actions"] if item["canonical_action"] == "publish"]
    assert publish
    assert {item["classification"] for item in publish} == {"prohibited"}
    assert assessment["effective_authority"]["publish"]["authority"] == "prohibited"
    assert assessment["level"] in {"low", "medium"}


def test_quoted_example_is_mentioned_not_requested():
    assessment = foundry.assess_risk("The policy example says 'send an email,' but this agent only drafts locally.")
    external = [item for item in assessment["actions"] if item["canonical_action"] == "external_send"]
    assert external
    assert {item["classification"] for item in external} == {"mentioned"}
    assert "external_send" not in assessment["requested_authority"]


def test_approval_gate_has_scope_digest_and_answers_cannot_self_approve():
    answers = {**COMPLETE_SAFE_ANSWERS, "outputs": ["Email the customer"]}
    risk = foundry.assess_risk_sources("Build an agent to email customers", None, answers)
    gate = foundry.build_approval_gates(risk, answers, objective="Build an agent to email customers")[0]
    assert gate["status"] == "pending"
    assert len(gate["scope_digest"]) == 64
    assert gate["gate_id"].endswith(gate["scope_digest"][:12])
    changed = {**answers, "outputs": ["Email every customer"]}
    changed_risk = foundry.assess_risk_sources("Build an agent to email customers", None, changed)
    changed_gate = foundry.build_approval_gates(changed_risk, changed, objective="Build an agent to email customers")[0]
    assert changed_gate["scope_digest"] != gate["scope_digest"]
    with pytest.raises(ValueError, match="unknown Foundry answer keys"):
        foundry.validate_answers({**answers, "approval_statuses": {"external_send": "approved"}})


def test_foundry_execution_nodes_are_not_invoked_even_with_execution_flags(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("execution node was invoked in Foundry spec-only mode")

    for name in mobius.FOUNDRY_EXECUTION_NODES:
        monkeypatch.setattr(mobius, name, forbidden)
    state = mobius.run_graph(
        "Build a weekly agent that creates a local project digest and never sends it",
        "internal",
        run_id="spec_only_flags",
        answers=COMPLETE_SAFE_ANSWERS,
        execute_local=True,
        worker_commands=["python3 -m pytest -q"],
        execute_patch=True,
        patch_request={"file_path": "/tmp/outside", "old_string": "a", "new_string": "b"},
        execute_change_set=True,
        change_set_request={"changes": []},
        approval_decisions={"patch": True, "change_set": True},
    )
    assert state["mode"] == "foundry_spec_only"
    assert state["decision"] == "spec_ready"
    assert state["execution_authorized"] is False
    assert state["side_effects_performed"] == []
    assert state["local_worker_result"]["status"] == "skipped"
    assert state["single_change_patch_result"]["status"] == "skipped"
    assert state["atomic_change_set_result"]["status"] == "skipped"


def test_execution_nodes_independently_fail_closed_in_foundry_mode():
    state = {
        "mode": "foundry_spec_only",
        "execute_local": True,
        "execute_patch": True,
        "execute_change_set": True,
        "execute_rollback": True,
        "execute_post_rollback_verify": True,
        "propose_patch": True,
        "approval_decisions": {"patch": True, "change_set": True, "rollback": True},
    }
    checks = (
        (mobius.build_patch_proposal, "patch_proposal"),
        (mobius.apply_approved_patch, "single_change_patch_result"),
        (mobius.apply_approved_change_set, "atomic_change_set_result"),
        (mobius.execute_single_change_patch_worker, "single_change_patch_result"),
        (mobius.execute_local_worker_adapter, "local_worker_result"),
        (mobius.execute_guarded_rollback, "rollback_result"),
        (mobius.execute_post_rollback_verifier, "post_rollback_verifier_result"),
    )
    for function, result_key in checks:
        assert function(state)[result_key]["status"] == "blocked"


def test_tampered_checkpoint_recomputes_derived_fields_and_uses_new_run(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    first = mobius.run_graph(
        "Build an agent that creates a local weekly digest",
        "internal",
        run_id="tamper_parent",
        answers={"goal": COMPLETE_SAFE_ANSWERS["goal"]},
    )
    checkpoint_path = Path(first["checkpoint_path"])
    payload = json.loads(checkpoint_path.read_text())
    payload.update({
        "risk_level": "low",
        "decision": "ready_to_execute",
        "readiness": {name: {"status": "pass"} for name in foundry.READINESS_DIMENSIONS},
        "approval_gates": [{"status": "approved"}],
        "execute_patch": True,
        "patch_request": {"file_path": "/tmp/outside"},
        "run_id": "../../outside",
        "agent_spec_paths": {"json": "/tmp/outside.json"},
    })
    checkpoint_path.write_text(json.dumps(payload))
    remaining = {key: value for key, value in COMPLETE_SAFE_ANSWERS.items() if key != "goal"}
    resumed = mobius.run_graph("", answers=remaining, resume_checkpoint=str(checkpoint_path))
    assert resumed["run_id"] != "../../outside"
    assert resumed["parent_run_id"] == ""
    assert resumed["decision"] == "spec_ready"
    assert resumed["readiness"]["verification_evidence"]["status"] == "not_evaluated"
    assert resumed["execution_authorized"] is False
    assert "execute_patch" in resumed["resume_diagnostics"]["ignored_untrusted_fields"]
    assert not Path("/tmp/outside.json").exists()


def test_invalid_run_id_secret_and_symlink_outputs_fail_closed(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="run_id"):
        mobius.run_graph("Build an agent", run_id="../../outside")
    with pytest.raises(ValueError, match="secret-looking"):
        mobius.run_graph(
            "Build an agent",
            answers={"goal": "Use api_key=abcdefghijklmnop123456"},
        )
    with pytest.raises(ValueError, match="secret-looking"):
        mobius.run_graph("Build an agent with token=abcdefghijklmnop123456")
    app = tmp_path / ".mobius"
    app.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    agent_specs = app / "agent_specs"
    if agent_specs.exists():
        assert not list(agent_specs.iterdir())
        agent_specs.rmdir()
    agent_specs.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        mobius.run_graph(
            "Build a weekly agent that creates a local project digest and never sends it",
            run_id="symlink_block",
            answers=COMPLETE_SAFE_ANSWERS,
        )
    assert not list(outside.iterdir())


def test_spec_only_readiness_and_registration_path_never_overclaim(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    declarative_destination = tmp_path / "must-not-be-written" / "agent.md"
    answers = {**COMPLETE_SAFE_ANSWERS, "registration_path": str(declarative_destination)}
    state = mobius.run_graph(
        "Build a weekly agent that creates a local project digest and never sends it",
        run_id="readiness_truth",
        answers=answers,
    )
    assert state["readiness"]["operational_readiness"]["status"] == "not_evaluated"
    assert state["readiness"]["verification_evidence"]["status"] == "not_evaluated"
    spec = json.loads(Path(state["agent_spec_json_path"]).read_text())
    assert spec["status"] == "spec_ready"
    assert spec["execution_authorized"] is False
    assert not declarative_destination.exists()


def test_artifacts_refuse_collision_and_generated_run_ids_are_unique(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    first = mobius.run_graph("Build an agent that creates a local digest", run_id="collision")
    checkpoint = Path(first["checkpoint_path"])
    original = checkpoint.read_bytes()
    with pytest.raises(FileExistsError):
        mobius.run_graph("Build an agent that creates a local digest", run_id="collision")
    assert checkpoint.read_bytes() == original
    a = mobius.run_graph("Build an agent that creates a local digest")
    b = mobius.run_graph("Build an agent that creates a local digest")
    assert a["run_id"] != b["run_id"]


def test_atomic_artifact_writer_refuses_existing_symlink_target(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged")
    target = root / "artifact.json"
    target.symlink_to(outside)
    with pytest.raises(FileExistsError):
        foundry.atomic_write_new(target, "attacker-controlled")
    assert outside.read_text() == "unchanged"


def test_final_history_matches_all_final_artifacts(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Build a weekly agent that creates a local project digest and never sends it",
        run_id="final_history",
        answers=COMPLETE_SAFE_ANSWERS,
    )
    last = json.loads(Path(state["run_history_path"]).read_text().splitlines()[-1])
    for key in ("report_path", "checkpoint_path", "json_spec_path", "agent_spec_json_path", "agent_spec_markdown_path"):
        assert last[key] == state[key]
        assert Path(last[key]).exists()
    assert last["decision"] == state["decision"]
    assert last["risk_level"] == state["risk_level"]
    assert last["readiness"] == state["readiness"]
    assert last["runtime_recommendation"] == state["runtime_recommendation"]
    assert last["approval_gates"] == state["approval_gates"]


def test_natural_prohibition_phrases_are_not_requests():
    for text in (
        "Nothing is sent or published.",
        "No email is sent.",
        "The digest is not published.",
        "Nothing will be sent.",
    ):
        risk = foundry.assess_risk_sources(text, None, {})
        requested = {
            action
            for action, item in (risk.get("effective_authority") or {}).items()
            if item.get("authority") in {"requested", "approval_gated", "blocked_conflict"}
        }
        assert "publish" not in requested, text
        assert "external_send" not in requested, text


def test_common_approval_and_prohibition_wording_is_classified_truthfully():
    gated = foundry.assess_risk_sources("Do not send email without human approval", None, {})
    assert gated["effective_authority"]["external_send"]["authority"] == "approval_gated"
    assert gated["level"] == "high"

    for text in ("Send no emails", "Email sending is prohibited"):
        risk = foundry.assess_risk_sources(text, None, {})
        assert risk["effective_authority"]["external_send"]["authority"] == "prohibited"
        assert risk["level"] == "low"


def test_structured_answers_force_foundry_but_maintenance_language_does_not(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    forced = mobius.run_graph("Create a weekly local digest", answers=dict(COMPLETE_SAFE_ANSWERS))
    assert forced["mode"] == "foundry_spec_only"
    assert forced["decision"] == "spec_ready"

    maintenance = mobius.run_graph("Document the existing automation architecture")
    assert maintenance["mode"] == "bounded_control_loop"


def test_configured_app_root_symlink_is_rejected_before_writes(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    app_link = tmp_path / "app-link"
    app_link.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(mobius, "APP_DIR", app_link)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app_link / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app_link / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app_link / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app_link / "history")
    monkeypatch.setattr(mobius, "DEFAULT_AGENT_SPEC_DIR", app_link / "agent_specs")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app_link / "history" / "runs.jsonl")
    with pytest.raises(ValueError, match="symlink"):
        mobius.run_graph("Build an agent", answers=dict(COMPLETE_SAFE_ANSWERS))
    assert list(outside.iterdir()) == []


def test_late_artifact_collision_is_preflighted_without_partial_publication(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    run_id = "preflight_collision"
    checkpoint_root = Path(mobius.DEFAULT_CHECKPOINT_DIR)
    checkpoint_root.mkdir(parents=True)
    checkpoint = checkpoint_root / f"{run_id}_checkpoint.json"
    checkpoint.write_text("preserve")
    with pytest.raises(FileExistsError):
        mobius.run_graph("Build an agent", answers=dict(COMPLETE_SAFE_ANSWERS), run_id=run_id)
    assert checkpoint.read_text() == "preserve"
    assert not (Path(mobius.DEFAULT_AGENT_SPEC_DIR) / f"{run_id}_agent_spec.json").exists()
    assert not (Path(mobius.DEFAULT_SPEC_DIR) / f"{run_id}_mobius_spec.json").exists()


def test_sensitive_customer_data_requires_review_even_when_read_only():
    answers = dict(COMPLETE_SAFE_ANSWERS)
    answers["inputs"] = ["customer PII from a read-only CRM export"]
    risk = foundry.assess_risk_sources("Build an agent to summarize CRM records", None, answers)
    gates = foundry.build_approval_gates(risk, answers, objective="Build an agent to summarize CRM records")
    assert risk["level"] == "medium"
    assert [gate["action"] for gate in gates] == ["sensitive_data_access"]


def test_additional_authority_phrases_and_system_record_writes():
    for text in ("Email sending is disallowed", "No sending emails is allowed"):
        prohibited = foundry.assess_risk_sources(text, None, {})
        assert prohibited["effective_authority"]["external_send"]["authority"] == "prohibited"
        assert prohibited["level"] == "low"

    not_permitted = foundry.assess_risk_sources("The agent is not permitted to email customers", None, {})
    assert not_permitted["effective_authority"]["external_send"]["authority"] == "prohibited"

    gated = foundry.assess_risk_sources("The agent may email only after manager sign-off", None, {})
    assert gated["effective_authority"]["external_send"]["authority"] == "approval_gated"

    for request in (
        "Make changes to the CRM",
        "Modify customer records in the CRM",
        "Add a note to the CRM",
        "Set the lifecycle stage in the CRM",
        "Log a call in the CRM",
        "Assign the CRM record to an owner",
    ):
        assessment = foundry.assess_risk_sources(request, None, {})
        assert assessment["effective_authority"]["system_of_record_writes"]["authority"] == "requested"
        assert assessment["level"] == "high"


def test_common_agent_intent_routes_to_spec_only_foundry(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    for index, objective in enumerate((
        "I want an agent that summarizes local notes",
        "An agent that summarizes local notes",
    )):
        state = mobius.run_graph(objective, run_id=f"ordinary_agent_intent_{index}")
        assert state["mode"] == "foundry_spec_only"
        assert state["execution_authorized"] is False


def test_failure_cleanup_preserves_unowned_concurrent_artifact(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    concurrent_path = tmp_path / ".mobius" / "specs" / "concurrent_mobius_spec.json"

    class FailingGraph:
        def invoke(self, _state):
            concurrent_path.write_text("created by another invocation")
            raise RuntimeError("injected failure")

    monkeypatch.setattr(mobius, "build_graph", lambda _order: FailingGraph())
    with pytest.raises(RuntimeError, match="injected failure"):
        mobius.run_graph("Build an agent that summarizes local notes", run_id="concurrent")
    assert concurrent_path.read_text() == "created by another invocation"


def test_failure_cleanup_removes_only_owned_artifact(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    owned_path = tmp_path / ".mobius" / "specs" / "owned_mobius_spec.json"

    class FailingGraph:
        def invoke(self, _state):
            foundry.atomic_write_new(owned_path, "owned")
            raise RuntimeError("injected failure")

    monkeypatch.setattr(mobius, "build_graph", lambda _order: FailingGraph())
    with pytest.raises(RuntimeError, match="injected failure"):
        mobius.run_graph("Build an agent that summarizes local notes", run_id="owned")
    assert not owned_path.exists()


def test_owned_cleanup_refuses_renamed_parent_symlink_and_outside_hardlink(tmp_path):
    original_parent = tmp_path / "original"
    original_parent.mkdir()
    artifact = original_parent / "artifact.json"
    token, owned = foundry.begin_artifact_tracking()
    try:
        foundry.atomic_write_new(artifact, "owned")
    finally:
        foundry.end_artifact_tracking(token)

    moved_parent = tmp_path / "moved"
    original_parent.rename(moved_parent)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_artifact = outside / artifact.name
    outside_artifact.hardlink_to(moved_parent / artifact.name)
    original_parent.symlink_to(outside, target_is_directory=True)

    foundry.cleanup_owned_artifacts(owned)
    assert outside_artifact.read_text() == "owned"
    assert (moved_parent / artifact.name).read_text() == "owned"


def test_doctor_fails_when_langgraph_runtime_is_unavailable(monkeypatch):
    monkeypatch.setattr(mobius, "StateGraph", None)
    result = mobius.run_doctor()
    assert result["status"] == "fail"
    assert result["checks"]["langgraph_runtime"] == "fail"


def test_weekly_digest_example_reaches_spec_ready(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    answers = json.loads(Path("examples/weekly-digest-answers.json").read_text(encoding="utf-8"))
    state = mobius.run_graph(
        "Build an agent that writes a weekly digest of local project notes",
        "internal",
        run_id="readme_digest",
        answers=answers,
    )
    assert state["decision"] == "spec_ready"
    assert state["execution_authorized"] is False
    assert state["scaffold_context"] == "internal"
    assert state["pending_approval_gates"] == []
    assert (state.get("runtime_recommendation") or {}).get("selected") != "do_not_build_agent"
    brief = Path(state["brief_path"]).read_text(encoding="utf-8")
    assert "**Mode:** `intake`" in brief
    assert "foundry_spec_only" not in brief


def test_context_hint_beats_notes_keyword(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    state = mobius.run_graph(
        "Build an agent that writes a weekly digest of local project notes",
        "internal",
        run_id="notes_not_obsidian",
    )
    assert state["scaffold_context"] == "internal"
    assert state["decision"] == "needs_interview"
