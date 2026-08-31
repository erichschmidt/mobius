"""Mobius trace report rendering — operator-first, advisory contracts on demand."""
from __future__ import annotations

from typing import Any, Mapping
import json

_V22_ARTIFACT_CLASSES = {
    "launch_package",
    "governance_packet",
    "operating_playbook",
    "dashboard",
    "research_synthesis",
}


def _json_block(value: Any) -> list[str]:
    return ["```json", json.dumps(value, indent=2), "```", ""]


def include_v22_contracts(state: Mapping[str, Any]) -> bool:
    router = state.get("artifact_router") or {}
    pipeline = state.get("sectioned_artifact_pipeline") or {}
    dashboard = state.get("interactive_dashboard_contract") or {}
    artifact_class = router.get("artifact_class", "bounded_spec")
    baseline_outputs = {"json_spec", "checkpoint", "markdown_report"}
    extra_outputs = set(router.get("required_outputs") or []) - baseline_outputs
    return (
        artifact_class in _V22_ARTIFACT_CLASSES
        or bool(pipeline.get("enabled"))
        or bool(dashboard.get("enabled"))
        or bool(extra_outputs)
    )


def include_v23_contracts(state: Mapping[str, Any]) -> bool:
    objective = (state.get("objective") or "").lower()
    if "deepagent" in objective or "deep agent" in objective:
        return True
    harness = state.get("deep_agent_harness_contract") or {}
    return bool(harness.get("objective_signals"))


def include_artifact_governance(state: Mapping[str, Any]) -> bool:
    contract = state.get("artifact_contract") or {}
    if contract.get("mode") == "interview_to_artifact":
        return True
    objective = (state.get("objective") or "").lower()
    return "decision ledger" in objective or "constraint ledger" in objective


def include_foundry_detail(state: Mapping[str, Any]) -> bool:
    intake = state.get("foundry_intake") or {}
    return intake.get("status") != "not_applicable"


def include_risk_detail(state: Mapping[str, Any]) -> bool:
    if include_foundry_detail(state):
        return True
    risk = state.get("risk_level", "low")
    assessment = state.get("risk_assessment") or {}
    return risk != "low" or bool(assessment.get("actions"))


def include_venture_loop(state: Mapping[str, Any]) -> bool:
    venture = state.get("venture_loop") or {}
    return venture.get("status") not in {None, "skipped"}


def _result_active(result: Mapping[str, Any] | None) -> bool:
    if not result:
        return False
    status = result.get("status")
    return status not in {None, "skipped", "not_run", "blocked"}


def include_execution_detail(state: Mapping[str, Any]) -> bool:
    return any(
        _result_active(state.get(key) or {})
        for key in (
            "patch_proposal",
            "single_change_patch_result",
            "atomic_change_set_result",
            "patch_evaluation",
            "rollback_result",
            "post_rollback_verifier_result",
            "local_worker_result",
            "keep_going_result",
        )
    ) or bool(state.get("loop_summary"))


def render_markdown_report(state: Mapping[str, Any]) -> str:
    spec = state.get("working_spec") or {}
    scaffold = state.get("scaffold_recommendation") or {}
    lines = [
        f"# Möbius Run - {state.get('run_id')}",
        "",
        f"**Mode:** `{state.get('mode')}`",
        f"**Decision:** `{state.get('decision')}`",
        f"**Execution authorized:** `{str(state.get('execution_authorized', False)).lower()}`",
        f"**Goal type:** `{state.get('goal_type')}`",
        f"**Scaffold context:** `{state.get('scaffold_context')}`",
        f"**Risk level:** `{state.get('risk_level')}`",
        f"**Ambiguity score:** `{state.get('ambiguity_score')}`",
        f"**Quality:** `{state.get('quality_status')}` ({state.get('quality_score')}/100)",
        f"**Operator brief:** `{state.get('brief_path')}`",
        f"**Next action:** {state.get('recommended_next_action') or ''}",
        "",
        "## Submitted Objective",
        "",
        "```json",
        json.dumps(state.get("objective"), ensure_ascii=False),
        "```",
        "",
        "## Scaffold Recommendation",
        "",
        f"- **Location:** {scaffold.get('location')}",
        f"- **Stack:** {scaffold.get('stack')}",
        f"- **Testing:** {scaffold.get('testing')}",
        f"- **Why this scaffold:** {scaffold.get('why')}",
        f"- **Avoid:** {scaffold.get('avoid')}",
        "",
        "## Working Spec",
        "",
        *(_json_block(spec)),
        "## Success Criteria",
        "",
    ]
    lines += [f"- {x}" for x in state.get("success_criteria", [])]
    lines += ["", "## Verifier Plan", ""]
    lines += [f"- {x}" for x in state.get("verifier_plan", [])]
    lines += ["", "## Budget and Runaway Controls", ""]
    lines += _json_block(state.get("budget_policy", {}))
    lines += ["## Rubric Score", ""]
    lines += _json_block(state.get("rubric_score", {}))
    lines += ["## Approval Packet", ""]
    lines += _json_block(state.get("approval_packet", {}))

    if include_risk_detail(state):
        lines += ["## Action-Aware Risk Assessment", ""]
        lines += _json_block(state.get("risk_assessment", {}))

    if include_foundry_detail(state):
        lines += ["## Intake", ""]
        lines += _json_block(state.get("agent_foundry_contract", {}))
        lines += ["## Foundry Intake", ""]
        lines += _json_block(state.get("foundry_intake", {}))
        lines += ["## Foundry Approval Gates", ""]
        lines += _json_block(state.get("approval_gates", []))
        lines += ["## Foundry Readiness", ""]
        lines += _json_block(state.get("readiness", {}))
        lines += ["## Runtime Recommendation", ""]
        lines += _json_block(state.get("runtime_recommendation", {}))
        if state.get("agent_spec_json_path") or state.get("agent_spec_markdown_path"):
            lines += [
                "## Standalone Agent Spec Paths",
                "",
                f"- JSON: `{state.get('agent_spec_json_path')}`",
                f"- Markdown: `{state.get('agent_spec_markdown_path')}`",
                "",
            ]

    if include_v22_contracts(state):
        lines += ["## Artifact Router", ""]
        lines += _json_block(state.get("artifact_router", {}))
        lines += ["## Method Basis Ledger", ""]
        lines += _json_block(state.get("method_basis_ledger", {}))
        lines += ["## Sectioned Artifact Pipeline", ""]
        lines += _json_block(state.get("sectioned_artifact_pipeline", {}))
        lines += ["## State Key Schema", ""]
        lines += _json_block(state.get("state_key_schema", {}))
        lines += ["## Interactive Dashboard Contract", ""]
        lines += _json_block(state.get("interactive_dashboard_contract", {}))

    if include_v23_contracts(state):
        lines += ["## Deep Agent Harness Contract", ""]
        lines += _json_block(state.get("deep_agent_harness_contract", {}))
        lines += ["## Subagent Delegation Matrix", ""]
        lines += _json_block(state.get("subagent_delegation_matrix", {}))
        lines += ["## Context Filesystem Policy", ""]
        lines += _json_block(state.get("context_filesystem_policy", {}))
        lines += ["## Human Interrupt Policy", ""]
        lines += _json_block(state.get("human_interrupt_policy", {}))
        lines += ["## Context Compaction Policy", ""]
        lines += _json_block(state.get("context_compaction_policy", {}))

    if include_artifact_governance(state):
        lines += ["## Artifact Contract", ""]
        lines += _json_block(state.get("artifact_contract", {}))
        lines += ["## Decision Ledger", ""]
        lines += _json_block(state.get("decision_ledger", {}))
        lines += ["## Constraint Ledger", ""]
        lines += _json_block(state.get("constraint_ledger", {}))
        lines += ["## Verification Contract", ""]
        lines += _json_block(state.get("verification_contract", {}))

    if include_venture_loop(state):
        lines += [
            "## Venture/Product Extension Loop",
            "",
            "Business Plan / GTM Strategy / MVP Spec / Validation Plan / Mobius Handoff",
            "",
        ]
        lines += _json_block(state.get("venture_loop", {}))

    lines += [
        "## JSON Spec and Checkpoint",
        "",
        f"- JSON spec: `{state.get('json_spec_path')}`",
        f"- Checkpoint: `{state.get('checkpoint_path')}`",
        "",
    ]

    if include_execution_detail(state):
        lines += ["## Execution Loop", ""]
        lines += _json_block(state.get("execution_loop", {}))
        if state.get("patch_proposal"):
            lines += ["## Patch Proposal", ""]
            lines += _json_block(state.get("patch_proposal", {}))
        if _result_active(state.get("single_change_patch_result") or {}):
            lines += ["## Single-Change Patch Worker", ""]
            lines += _json_block(state.get("single_change_patch_result", {}))
        if _result_active(state.get("atomic_change_set_result") or {}):
            lines += ["## Atomic Change Set", ""]
            lines += _json_block(state.get("atomic_change_set_result", {}))
        if state.get("patch_evaluation"):
            lines += ["## Patch Evaluation and Rollback Recommendation", ""]
            lines += _json_block(state.get("patch_evaluation", {}))
        if _result_active(state.get("rollback_result") or {}):
            lines += ["## Guarded Rollback", ""]
            lines += _json_block(state.get("rollback_result", {}))
        if _result_active(state.get("post_rollback_verifier_result") or {}):
            lines += ["## Post-Rollback Verifier", ""]
            lines += _json_block(state.get("post_rollback_verifier_result", {}))
        if state.get("loop_summary"):
            lines += ["## Loop Summary", ""]
            lines += _json_block(state.get("loop_summary", {}))
        if _result_active(state.get("local_worker_result") or {}):
            lines += ["## Local Worker Adapter", ""]
            lines += _json_block(state.get("local_worker_result", {}))
        if state.get("keep_going_result"):
            lines += ["## Keep-Going Loop", ""]
            lines += _json_block(state.get("keep_going_result", {}))

    if state.get("interview_questions"):
        lines += ["## Interview Questions Before Execution", ""]
        lines += [f"{i + 1}. {q}" for i, q in enumerate(state.get("interview_questions", []))]
        lines.append("")
    if state.get("assumptions"):
        lines += ["## Assumptions", ""]
        lines += [f"- {a}" for a in state.get("assumptions", [])]
        lines.append("")
    lines += ["## Safety Boundary", ""]
    lines += [f"- {x}" for x in spec.get("non_goals", [])]
    lines.append("")
    return "\n".join(lines)
