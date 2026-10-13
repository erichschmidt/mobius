"""Mobius trace report rendering — operator-first, advisory contracts on demand."""
from __future__ import annotations

from typing import Any, Mapping
import json


def _json_block(value: Any) -> list[str]:
    return ["```json", json.dumps(value, indent=2), "```", ""]


def include_foundry_detail(state: Mapping[str, Any]) -> bool:
    intake = state.get("foundry_intake") or {}
    return intake.get("status") != "not_applicable"


def include_risk_detail(state: Mapping[str, Any]) -> bool:
    if include_foundry_detail(state):
        return True
    risk = state.get("risk_level", "low")
    assessment = state.get("risk_assessment") or {}
    return risk != "low" or bool(assessment.get("actions"))


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
        lines += ["## Agent Intake", ""]
        lines += _json_block(state.get("foundry_intake", {}))
        lines += ["## Approval Gates", ""]
        lines += _json_block(state.get("approval_gates", []))
        lines += ["## Readiness", ""]
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

    if state.get("assist"):
        lines += ["## Model Assist (advisory)", ""]
        lines += _json_block(state.get("assist"))

    lines += [
        "## JSON Spec and Checkpoint",
        "",
        f"- JSON spec: `{state.get('json_spec_path')}`",
        f"- Checkpoint: `{state.get('checkpoint_path')}`",
        "",
    ]

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
