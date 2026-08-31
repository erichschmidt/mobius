#!/usr/bin/env python3
"""Möbius v1 — pre-agent constitution.

Turns a vague objective into an inspectable spec, a human-readable brief,
and (when needed) interview questions. Does not build or run agents by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
import os
from typing import Any, Literal, TypedDict
import json
import re
import shlex
import subprocess
import sys
import tempfile

from . import RELEASE_VERSION
from . import foundry
from . import keep_going
from . import operator_surface
from . import reporting

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - tests verify LangGraph in this env
    END = "__end__"
    StateGraph = None  # type: ignore

GoalType = Literal["code", "research", "writing", "system_admin", "obsidian_project", "business_ops", "unknown"]
RiskLevel = Literal["low", "medium", "high"]
ScaffoldContext = Literal["internal", "client_work", "public_repo", "throwaway_spike", "obsidian_only", "unknown"]
Decision = Literal["ready_to_execute", "spec_ready", "needs_interview", "human_approval_required"]

APP_DIR = Path(os.environ.get("MOBIUS_APP_DIR", Path.cwd() / ".mobius")).absolute()
# Self-patch lane root: the package source tree itself. Only reachable via
# --self-patch (opt-in, loud); the default lane stays scoped to APP_DIR.
SELF_PATCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = APP_DIR / "runs"
DEFAULT_SPEC_DIR = APP_DIR / "specs"
DEFAULT_CHECKPOINT_DIR = APP_DIR / "checkpoints"
DEFAULT_HISTORY_DIR = APP_DIR / "history"
DEFAULT_AGENT_SPEC_DIR = APP_DIR / "agent_specs"
RUN_HISTORY_PATH = DEFAULT_HISTORY_DIR / "runs.jsonl"

GRAPH_NODE_ORDER = [
    "intake_objective",
    "classify_goal",
    "define_goal_rubric",
    "reason_about_scaffold",
    "build_working_spec",
    "detect_risk_and_ambiguity",
    "build_agent_foundry_contract",
    "generate_interview_if_needed",
    "define_success_criteria",
    "design_budget_policy",
    "design_execution_loop",
    "apply_goal_rubric_score",
    "build_approval_packet",
    "finalize_foundry_spec",
    "export_json_spec",
    "build_patch_proposal",
    "apply_approved_patch",
    "apply_approved_change_set",
    "execute_single_change_patch_worker",
    "execute_local_worker_adapter",
    "run_keep_going_loop",
    "evaluate_patch_and_verifier",
    "execute_guarded_rollback",
    "execute_post_rollback_verifier",
    "quality_review_spec",
    "write_checkpoint",
    "write_report",
    "record_run_history",
]

FOUNDRY_EXECUTION_NODES = {
    "build_patch_proposal",
    "apply_approved_patch",
    "apply_approved_change_set",
    "execute_single_change_patch_worker",
    "execute_local_worker_adapter",
    "run_keep_going_loop",
    "evaluate_patch_and_verifier",
    "execute_guarded_rollback",
    "execute_post_rollback_verifier",
}
FOUNDRY_NODE_ORDER = [node for node in GRAPH_NODE_ORDER if node not in FOUNDRY_EXECUTION_NODES]

RISK_TERMS = {
    "send", "email", "post", "publish", "delete", "remove", "trade", "buy", "purchase",
    "credential", "secret", "token", "production", "customer", "client", "outreach", "public",
}
CODE_TERMS = {"build", "code", "app", "script", "cli", "api", "test", "repo", "implement", "fix", "debug", "verify", "self", "check"}
RESEARCH_TERMS = {"research", "compare", "evaluate", "analyze", "find", "source", "summarize", "investigate"}
WRITING_TERMS = {"write", "draft", "article", "post", "copy", "brief", "memo", "proposal"}
SYSTEM_TERMS = {"server", "cron", "config", "env", "service", "logs", "backup", "dashboard"}
OBSIDIAN_TERMS = {"obsidian", "vault"}
BUSINESS_TERMS = {"client", "lead", "sales", "campaign", "sponsor", "launch"}


class MobiusState(TypedDict, total=False):
    objective: str
    context_hint: str | None
    run_id: str
    goal_type: GoalType
    goal_rubric: dict[str, Any]
    rubric_score: dict[str, Any]
    approval_packet: dict[str, Any]
    product_contract: dict[str, Any]
    product_status: dict[str, Any]
    artifact_router: dict[str, Any]
    method_basis_ledger: dict[str, Any]
    sectioned_artifact_pipeline: dict[str, Any]
    state_key_schema: dict[str, Any]
    interactive_dashboard_contract: dict[str, Any]
    deep_agent_harness_contract: dict[str, Any]
    subagent_delegation_matrix: dict[str, Any]
    context_filesystem_policy: dict[str, Any]
    human_interrupt_policy: dict[str, Any]
    context_compaction_policy: dict[str, Any]
    artifact_contract: dict[str, Any]
    decision_ledger: dict[str, Any]
    constraint_ledger: dict[str, Any]
    verification_contract: dict[str, Any]
    run_history_path: str
    scaffold_context: ScaffoldContext
    risk_level: RiskLevel
    ambiguity_score: int
    assumptions: list[str]
    scaffold_recommendation: dict[str, Any]
    working_spec: dict[str, Any]
    enable_venture_loop: bool
    venture_loop: dict[str, Any]
    agent_foundry_contract: dict[str, Any]
    answers: dict[str, Any]
    foundry_intake: dict[str, Any]
    risk_assessment: dict[str, Any]
    approval_gates: list[dict[str, Any]]
    pending_approval_gates: list[dict[str, Any]]
    readiness: dict[str, Any]
    runtime_recommendation: dict[str, Any]
    agent_spec: dict[str, Any]
    agent_spec_json_path: str
    agent_spec_markdown_path: str
    interview_questions: list[str]
    success_criteria: list[str]
    verifier_plan: list[str]
    budget_policy: dict[str, Any]
    execution_loop: dict[str, Any]
    execute_local: bool
    worker_commands: list[str]
    self_patch: bool
    json_spec_path: str
    checkpoint_path: str
    local_worker_result: dict[str, Any]
    execute_patch: bool
    patch_request: dict[str, Any]
    single_change_patch_result: dict[str, Any]
    patch_evaluation: dict[str, Any]
    execute_rollback: bool
    rollback_result: dict[str, Any]
    execute_post_rollback_verify: bool
    post_rollback_commands: list[str]
    post_rollback_verifier_result: dict[str, Any]
    propose_patch: bool
    patch_proposal: dict[str, Any]
    approval_decisions: dict[str, bool]
    bounded_loop: bool
    keep_going: bool
    keep_going_result: dict[str, Any]
    execute_change_set: bool
    change_set_request: dict[str, Any]
    atomic_change_set_result: dict[str, Any]
    loop_summary: dict[str, Any]
    resumed_from_checkpoint: str
    quality_score: int
    quality_status: str
    decision: Decision
    report_path: str
    brief_path: str
    recommended_next_action: str
    mode: str
    execution_authorized: bool
    side_effects_performed: list[str]
    resume_diagnostics: dict[str, Any]
    resume_package: dict[str, Any]
    parent_run_id: str
    errors: list[str]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _contains_any(text: str, terms: set[str]) -> bool:
    toks = _tokens(text)
    return bool(toks & terms)


def _new_run_id() -> str:
    return foundry.new_run_id()


def intake_objective(state: MobiusState) -> MobiusState:
    objective = (state.get("objective") or "").strip()
    if not objective:
        return {**state, "errors": ["objective is required"], "decision": "needs_interview"}
    return {
        **state,
        "objective": objective,
        "run_id": state.get("run_id") or _new_run_id(),
        "assumptions": list(state.get("assumptions") or []),
        "errors": list(state.get("errors") or []),
    }


def classify_goal(state: MobiusState) -> MobiusState:
    text = f"{state.get('objective','')} {state.get('context_hint') or ''}".lower()
    if _contains_any(text, CODE_TERMS):
        gt: GoalType = "code"
    elif _contains_any(text, RESEARCH_TERMS):
        gt = "research"
    elif _contains_any(text, WRITING_TERMS):
        gt = "writing"
    elif _contains_any(text, SYSTEM_TERMS):
        gt = "system_admin"
    elif _contains_any(text, OBSIDIAN_TERMS):
        gt = "obsidian_project"
    elif _contains_any(text, BUSINESS_TERMS):
        gt = "business_ops"
    else:
        gt = "unknown"
    return {**state, "goal_type": gt}


def define_goal_rubric(state: MobiusState) -> MobiusState:
    goal_type = state.get("goal_type", "unknown")
    profiles: dict[str, dict[str, Any]] = {
        "code": {
            "criteria": ["test_evidence", "runtime_smoke", "scope_control", "rollback_readiness"],
            "verifier_focus": "tests, compile checks, wrapper smoke, and artifact paths",
        },
        "research": {
            "criteria": ["source_grounding", "comparison_method", "uncertainty_labeling", "durable_artifact"],
            "verifier_focus": "sources, scoring transparency, assumptions, and saved report",
        },
        "writing": {
            "criteria": ["audience_fit", "tone_match", "claim_support", "human_readability"],
            "verifier_focus": "voice, concision, supported claims, and final saved draft",
        },
        "system_admin": {
            "criteria": ["pre_state_capture", "backup_or_checkpoint", "post_state_verification", "rollback_path"],
            "verifier_focus": "before/after command evidence and safe rollback notes",
        },
        "obsidian_project": {
            "criteria": ["vault_path_validity", "link_integrity", "para_placement", "read_back_verification"],
            "verifier_focus": "correct vault path, readable note, links/index updates, and no orphan artifacts",
        },
        "business_ops": {
            "criteria": ["business_outcome", "approval_boundary", "risk_separation", "next_action_clarity"],
            "verifier_focus": "draft-only boundaries, stakeholder risk, assumptions, and clear next step",
        },
        "unknown": {
            "criteria": ["clarified_context", "done_definition", "risk_boundary", "smallest_useful_artifact"],
            "verifier_focus": "interview questions and explicit assumptions before execution",
        },
    }
    selected = profiles.get(str(goal_type), profiles["unknown"])
    rubric = {
        "rubric_version": "mobius.goal_rubric.v2.0",
        "profile": goal_type,
        "criteria": selected["criteria"],
        "verifier_focus": selected["verifier_focus"],
        "minimum_score_to_keep": 80 if goal_type in {"code", "system_admin"} else 75,
        "human_review_required_when": [
            "risk_level is high",
            "approval boundary is encountered",
            "verifier evidence is missing",
        ],
    }
    return {**state, "goal_rubric": rubric}


def _scaffold_recommendation(context: ScaffoldContext) -> dict[str, str]:
    recs: dict[ScaffoldContext, dict[str, str]] = {
        "client_work": {
            "location": "work/private repo or approved workplace workspace",
            "stack": "existing workplace conventions",
            "testing": "unit tests plus a privacy review checklist",
            "why": "Work-context builds need policy boundaries and no unapproved public exposure.",
            "avoid": "Do not default to personal machine paths or a public repo.",
        },
        "public_repo": {
            "location": "a clean repo, not personal runtime paths",
            "stack": "portable package with README, license, examples, tests, and CI",
            "testing": "CI-friendly test suite",
            "why": "Public repos need clean boundaries, docs, and no private path leakage.",
            "avoid": "Do not include secrets or operator-specific paths.",
        },
        "throwaway_spike": {
            "location": "a clearly marked local spike directory",
            "stack": "a small script",
            "testing": "a smoke test",
            "why": "Spikes should prove the idea cheaply before overbuilding.",
            "avoid": "Do not add heavy frameworks until the idea survives a real run.",
        },
        "obsidian_only": {
            "location": "the vault or knowledge-base folder named in the objective",
            "stack": "Markdown, plus a wrapper script only if the job repeats",
            "testing": "read-back and link/path checks",
            "why": "If the output is a note, a durable Markdown file is enough.",
            "avoid": "Do not create an app when a note is the artifact.",
        },
        "internal": {
            "location": "a local project directory",
            "stack": "plain Python unless the job needs a state machine",
            "testing": "pytest plus one real smoke run",
            "why": "Internal tools benefit from local paths, a small wrapper, and fast iteration.",
            "avoid": "Do not start with a web UI unless the interface is the hard part.",
        },
        "unknown": {
            "location": "undecided",
            "stack": "undecided",
            "testing": "undecided",
            "why": "The objective lacks enough context to choose a scaffold confidently.",
            "avoid": "Do not execute until context and the output artifact are clear.",
        },
    }
    return recs[context]


def reason_about_scaffold(state: MobiusState) -> MobiusState:
    hint = re.sub(r"[\s-]+", "_", (state.get("context_hint") or "").strip().lower())
    text = f"{state.get('objective', '')} {state.get('context_hint') or ''}".lower()
    assumptions = list(state.get("assumptions") or [])
    explicit = {
        "internal": "internal",
        "client_work": "client_work",
        "client": "client_work",
        "public_repo": "public_repo",
        "public": "public_repo",
        "throwaway_spike": "throwaway_spike",
        "spike": "throwaway_spike",
        "obsidian_only": "obsidian_only",
        "obsidian": "obsidian_only",
    }

    if hint in explicit:
        context: ScaffoldContext = explicit[hint]  # type: ignore[assignment]
    elif "workplace" in text or "work-safe" in text or "enterprise" in text or "client_work" in text or "client work" in text:
        context = "client_work"
    elif ("public" in text and "no public" not in text) or "github" in text or ("repo" in text and "public" in text):
        context = "public_repo"
    elif "spike" in text or "prototype" in text or "experiment" in text:
        context = "throwaway_spike"
    elif "obsidian" in text or "vault" in text:
        context = "obsidian_only"
    elif "internal" in text or state.get("goal_type") in {"code", "system_admin", "research"}:
        context = "internal"
    else:
        context = "unknown"

    rec = _scaffold_recommendation(context)
    if hint in explicit:
        assumptions.append(f"Scaffold context taken from --context {hint}.")
    elif context != "unknown":
        assumptions.append(f"Scaffold context inferred as {context} unless you override it with --context.")
    return {**state, "scaffold_context": context, "scaffold_recommendation": rec, "assumptions": assumptions}


def build_working_spec(state: MobiusState) -> MobiusState:
    objective = state["objective"]
    goal_type = state.get("goal_type", "unknown")
    scaffold = state.get("scaffold_recommendation", {})
    spec = {
        "objective": objective,
        "goal_type": goal_type,
        "scaffold_context": state.get("scaffold_context", "unknown"),
        "recommended_location": scaffold.get("location"),
        "recommended_stack": scaffold.get("stack"),
        "scaffold_rationale": scaffold.get("why"),
        "goal_rubric": state.get("goal_rubric", {}),
        "non_goals": [
            "No public posting/contacting/paid service creation without explicit approval.",
            "No credential exposure or secret printing.",
            "No destructive file operations without backup and approval gate.",
        ],
        "expected_artifacts": [],
    }
    if state.get("mode") == "foundry_spec_only":
        spec["agent_foundry"] = {
            "status": "active_foundry_spec_only",
            "front_door": "raw_agent_idea_to_interviewed_agent_spec",
            "output_contract": "Agent Spec plus one advisory runtime recommendation; no build or execution",
        }
    if goal_type == "code":
        spec["expected_artifacts"] = ["source code", "tests", "wrapper or run command", "final run report"]
    elif goal_type == "research":
        spec["expected_artifacts"] = ["source-grounded findings", "comparison/scoring", "Obsidian/report artifact"]
    elif goal_type == "writing":
        spec["expected_artifacts"] = ["draft", "quality review", "saved document"]
    elif goal_type == "obsidian_project":
        spec["expected_artifacts"] = ["Markdown note/update", "link/index update", "read-back verification"]
    else:
        spec["expected_artifacts"] = ["clarified spec", "success criteria", "final report"]
    if spec.get("agent_foundry"):
        spec["expected_artifacts"] = list(dict.fromkeys([*spec.get("expected_artifacts", []), "Agent Spec", "interview questions", "build path decision", "registration plan"]))
    if state.get("enable_venture_loop"):
        spec["venture_loop"] = {
            "purpose": "Turn a raw product idea into business, GTM, MVP, validation, and Mobius execution handoff artifacts.",
            "mode": "extension_loop_option",
        }
    return {**state, "working_spec": spec}


def build_venture_loop(state: MobiusState) -> MobiusState:
    if not state.get("enable_venture_loop"):
        return {**state, "venture_loop": {"version": "mobius.venture_loop.v0.1", "status": "skipped", "reason": "enable_venture_loop not set"}}
    loop = {
        "version": "mobius.venture_loop.v0.1",
        "status": "ready_option",
        "positioning": "Domain extension loop that feeds better product/business objectives into Mobius v2.0's bounded execution control layer.",
        "artifact_sequence": [
            "idea_intake",
            "problem_customer_hypothesis",
            "market_scan_brief",
            "business_plan",
            "go_to_market_strategy",
            "mvp_spec",
            "validation_plan",
            "risk_and_assumption_register",
            "mobius_execution_handoff",
        ],
        "business_plan_sections": [
            "customer and painful job",
            "offer and wedge",
            "revenue model and pricing assumptions",
            "startup and monthly cost assumptions",
            "unit economics scenarios",
            "operating model",
            "risks requiring professional review",
        ],
        "gtm_sections": [
            "first narrow buyer",
            "wedge promise",
            "first 10 customers path",
            "channels and launch sequence",
            "landing-page messaging",
            "validation metric",
        ],
        "mvp_sections": [
            "v0 scope",
            "user stories",
            "manual concierge fallback",
            "build artifacts",
            "verification checklist",
        ],
        "approval_boundaries": [
            "no purchases or paid tools",
            "no public posting or prospect outreach",
            "no domain/entity/legal/tax actions",
            "no production deploy without explicit approval",
        ],
        "handoff_contract": {
            "to_mobius": "MVP spec, artifact list, approval decisions, verifier plan, and bounded next build step.",
            "from_mobius": "reports, checkpoints, run history, doctor health, and safe file-change execution.",
        },
    }
    return {**state, "venture_loop": loop}


def build_agent_foundry_contract(state: MobiusState) -> MobiusState:
    """Build the v2.5 spec-only Foundry intake after risk is known."""
    objective = state.get("objective", "")
    active = state.get("mode") == "foundry_spec_only"
    contract = foundry.contract("active" if active else "available", str(state.get("risk_level", "low")))
    if not active:
        return {
            **state,
            "agent_foundry_contract": contract,
            "foundry_intake": {"status": "not_applicable", "completeness": {"complete": False, "missing": []}},
            "approval_gates": [],
            "pending_approval_gates": [],
            "readiness": {name: {"status": "not_evaluated", "reason": "Not an agent-intake request."} for name in foundry.READINESS_DIMENSIONS},
            "runtime_recommendation": {"selected": None, "reasons": ["Not an agent-intake request."]},
        }

    intake = foundry.build_intake(objective, state.get("context_hint"), state.get("answers"))
    risk_assessment = state.get("risk_assessment") or foundry.assess_risk_sources(
        objective,
        state.get("context_hint"),
        state.get("answers"),
    )
    gates = foundry.build_approval_gates(
        risk_assessment,
        state.get("answers"),
        objective=objective,
        revision=1,
    )
    runtime = foundry.select_runtime(intake, risk_assessment, gates)
    readiness = foundry.evaluate_readiness(intake, risk_assessment, gates, runtime, state.get("answers"))
    pending = [gate for gate in gates if gate["status"] == "pending"]
    return {
        **state,
        "agent_foundry_contract": contract,
        "foundry_intake": intake,
        "answers": intake["answers"],
        "approval_gates": gates,
        "pending_approval_gates": pending,
        "readiness": readiness,
        "runtime_recommendation": runtime,
    }


def detect_risk_and_ambiguity(state: MobiusState) -> MobiusState:
    objective = state.get("objective", "")
    assessment = foundry.assess_risk_sources(
        objective,
        state.get("context_hint"),
        state.get("answers"),
    )
    risk: RiskLevel = assessment["level"]
    text = objective.lower()
    ambiguity = 0
    if state.get("goal_type") == "unknown":
        ambiguity += 3
    if state.get("scaffold_context") == "unknown":
        ambiguity += 3
    if len(text.split()) < 6:
        ambiguity += 2
    if any(word in text for word in ["better", "improve", "fix this", "make it work", "do something"]):
        ambiguity += 2
    if risk != "low":
        ambiguity += 1
    return {**state, "risk_level": risk, "risk_assessment": assessment, "ambiguity_score": ambiguity}


def generate_interview_if_needed(state: MobiusState) -> MobiusState:
    qs: list[str] = []
    intake = state.get("foundry_intake") or {}
    if intake.get("status") != "not_applicable":
        missing = list((intake.get("completeness") or {}).get("missing") or [])
        qs.extend(foundry.interview_questions_for_dimensions(missing))
        if missing:
            decision: Decision = "needs_interview"
        elif state.get("pending_approval_gates"):
            qs.extend(foundry.interview_questions_for_gates(state["pending_approval_gates"]))
            decision = "human_approval_required"
        elif any(gate["status"] in {"rejected", "expired"} for gate in state.get("approval_gates", [])):
            decision = "human_approval_required"
        else:
            decision = "spec_ready"
        return {**state, "interview_questions": qs, "decision": decision}

    risk = state.get("risk_level", "low")
    ambiguity = int(state.get("ambiguity_score", 0))
    scaffold = state.get("scaffold_context", "unknown")
    if scaffold == "unknown":
        qs.append("What context should this run in: internal, client/work, public repo, notes-only, or throwaway spike?")
    if ambiguity >= 4:
        qs.append("What artifact should count as done: code/app, CLI, report, Obsidian note, PR, or something else?")
        qs.append("What is the smallest useful version you would accept for v0?")
    if risk in {"medium", "high"}:
        qs.append("Should Mobius operate draft-only, or is it allowed to make local changes after backups?")
    if risk == "high":
        qs.append("Confirm the approval boundary for risky actions: public posting, third-party sends, purchases/trades, deletions, credentials, or production changes.")
    decision = "human_approval_required" if risk == "high" else ("needs_interview" if qs else "spec_ready")
    return {**state, "interview_questions": qs, "decision": decision}


def define_success_criteria(state: MobiusState) -> MobiusState:
    goal_type = state.get("goal_type", "unknown")
    criteria = ["A working spec exists with objective, scaffold, assumptions, risks, and non-goals."]
    verifier = ["Read back generated report and confirm required sections exist."]

    if goal_type == "code":
        criteria += [
            "Implementation has tests or a documented smoke check.",
            "A real command/run verifies the artifact, not just a written plan.",
            "Final summary includes changed paths and command output evidence.",
        ]
        verifier += ["Run pytest or project test command.", "Run the wrapper/app once with representative input."]
    elif goal_type == "research":
        criteria += [
            "Claims are source-grounded or explicitly marked as assumptions.",
            "Comparison/scoring method is visible.",
            "Output is saved to the appropriate durable artifact location.",
        ]
        verifier += ["Check citations/source list.", "Review scoring against the objective."]
    elif goal_type == "writing":
        criteria += ["Draft matches requested voice/audience.", "AI-isms and unsupported claims are reduced."]
        verifier += ["Run quality review against audience and tone rubric."]
    elif goal_type == "system_admin":
        criteria += ["Backups/checkpoints exist before edits.", "Service/config state is verified after changes."]
        verifier += ["Run status/health command before and after."]

    return {**state, "success_criteria": criteria, "verifier_plan": verifier}


def design_budget_policy(state: MobiusState) -> MobiusState:
    """Create explicit cost/runaway controls before any worker loop exists.

    Metered or capped execution backends may apply; Mobius treats every loop as budgeted by default.
    """
    text = state.get("objective", "").lower()
    risk_reasons: list[str] = []
    if any(term in text for term in ["forever", "never-ending", "never ending", "continuous", "keep improving", "indefinitely"]):
        risk_reasons.append("Objective implies forever/continuous looping; require bounded budget review.")
    if state.get("risk_level") != "low":
        risk_reasons.append(f"Risk level is {state.get('risk_level')}; budget and approval gates should be stricter.")
    if state.get("ambiguity_score", 0) >= 4:
        risk_reasons.append("Ambiguous objectives can burn tokens while searching for a spec; interview first.")

    policy = {
        "estimated_cost_mode": "oauth_capped",
        "api_metered_ready": True,
        "max_iterations": 3,
        "max_worker_runs": 3,
        "max_reviewer_runs": 3,
        "max_minutes": 45,
        "max_consecutive_failures": 2,
        "require_progress_delta_each_iteration": True,
        "requires_budget_review": bool(risk_reasons),
        "risk_reasons": risk_reasons,
        "future_api_controls": {
            "max_input_tokens_per_run": 120000,
            "max_output_tokens_per_run": 12000,
            "max_estimated_usd_per_goal": 5.00,
            "hard_stop_on_missing_usage": True,
            "warn_at_budget_percent": 80,
        },
        "runaway_stop_conditions": [
            "no measurable progress after one iteration",
            "same failure repeats twice",
            "worker asks for broader scope than approved",
            "usage/cost telemetry missing on API-backed run",
            "estimated budget reaches warning threshold",
            "human approval boundary encountered",
        ],
    }
    if risk_reasons and state.get("decision") in {"ready_to_execute", "spec_ready"} and (state.get("foundry_intake") or {}).get("status") == "not_applicable":
        existing_questions = list(state.get("interview_questions") or [])
        existing_questions.append("This objective may create token/cost runaway risk. Confirm the budget cap, max iterations, and whether API-metered execution is allowed.")
        return {**state, "budget_policy": policy, "decision": "needs_interview", "interview_questions": existing_questions}
    return {**state, "budget_policy": policy}


def design_execution_loop(state: MobiusState) -> MobiusState:
    budget = state.get("budget_policy", {})
    loop = {
        "max_iterations": budget.get("max_iterations", 3),
        "max_minutes": budget.get("max_minutes", 45),
        "max_worker_runs": budget.get("max_worker_runs", 3),
        "worker_mode": "Mobius CLI run or spawned local worker depending on task size",
        "iteration_steps": [
            "select next concrete task from spec",
            "execute bounded work",
            "run verifier plan",
            "measure progress delta and usage",
            "score progress",
            "continue, revise, ask, or stop",
        ],
        "stop_rules": [
            "success criteria satisfied",
            "three failed attempts without new information",
            "two consecutive failures with the same root cause",
            "no measurable progress delta after an iteration",
            "token/cost budget threshold reached",
            "usage telemetry missing during API-metered run",
            "risk boundary encountered",
            "required user decision missing",
        ],
        "approval_required_for": [
            "public posting or third-party sends",
            "purchases, trades, or paid service creation",
            "credential changes or secret handling",
            "destructive deletes or production changes",
            "raising token/cost/time limits beyond the generated budget policy",
        ],
    }
    return {**state, "execution_loop": loop}


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json_value(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_json_value(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)



def apply_goal_rubric_score(state: MobiusState) -> MobiusState:
    rubric = state.get("goal_rubric") or {}
    criteria = list(rubric.get("criteria") or [])
    goal_type = state.get("goal_type", "unknown")
    score = 100
    reasons: list[str] = []
    if state.get("decision") == "human_approval_required":
        score -= 20
        reasons.append("Human approval boundary is active.")
    if state.get("risk_level") == "high":
        score -= 10
        reasons.append("High-risk objective reduces autonomous readiness.")
    if state.get("ambiguity_score", 0) >= 4:
        score -= 15
        reasons.append("Ambiguity requires more clarification before execution.")
    if not criteria:
        score -= 25
        reasons.append("No rubric criteria available.")
    if not reasons:
        reasons.append(f"{goal_type} rubric criteria are present and objective is within bounded local scope.")
    result = {
        "rubric_version": "mobius.rubric_score.v2.0",
        "profile": goal_type,
        "criteria_checked": criteria,
        "score": max(score, 0),
        "passed": score >= int(rubric.get("minimum_score_to_keep", 75)),
        "reasons": reasons,
    }
    return {**state, "rubric_score": result}


def build_approval_packet(state: MobiusState) -> MobiusState:
    required: list[str] = []
    if state.get("execute_patch") or state.get("propose_patch"):
        required.append("patch")
    if state.get("execute_change_set"):
        required.append("change_set")
    if state.get("execute_rollback"):
        required.append("rollback")
    if state.get("decision") == "human_approval_required":
        required.append("human")
    seen: list[str] = []
    for item in required:
        if item not in seen:
            seen.append(item)
    approvals = state.get("approval_decisions") or {}
    packet = {
        "version": "mobius.approval_packet.v2.0",
        "required_approvals": seen,
        "granted": {key: bool(approvals.get(key)) for key in seen},
        "missing": [key for key in seen if not approvals.get(key) and key != "human"],
        "human_required": "human" in seen,
    }
    return {**state, "approval_packet": packet}


def define_product_contract(state: MobiusState) -> MobiusState:
    contract = {
        "product_version": RELEASE_VERSION,
        "stability": "stable",
        "stable_workflows": [
            "spec_to_report",
            "foundry_intake",
            "checkpoint_resume",
            "doctor_health_check",
            "run_history",
            "operator_brief",
            "bounded_local_verification",
        ],
        "non_goals": [
            "arbitrary_shell",
            "unapproved_public_or_third_party_actions",
            "credential_handling",
            "production_changes_without_explicit_scope",
            "forever_loops",
            "build_or_activate_agents_by_default",
        ],
        "operating_contract": "Use as a pre-agent constitution: spec, interview, and bounded local verification before any build work.",
    }
    rubric_score = state.get("rubric_score") or {}
    product_status = {
        "status": "ready" if rubric_score.get("passed", False) and state.get("decision") != "needs_interview" else "needs_review",
        "reason": "v1 core loop: spec, Foundry intake, checkpointing, history, operator brief, and doctor are available.",
    }
    return {**state, "product_contract": contract, "product_status": product_status}


def _artifact_mode_from_objective(objective: str) -> str:
    text = objective.lower()
    if "interview" in text and any(term in text for term in ["artifact", "playbook", "html", "markdown", "document"]):
        return "interview_to_artifact"
    if any(term in text for term in ["html", "markdown", "playbook", "artifact", "deck", "report"]):
        return "artifact_delivery"
    return "bounded_spec"


def _artifact_class_from_objective(objective: str) -> str:
    text = objective.lower()
    if any(term in text for term in ["launch package", "launch system", "field lab", "validation tracker"]):
        return "launch_package"
    if "governance packet" in text or "private governance" in text:
        return "governance_packet"
    if any(term in text for term in ["playbook", "operating playbook"]):
        return "operating_playbook"
    if any(term in text for term in ["html dashboard", "dashboard"]):
        return "dashboard"
    if any(term in text for term in ["code", "repo", "implement", "test"]):
        return "code_change"
    if any(term in text for term in ["research", "analyze", "compare", "synthesis"]):
        return "research_synthesis"
    return "bounded_spec"


def route_artifact(state: MobiusState) -> MobiusState:
    objective = state.get("objective", "")
    text = objective.lower()
    artifact_class = _artifact_class_from_objective(objective)
    shareability = "private_internal" if any(term in text for term in ["private", "internal", "governance", "approval gate"]) else "reviewable_internal"
    if any(term in text for term in ["public", "shareable", "client-facing", "parent one-pager", "sponsor package"]):
        shareability = "mixed_private_and_shareable"
    outputs = ["json_spec", "checkpoint", "markdown_report"]
    if any(term in text for term in ["html", "dashboard"]):
        outputs.append("html_dashboard")
    if any(term in text for term in ["markdown", "command center", "note"]):
        outputs.append("markdown_artifact")
    if any(term in text for term in ["governance", "decision ledger", "constraint ledger"]):
        outputs.append("private_governance_packet")
    if "validation tracker" in text:
        outputs.append("validation_tracker")
    checks = ["artifact_paths_written", "json_spec_written", "checkpoint_written", "markdown_report_written"]
    if "html_dashboard" in outputs:
        checks.append("html_parse_or_browser_check")
    if any(term in text for term in ["approval", "outreach", "public", "sponsor"]):
        checks.append("approval_gate")
    if shareability in {"private_internal", "mixed_private_and_shareable"}:
        checks.append("shareability_boundary_review")
    router = {
        "version": "mobius.artifact_router.v2.2",
        "artifact_class": artifact_class,
        "shareability": shareability,
        "destination_policy": {
            "scratch": ".mobius/",
            "durable": "project_or_vault_destination_selected_by_scaffold_context",
            "shareable": "explicitly_marked_shareable_only",
            "private": "private_governance_or_internal_packet",
        },
        "required_outputs": list(dict.fromkeys(outputs)),
        "verification_checks": list(dict.fromkeys(checks)),
    }
    return {**state, "artifact_router": router}


def build_method_basis_ledger(state: MobiusState) -> MobiusState:
    goal_type = state.get("goal_type", "unknown")
    context = state.get("scaffold_context", "unknown")
    objective = state.get("objective", "").lower()
    skills = ["notes-first-reasoning"] if context in {"obsidian_only", "internal", "client_work"} else []
    if goal_type == "business_ops" or any(term in objective for term in ["launch", "sponsor", "business", "validation"]):
        skills.append("business-idea-validation")
    if goal_type == "code" or any(term in objective for term in ["repo", "implement", "test", "push"]):
        skills.append("test-driven-development")
    if "dashboard" in objective or "html" in objective:
        skills.append("claude-design")
    ledger = {
        "version": "mobius.method_basis_ledger.v2.2",
        "recommended_skills": list(dict.fromkeys(skills)),
        "source_hierarchy": [
            "obsidian_project_notes",
            "local_repo_or_files",
            "live_tool_state",
            "web_sources",
            "user_interview_answers",
        ],
        "method_assumptions": [
            "Load relevant methods before producing durable artifacts.",
            "Prefer existing project context before generic generation.",
            "Record excluded methods when a tempting but wrong workflow is avoided.",
        ],
        "governing_context": context,
    }
    return {**state, "method_basis_ledger": ledger}


def build_sectioned_artifact_pipeline(state: MobiusState) -> MobiusState:
    router = state.get("artifact_router", {})
    artifact_class = router.get("artifact_class", "bounded_spec")
    enabled = artifact_class in {"launch_package", "governance_packet", "operating_playbook", "dashboard", "research_synthesis"}
    phases = [
        "outline_contract",
        "section_generation",
        "coherence_review",
        "constraint_review",
        "final_render",
        "verification_report",
    ] if enabled else ["single_spec_generation", "verification_report"]
    pipeline = {
        "version": "mobius.sectioned_artifact_pipeline.v2.2",
        "enabled": enabled,
        "phases": phases,
        "completion_rule": "Long artifacts must pass coherence and constraint review before final render.",
        "review_focus": [
            "audience_fit",
            "missing_sections",
            "private_vs_shareable_boundary",
            "approval_gates",
            "artifact_paths",
        ],
    }
    return {**state, "sectioned_artifact_pipeline": pipeline}


def build_state_key_schema(state: MobiusState) -> MobiusState:
    run_id = state.get("run_id") or _new_run_id()
    objective = state.get("objective", "").lower()
    project = "example" if any(term in objective for term in ["launch", "example-project"]) else "mobius"
    keys = [
        f"run:{run_id}:objective",
        f"run:{run_id}:artifact_router",
        f"run:{run_id}:method_basis",
        f"run:{run_id}:interview_state",
        f"run:{run_id}:decision_ledger",
        f"run:{run_id}:constraint_ledger",
        f"run:{run_id}:artifact_contract",
        f"run:{run_id}:verification_report",
    ]
    project_keys = [
        f"project:{project}:active_goals",
        f"project:{project}:latest_dashboard",
        f"project:{project}:latest_validation_tracker",
    ]
    schema = {
        "version": "mobius.state_key_schema.v2.2",
        "key_style": "hierarchical colon-delimited keys",
        "keys": keys,
        "project_keys": project_keys,
        "durability_rule": "Run state must be reconstructable from JSON spec, checkpoint, and project artifacts.",
    }
    return {**state, "state_key_schema": schema}


def build_interactive_dashboard_contract(state: MobiusState) -> MobiusState:
    router = state.get("artifact_router", {})
    outputs = router.get("required_outputs", [])
    objective = state.get("objective", "").lower()
    enabled = "html_dashboard" in outputs or "dashboard" in objective
    panels = ["run_summary", "decision_ledger", "constraint_ledger", "verification_status"]
    if any(term in objective for term in ["launch", "validation", "example-project"]):
        panels += ["launch_readiness", "validation_signals", "approval_gates"]
    contract = {
        "version": "mobius.interactive_dashboard_contract.v2.2",
        "enabled": enabled,
        "panels": list(dict.fromkeys(panels)),
        "interaction_model": "static_local_first_with_future_script_backed_updates",
        "no_browser_storage_rule": "Do not rely on browser localStorage/sessionStorage for durable state; persist via files or explicit backend scripts.",
    }
    return {**state, "interactive_dashboard_contract": contract}


def build_deep_agent_harness_contract(state: MobiusState) -> MobiusState:
    """Adapt Deep Agents/Claude-Code-style harness principles into Mobius.

    This is not a dependency on deepagents. It records the transferable operating
    ideas: explicit plan tool, isolated subagents, filesystem-backed context,
    human interrupts, and bounded context compaction.
    """
    goal_type = state.get("goal_type", "unknown")
    risk_level = state.get("risk_level", "low")
    objective = state.get("objective", "").lower()
    contract = {
        "version": "mobius.deep_agent_harness.v2.3",
        "inspiration_source": "langchain-ai/deepagents commit 6a37792 plus official LangChain Deep Agents docs",
        "adopted_principles": [
            "opinionated defaults for long-horizon work",
            "explicit planning/todo state before tool execution",
            "specialized subagents with isolated context windows",
            "filesystem-backed scratch/artifact memory instead of transcript-only memory",
            "human-in-the-loop interrupts for sensitive tools",
            "context compaction before large tool output floods the control loop",
            "tool/sandbox boundaries enforce safety; prompts only describe intent",
        ],
        "mobius_interpretation": "Mobius remains the deterministic control layer; Deep-Agents-style workers are optional execution specialists under Mobius gates.",
        "when_to_use_deep_agent_worker": goal_type in {"code", "research", "writing", "business_ops"} and risk_level != "high",
        "never_delegate_silently": [
            "public posting or outreach",
            "purchases, trades, payments, or account changes",
            "credential handling",
            "broad deletion or production changes",
        ],
        "fit_notes": [
            "Use LangGraph directly when Mobius needs custom graph control.",
            "Use a Deep-Agents-style harness when the inner worker needs planning, files, skills, and subagent delegation.",
            "Pass compiled LangGraph agents into the worker layer only after contract tests exist.",
        ],
        "objective_signals": [term for term in ["repo", "research", "dashboard", "launch", "artifact", "code", "playbook"] if term in objective],
    }
    return {**state, "deep_agent_harness_contract": contract}


def build_subagent_delegation_matrix(state: MobiusState) -> MobiusState:
    goal_type = state.get("goal_type", "unknown")
    risk_level = state.get("risk_level", "low")
    base_roles = [
        {
            "name": "researcher",
            "description": "Collect source/context evidence and return only distilled findings with paths/URLs.",
            "tools": "read/search/web only by default",
            "approval": "no external side effects",
        },
        {
            "name": "builder",
            "description": "Make bounded local changes from an approved spec or change set.",
            "tools": "app-root file edits plus allowlisted verifier commands",
            "approval": "requires approved patch/change_set for writes",
        },
        {
            "name": "reviewer",
            "description": "Grade the result against the rubric and list gaps before Mobius reports done.",
            "tools": "read/test evidence; no writes",
            "approval": "read-only",
        },
    ]
    if goal_type in {"writing", "business_ops", "obsidian_project"}:
        base_roles.append({
            "name": "artifact_writer",
            "description": "Turn ledgers and outline contracts into sectioned Markdown/HTML artifacts.",
            "tools": "draft artifacts under the selected project folder",
            "approval": "shareable/external outputs require human review",
        })
    matrix = {
        "version": "mobius.subagent_delegation_matrix.v2.3",
        "delegation_rule": "Delegate only work that would bloat Mobius context or benefits from a specialist role; parent sees final summary plus artifact paths.",
        "default_roles": base_roles,
        "state_pass_through": ["objective", "working_spec", "goal_rubric", "artifact_router", "constraint_ledger", "verification_contract"],
        "state_excluded_from_child_return": ["raw_tool_output", "credentials", "full_transcript", "unverified_intermediate_notes"],
        "parallelism_policy": "researcher and reviewer may run independently; builder waits for approval packet and preflight.",
        "high_risk_override": "If risk_level is high, subagents may draft plans/reviews only; execution remains blocked until explicit approval.",
        "recommended_now": risk_level != "high" and goal_type in {"code", "research", "writing", "business_ops", "obsidian_project"},
    }
    return {**state, "subagent_delegation_matrix": matrix}


def build_context_filesystem_policy(state: MobiusState) -> MobiusState:
    run_id = state.get("run_id") or _new_run_id()
    context = state.get("scaffold_context", "unknown")
    policy = {
        "version": "mobius.context_filesystem_policy.v2.3",
        "principle": "Use files as the long-horizon working memory; keep the chat/control state small and auditable.",
        "scratch_root": f".mobius/runs/{run_id}/scratch/",
        "artifact_root": "project_or_vault_destination_selected_by_artifact_router",
        "memory_scopes": {
            "run_scoped": ["scratch notes", "raw research extracts", "temporary outlines"],
            "project_scoped": ["decision ledgers", "constraint ledgers", "accepted specs", "verification reports"],
            "user_profile": ["stable preferences only; never transient run progress"],
        },
        "backend_boundary": "virtual/app-root by default; host filesystem and shell are opt-in and allowlisted.",
        "context_source_order": (state.get("method_basis_ledger") or {}).get("source_hierarchy", []),
        "sensitive_data_rule": "Never persist API keys, tokens, credentials, or private customer data in memory/skills/artifacts.",
        "governing_context": context,
    }
    return {**state, "context_filesystem_policy": policy}


def build_human_interrupt_policy(state: MobiusState) -> MobiusState:
    risk = state.get("risk_level", "low")
    policy = {
        "version": "mobius.human_interrupt_policy.v2.3",
        "decision_types": ["approve", "edit", "reject"],
        "respond_rule": "Use respond only when the human is answering a question; never use it to deny a side-effecting tool as if the tool succeeded.",
        "interrupt_on": {
            "delete_or_remove": {"allowed_decisions": ["approve", "edit", "reject"], "default": "reject"},
            "external_send_post_publish_outreach": {"allowed_decisions": ["approve", "reject"], "default": "reject"},
            "purchase_trade_payment_account_change": {"allowed_decisions": ["approve", "reject"], "default": "reject"},
            "credential_or_secret_access": {"allowed_decisions": ["reject"], "default": "reject"},
            "local_write_patch": {"allowed_decisions": ["approve", "edit", "reject"], "default": "requires_preflight"},
            "read_only_research": {"allowed_decisions": [], "default": "auto_allowed"},
        },
        "checkpointer_required": True,
        "current_run_gate": "human_approval_required" if risk == "high" else "normal_mobius_approval_packet",
    }
    return {**state, "human_interrupt_policy": policy}


def build_context_compaction_policy(state: MobiusState) -> MobiusState:
    policy = {
        "version": "mobius.context_compaction_policy.v2.3",
        "trigger_conditions": [
            "tool output exceeds reportable summary size",
            "more than one specialist worker produces intermediate artifacts",
            "run spans multiple checkpoints or sessions",
            "raw source material would obscure the decision ledger",
        ],
        "retention_shape": {
            "keep_in_state": ["final finding", "artifact path", "score", "decision", "open question"],
            "write_to_files": ["raw extracts", "full test output", "long source notes", "draft variants"],
            "discard_or_archive": ["duplicate failed attempts", "irrelevant search results", "unselected drafts after decision is recorded"],
        },
        "summary_contract": "Every compaction must preserve source path/URL, confidence, reason, and next action.",
        "quality_gate": "Reviewer must be able to reconstruct why Mobius made the recommendation from compacted artifacts.",
    }
    return {**state, "context_compaction_policy": policy}


def build_artifact_contract(state: MobiusState) -> MobiusState:
    """Declare the durable outputs a Mobius run must leave behind.

    This makes Mobius different from a single prompt: the run records a machine-readable
    output contract before it writes specs/checkpoints/reports.
    """
    objective = state.get("objective", "")
    text = objective.lower()
    mode = _artifact_mode_from_objective(objective)
    outputs = ["markdown_report", "json_spec", "checkpoint", "run_history"]
    if "html" in text:
        outputs.append("html")
    if "markdown" in text or "playbook" in text or "document" in text:
        outputs.append("markdown")
    if "decision ledger" in text or mode == "interview_to_artifact":
        outputs.append("decision_ledger")
    if "constraint" in text or mode == "interview_to_artifact":
        outputs.append("constraint_ledger")
    contract = {
        "version": "mobius.artifact_contract.v2.1",
        "mode": mode,
        "required_outputs": list(dict.fromkeys(outputs)),
        "artifact_governance": [
            "capture interview state before final artifact generation",
            "record decisions, assumptions, and constraints in machine-readable form",
            "define verification checks before reporting completion",
            "persist ledgers to JSON spec, checkpoint, and Markdown report",
        ],
        "completion_rule": "Do not call an artifact run complete until required outputs are written and verification checks are recorded.",
    }
    return {**state, "artifact_contract": contract}


def build_decision_ledger(state: MobiusState) -> MobiusState:
    spec = state.get("working_spec", {})
    contract = state.get("artifact_contract", {})
    entries = [
        {
            "decision": f"Use {contract.get('mode', 'bounded_spec')} as the primary artifact mode.",
            "reason": "The objective determines whether Mobius should create a simple spec or a governed artifact package.",
        },
        {
            "decision": f"Treat {state.get('goal_type', 'unknown')} as the goal profile.",
            "reason": "The goal profile selects success criteria, verifier focus, and quality rubric.",
        },
        {
            "decision": f"Use {state.get('scaffold_context', 'unknown')} as the scaffold context.",
            "reason": "Context controls location, risk posture, and how much approval is required before execution.",
        },
        {
            "decision": "Persist JSON spec, checkpoint, run history, and Markdown report for auditability.",
            "reason": "A prompt transcript is not enough; Mobius needs durable run evidence and resume artifacts.",
        },
    ]
    if spec.get("expected_artifacts"):
        entries.append({
            "decision": "Use the working spec expected artifacts as the output backbone.",
            "reason": ", ".join(spec.get("expected_artifacts", [])),
        })
    ledger = {
        "version": "mobius.decision_ledger.v2.1",
        "entries": entries,
        "open_decisions": state.get("interview_questions", []),
    }
    return {**state, "decision_ledger": ledger}


def build_constraint_ledger(state: MobiusState) -> MobiusState:
    objective = state.get("objective", "")
    text = objective.lower()
    forbidden_terms = []
    if "forbidden project names" in text:
        forbidden_terms = ["ExampleBrand", "InternalCodename", "ClientProject"]
    constraints = list((state.get("working_spec") or {}).get("non_goals", []))
    constraints += [
        "Respect the scaffold context and audience boundaries.",
        "Keep risky actions draft-only unless explicitly approved.",
        "Record assumptions rather than silently inventing missing context.",
    ]
    if forbidden_terms:
        constraints.append("Run a forbidden-term scan before marking the artifact safe to share.")
    ledger = {
        "version": "mobius.constraint_ledger.v2.1",
        "constraints": list(dict.fromkeys(constraints)),
        "forbidden_terms": forbidden_terms,
        "approval_boundaries": (state.get("approval_packet") or {}).get("required_approvals", []),
        "risk_level": state.get("risk_level"),
    }
    return {**state, "constraint_ledger": ledger}


def build_verification_contract(state: MobiusState) -> MobiusState:
    artifact_contract = state.get("artifact_contract", {})
    required = [
        "json_spec_written",
        "checkpoint_written",
        "markdown_report_written",
        "required_sections_present",
    ]
    outputs = artifact_contract.get("required_outputs", [])
    if "html" in outputs:
        required.append("html_parse_or_browser_check")
    if (state.get("constraint_ledger") or {}).get("forbidden_terms"):
        required.append("forbidden_term_scan")
    if state.get("verifier_plan"):
        required.append("domain_verifier_plan_review")
    contract = {
        "version": "mobius.verification_contract.v2.1",
        "required_checks": list(dict.fromkeys(required)),
        "evidence_to_record": [
            "artifact paths",
            "test or smoke command output",
            "constraint scan result",
            "human review gates when required",
        ],
        "completion_rule": "Final response must cite real written artifacts and verification evidence.",
    }
    return {**state, "verification_contract": contract}


def finalize_foundry_spec(state: MobiusState) -> MobiusState:
    """Write standalone Agent Specs only after all intake dimensions resolve."""
    intake = state.get("foundry_intake") or {}
    if intake.get("status") == "not_applicable" or not (intake.get("completeness") or {}).get("complete"):
        return {**state, "agent_spec": {}}
    spec = foundry.build_agent_spec(
        run_id=str(state.get("run_id") or _new_run_id()),
        objective=str(state.get("objective") or ""),
        context=state.get("context_hint"),
        intake=intake,
        risk=state.get("risk_assessment") or {},
        gates=state.get("approval_gates") or [],
        readiness=state.get("readiness") or {},
        runtime=state.get("runtime_recommendation") or {},
    )
    json_path, markdown_path = foundry.write_agent_spec(spec, _effective_agent_spec_dir(), APP_DIR)
    return {
        **state,
        "agent_spec": spec,
        "agent_spec_json_path": json_path,
        "agent_spec_markdown_path": markdown_path,
    }


def export_json_spec(state: MobiusState) -> MobiusState:
    root = foundry.ensure_artifact_root(DEFAULT_SPEC_DIR, APP_DIR)
    run_id = foundry.validate_run_id(str(state.get("run_id") or _new_run_id()))
    path = root / f"{run_id}_mobius_spec.json"
    payload = {
        "schema_version": "mobius.spec.v1.0",
        "product_version": RELEASE_VERSION,
        "run_id": run_id,
        "objective": state.get("objective"),
        "context_hint": state.get("context_hint"),
        "answers": state.get("answers", {}),
        "mode": state.get("mode"),
        "execution_authorized": state.get("execution_authorized", False),
        "side_effects_performed": state.get("side_effects_performed", []),
        "parent_run_id": state.get("parent_run_id"),
        "resume_diagnostics": state.get("resume_diagnostics", {}),
        "decision": state.get("decision"),
        "goal_type": state.get("goal_type"),
        "goal_rubric": state.get("goal_rubric", {}),
        "rubric_score": state.get("rubric_score", {}),
        "approval_packet": state.get("approval_packet", {}),
        "agent_foundry_contract": state.get("agent_foundry_contract", {}),
        "foundry_intake": state.get("foundry_intake", {}),
        "risk_assessment": state.get("risk_assessment", {}),
        "approval_gates": state.get("approval_gates", []),
        "pending_approval_gates": state.get("pending_approval_gates", []),
        "readiness": state.get("readiness", {}),
        "runtime_recommendation": state.get("runtime_recommendation", {}),
        "agent_spec": state.get("agent_spec", {}),
        "agent_spec_paths": {
            "json": state.get("agent_spec_json_path"),
            "markdown": state.get("agent_spec_markdown_path"),
        },
        "scaffold_context": state.get("scaffold_context"),
        "working_spec": state.get("working_spec", {}),
        "success_criteria": state.get("success_criteria", []),
        "verifier_plan": state.get("verifier_plan", []),
        "budget_policy": state.get("budget_policy", {}),
        "execution_loop": state.get("execution_loop", {}),
        "interview_questions": state.get("interview_questions", []),
        "safety_boundary": (state.get("working_spec") or {}).get("non_goals", []),
    }
    foundry.atomic_write_new(path, json.dumps(_safe_json_value(payload), indent=2))
    return {**state, "json_spec_path": str(path)}


def apply_single_change_patch(file_path: str, old_string: str, new_string: str, description: str = "", allowed_root: Path | None = None) -> dict[str, Any]:
    target = Path(file_path).resolve()
    root = (allowed_root or APP_DIR).resolve()
    if not _is_inside_patch_root(target, root):
        return {"status": "blocked", "reason": "patch target outside approved patch root", "file_path": str(target)}
    if not target.exists() or not target.is_file():
        return {"status": "blocked", "reason": "patch target must be an existing file", "file_path": str(target)}
    if not old_string:
        return {"status": "blocked", "reason": "old_string is required"}
    text = target.read_text()
    count = text.count(old_string)
    if count != 1:
        return {"status": "blocked", "reason": f"old_string must appear exactly once; found {count}", "replacement_count": count}
    backup_path = target.with_name(f"{target.name}.backup_{_new_run_id()}")
    backup_path.write_text(text)
    target.write_text(text.replace(old_string, new_string, 1))
    return {
        "status": "pass",
        "file_path": str(target),
        "backup_path": str(backup_path),
        "replacement_count": 1,
        "description": description,
    }


def _preflight_change(change: dict[str, Any], allowed_root: Path | None = None) -> dict[str, Any]:
    target = Path(str(change.get("file_path", ""))).resolve()
    root = (allowed_root or APP_DIR).resolve()
    old_string = str(change.get("old_string", ""))
    if not _is_inside_patch_root(target, root):
        return {"status": "blocked", "reason": "change target outside approved patch root", "file_path": str(target)}
    if not target.exists() or not target.is_file():
        return {"status": "blocked", "reason": "change target must be an existing file", "file_path": str(target)}
    if not old_string:
        return {"status": "blocked", "reason": "old_string is required", "file_path": str(target)}
    text = target.read_text()
    count = text.count(old_string)
    if count != 1:
        return {"status": "blocked", "reason": f"old_string must appear exactly once; found {count}", "replacement_count": count, "file_path": str(target)}
    return {"status": "ready", "file_path": str(target), "text": text}


def apply_atomic_change_set(changes: list[dict[str, Any]], description: str = "", allowed_root: Path | None = None) -> dict[str, Any]:
    if not changes:
        return {"status": "blocked", "reason": "at least one change is required"}
    if len(changes) > 5:
        return {"status": "blocked", "reason": "change set exceeds max 5 files", "change_count": len(changes)}
    preflight = [_preflight_change(change, allowed_root=allowed_root) for change in changes]
    blocked = [item for item in preflight if item.get("status") != "ready"]
    if blocked:
        return {"status": "blocked", "reason": "change set preflight failed", "failures": blocked, "change_count": len(changes)}
    targets = [item["file_path"] for item in preflight]
    if len(set(targets)) != len(targets):
        return {"status": "blocked", "reason": "change set targets must be unique", "change_count": len(changes)}
    run_id = _new_run_id()
    backups: list[dict[str, str]] = []
    try:
        for change, ready in zip(changes, preflight):
            target = Path(str(ready["file_path"]))
            text = str(ready["text"])
            backup_path = target.with_name(f"{target.name}.backup_{run_id}")
            backup_path.write_text(text)
            backups.append({"file_path": str(target), "backup_path": str(backup_path)})
        for change, ready in zip(changes, preflight):
            target = Path(str(ready["file_path"]))
            text = str(ready["text"])
            target.write_text(text.replace(str(change["old_string"]), str(change["new_string"]), 1))
    except Exception as exc:
        for item in backups:
            target = Path(item["file_path"])
            backup = Path(item["backup_path"])
            if backup.exists():
                target.write_text(backup.read_text())
        return {"status": "rolled_back", "reason": f"change set apply failed: {exc}", "backups": backups, "change_count": len(changes)}
    return {"status": "pass", "description": description, "change_count": len(changes), "backups": backups}


def _record_side_effect(state: MobiusState, label: str) -> list[str]:
    effects = list(state.get("side_effects_performed") or [])
    if label not in effects:
        effects.append(label)
    return effects



def build_patch_proposal(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        return {**state, "patch_proposal": {"status": "blocked", "reason": "Foundry mode is spec-only"}}
    if not state.get("propose_patch"):
        return {**state, "patch_proposal": {"status": "skipped", "reason": "propose_patch not enabled"}}
    preflight = _self_patch_preflight(state)
    if preflight is not None:
        return {**state, "patch_proposal": preflight}
    request = state.get("patch_request") or {}
    required = ["file_path", "old_string", "new_string"]
    missing = [key for key in required if key not in request]
    if missing:
        return {**state, "patch_proposal": {"status": "blocked", "reason": f"missing patch_request keys: {', '.join(missing)}"}}
    target = Path(str(request["file_path"])).resolve()
    root = _patch_allowed_root(state)
    if not _is_inside_patch_root(target, root):
        return {**state, "patch_proposal": {"status": "blocked", "reason": "proposal target outside approved patch root", "file_path": str(target)}}
    return {**state, "patch_proposal": {
        "status": "proposed",
        "file_path": str(target),
        "old_string": str(request["old_string"]),
        "new_string": str(request["new_string"]),
        "description": str(request.get("description", "")),
        "requires_approval": True,
    }}


def apply_approved_patch(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        return {**state, "single_change_patch_result": {"status": "blocked", "reason": "Foundry mode is spec-only"}}
    if not state.get("execute_patch"):
        return {**state, "single_change_patch_result": {"status": "skipped", "reason": "execute_patch not enabled"}}
    approvals = state.get("approval_decisions") or {}
    if state.get("propose_patch") and approvals.get("patch") is not True:
        return {**state, "single_change_patch_result": {"status": "approval_required", "reason": "patch proposal requires explicit patch approval"}}
    preflight = _self_patch_preflight(state)
    if preflight is not None:
        return {**state, "single_change_patch_result": preflight}
    request = state.get("patch_request") or {}
    required = ["file_path", "old_string", "new_string"]
    missing = [key for key in required if key not in request]
    if missing:
        return {**state, "single_change_patch_result": {"status": "blocked", "reason": f"missing patch_request keys: {', '.join(missing)}"}}
    result = apply_single_change_patch(
        file_path=str(request["file_path"]),
        old_string=str(request["old_string"]),
        new_string=str(request["new_string"]),
        description=str(request.get("description", "")),
        allowed_root=_patch_allowed_root(state),
    )
    if result.get("status") == "pass" and state.get("self_patch"):
        # Self-patch lane: mandatory full-suite verification at apply time.
        # The patch only stands if the whole package still passes; otherwise
        # it is reverted immediately and reported as verification_failed.
        verify = _run_self_patch_full_verify()
        if verify.get("status") != "pass":
            backup_path = result.get("backup_path")
            if backup_path:
                restore_backup_patch(
                    str(result["file_path"]),
                    str(backup_path),
                    "auto-revert after self-patch verification failure",
                    allowed_root=_patch_allowed_root(state),
                )
            result = {
                "status": "verification_failed",
                "reason": "self-patch full-suite verification failed; patch reverted",
                "file_path": str(result.get("file_path")),
                "verification": verify,
            }
        else:
            result = {**result, "self_patch_verified": True, "verification": {"status": "pass"}}
    updates: MobiusState = {**state, "single_change_patch_result": result}
    if result.get("status") == "pass":
        updates["side_effects_performed"] = _record_side_effect(state, "single_change_patch")
    return updates


def apply_approved_change_set(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        return {**state, "atomic_change_set_result": {"status": "blocked", "reason": "Foundry mode is spec-only"}}
    if not state.get("execute_change_set"):
        return {**state, "atomic_change_set_result": {"status": "skipped", "reason": "execute_change_set not enabled"}}
    approvals = state.get("approval_decisions") or {}
    if approvals.get("change_set") is not True:
        return {**state, "atomic_change_set_result": {"status": "approval_required", "reason": "atomic change set requires explicit change_set approval"}}
    preflight = _self_patch_preflight(state)
    if preflight is not None:
        return {**state, "atomic_change_set_result": preflight}
    request = state.get("change_set_request") or {}
    changes = request.get("changes") or []
    result = apply_atomic_change_set(changes, str(request.get("description", "")), allowed_root=_patch_allowed_root(state))
    if result.get("status") == "pass" and state.get("self_patch"):
        # Self-patch lane: mandatory full-suite verification at apply time.
        verify = _run_self_patch_full_verify()
        if verify.get("status") != "pass":
            for backup in result.get("backups", []):
                restore_backup_patch(
                    str(backup["file_path"]),
                    str(backup["backup_path"]),
                    "auto-revert after self-patch verification failure",
                    allowed_root=_patch_allowed_root(state),
                )
            result = {
                "status": "verification_failed",
                "reason": "self-patch full-suite verification failed; change set reverted",
                "verification": verify,
                "backups": result.get("backups", []),
            }
        else:
            result = {**result, "self_patch_verified": True, "verification": {"status": "pass"}}
    updates: MobiusState = {**state, "atomic_change_set_result": result}
    if result.get("status") == "pass":
        updates["side_effects_performed"] = _record_side_effect(state, "atomic_change_set")
    return updates


def execute_single_change_patch_worker(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        return {**state, "single_change_patch_result": {"status": "blocked", "reason": "Foundry mode is spec-only"}}
    if state.get("atomic_change_set_result", {}).get("status") in {"pass", "blocked", "approval_required"}:
        return {**state, "single_change_patch_result": {"status": "skipped", "reason": "atomic change set handled this run"}}
    if state.get("single_change_patch_result"):
        return state
    if not state.get("execute_patch"):
        return {**state, "single_change_patch_result": {"status": "skipped", "reason": "execute_patch not enabled"}}
    request = state.get("patch_request") or {}
    required = ["file_path", "old_string", "new_string"]
    missing = [key for key in required if key not in request]
    if missing:
        return {**state, "single_change_patch_result": {"status": "blocked", "reason": f"missing patch_request keys: {', '.join(missing)}"}}
    result = apply_single_change_patch(
        file_path=str(request["file_path"]),
        old_string=str(request["old_string"]),
        new_string=str(request["new_string"]),
        description=str(request.get("description", "")),
    )
    updates: MobiusState = {**state, "single_change_patch_result": result}
    if result.get("status") == "pass":
        updates["side_effects_performed"] = _record_side_effect(state, "single_change_patch")
    return updates


def evaluate_patch_outcome(patch_result: dict[str, Any], local_worker_result: dict[str, Any], goal_type: str) -> dict[str, Any]:
    patch_status = patch_result.get("status", "skipped")
    worker_status = local_worker_result.get("status", "skipped")
    reasons: list[str] = []
    score = 100

    if patch_status == "skipped":
        return {
            "rubric_version": "mobius.patch_eval.v2.0",
            "goal_type": goal_type,
            "score": 100,
            "recommendation": "no_patch_to_evaluate",
            "rollback_recommended": False,
            "reasons": ["No patch was executed."],
        }
    if patch_status != "pass":
        return {
            "rubric_version": "mobius.patch_eval.v2.0",
            "goal_type": goal_type,
            "score": 0,
            "recommendation": "block_patch",
            "rollback_recommended": False,
            "reasons": [f"Patch did not apply cleanly: {patch_result.get('reason', patch_status)}"],
        }

    if not patch_result.get("backup_path"):
        score -= 30
        reasons.append("Patch has no backup path.")
    if patch_result.get("replacement_count") != 1:
        score -= 40
        reasons.append("Patch replacement count was not exactly one.")
    if patch_result.get("self_patch_verified"):
        # Self-patch lane: the full suite already ran at apply time and gated
        # the apply (auto-revert on failure). Treat that as the verifier pass;
        # do not let the skipped local-worker adapter downgrade it to manual.
        worker_status = "pass"
        reasons.append("Self-patch full-suite verification passed at apply time.")
    elif worker_status == "pass":
        reasons.append("Verifier passed after patch.")
    elif worker_status == "skipped":
        score -= 35
        reasons.append("Verifier skipped after patch; keep requires manual review.")
    else:
        score -= 80
        reasons.append("Verifier failed after patch; rollback is recommended.")

    rollback = worker_status not in {"pass", "skipped"}
    if rollback:
        recommendation = "revert_patch"
    elif score >= 80 and worker_status == "pass":
        recommendation = "keep_patch"
    else:
        recommendation = "manual_review"
    return {
        "rubric_version": "mobius.patch_eval.v2.0",
        "goal_type": goal_type,
        "score": max(score, 0),
        "recommendation": recommendation,
        "rollback_recommended": rollback,
        "reasons": reasons,
        "backup_path": patch_result.get("backup_path"),
    }


def evaluate_patch_and_verifier(state: MobiusState) -> MobiusState:
    evaluation = evaluate_patch_outcome(
        state.get("single_change_patch_result", {"status": "skipped"}),
        state.get("local_worker_result", {"status": "skipped"}),
        str(state.get("goal_type", "unknown")),
    )
    return {**state, "patch_evaluation": evaluation}


def _patch_allowed_root(state: MobiusState) -> Path:
    """Return the patch root in effect for this run.

    Default lane: APP_DIR (.mobius/). Self-patch lane (--self-patch):
    the package source tree under src/mobius/.
    """
    return SELF_PATCH_ROOT if state.get("self_patch") else APP_DIR


def _is_inside_patch_root(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    root = root.resolve()
    return resolved == root or root in resolved.parents


def _git_worktree_clean() -> bool:
    """True when the repo working tree has no uncommitted changes.

    Self-patch must start from a clean, revertible baseline so a guarded
    rollback always restores the exact prior state.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--short"],
            text=True, capture_output=True, timeout=30, shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and not result.stdout.strip()


def _self_patch_preflight(state: MobiusState) -> dict[str, Any] | None:
    """Return a blocked result when self-patch preconditions are not met."""
    if not state.get("self_patch"):
        return None
    if not state.get("execute_post_rollback_verify"):
        return {
            "status": "blocked",
            "reason": "self-patch requires --execute-post-rollback-verify (mandatory full-suite verification)",
        }
    if not state.get("propose_patch"):
        return {
            "status": "blocked",
            "reason": "self-patch requires propose_patch (explicit proposal before any apply)",
        }
    approvals = state.get("approval_decisions") or {}
    if approvals.get("patch") is not True and approvals.get("change_set") is not True:
        return {
            "status": "blocked",
            "reason": "self-patch requires explicit approval (--approve-patch or --approve-change-set)",
        }
    if not _git_worktree_clean():
        return {
            "status": "blocked",
            "reason": "self-patch requires a clean git working tree (git status --short must be empty)",
        }
    return None


def restore_backup_patch(file_path: str, backup_path: str, description: str = "", allowed_root: Path | None = None) -> dict[str, Any]:
    target = Path(file_path).resolve()
    backup = Path(backup_path).resolve()
    root = (allowed_root or APP_DIR).resolve()
    if not _is_inside_patch_root(target, root) or not _is_inside_patch_root(backup, root):
        return {"status": "blocked", "reason": "rollback target and backup must be inside the approved patch root", "file_path": str(target), "backup_path": str(backup)}
    if not target.exists() or not target.is_file():
        return {"status": "blocked", "reason": "rollback target must be an existing file", "file_path": str(target)}
    if not backup.exists() or not backup.is_file():
        return {"status": "blocked", "reason": "rollback backup must be an existing file", "backup_path": str(backup)}
    target.write_text(backup.read_text())
    return {
        "status": "pass",
        "restored": True,
        "file_path": str(target),
        "backup_path": str(backup),
        "description": description,
    }


def execute_guarded_rollback(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        return {**state, "rollback_result": {"status": "blocked", "reason": "Foundry mode is spec-only"}}
    evaluation = state.get("patch_evaluation") or {}
    patch_result = state.get("single_change_patch_result") or {}
    if not evaluation.get("rollback_recommended"):
        return {**state, "rollback_result": {"status": "skipped", "reason": "rollback not recommended"}}
    if not state.get("execute_rollback"):
        return {**state, "rollback_result": {"status": "approval_required", "reason": "rollback recommended but execute_rollback not enabled"}}
    backup_path = patch_result.get("backup_path") or evaluation.get("backup_path")
    file_path = patch_result.get("file_path")
    if not file_path or not backup_path:
        return {**state, "rollback_result": {"status": "blocked", "reason": "rollback requires file_path and backup_path"}}
    result = restore_backup_patch(str(file_path), str(backup_path), "guarded rollback after verifier failure", allowed_root=_patch_allowed_root(state))
    updates: MobiusState = {**state, "rollback_result": result}
    if result.get("status") == "pass":
        updates["side_effects_performed"] = _record_side_effect(state, "guarded_rollback")
    return updates



def _build_loop_summary(state: MobiusState) -> dict[str, Any]:
    evaluation = state.get("patch_evaluation") or {}
    rollback = state.get("rollback_result") or {}
    post = state.get("post_rollback_verifier_result") or {}
    keep = state.get("keep_going_result") or {}
    final = evaluation.get("recommendation", "no_patch_to_evaluate")
    change_set = state.get("atomic_change_set_result") or {}
    if keep.get("status") in {"completed", "stopped", "blocked"}:
        status = str(keep.get("status"))
    elif rollback.get("status") == "pass":
        status = "rolled_back"
    elif change_set.get("status") == "blocked":
        status = "blocked"
    elif change_set.get("status") == "approval_required":
        status = "needs_review"
    elif final == "keep_patch":
        status = "completed"
    elif final in {"manual_review", "revert_patch"}:
        status = "needs_review"
    else:
        status = "completed" if final == "no_patch_to_evaluate" else "blocked"
    return {
        "version": "1.2",
        "bounded": True,
        "status": status,
        "final_recommendation": final,
        "patch_status": (state.get("single_change_patch_result") or {}).get("status"),
        "atomic_change_set_status": (state.get("atomic_change_set_result") or {}).get("status"),
        "rollback_status": rollback.get("status"),
        "post_rollback_status": post.get("status"),
        "keep_going_status": (state.get("keep_going_result") or {}).get("status"),
        "keep_going_stop_reason": (state.get("keep_going_result") or {}).get("stop_reason") or (state.get("keep_going_result") or {}).get("reason"),
        "max_iterations": (state.get("budget_policy") or {}).get("max_iterations", 3),
    }


def _run_self_patch_full_verify() -> dict[str, Any]:
    """Mandatory full-suite verification for the self-patch lane.

    Runs the entire pytest suite from the repo root plus a py_compile of the
    graph module, with a controlled environment (PYTHONPATH=src so the local
    source tree is importable, like the repo's own test invocation). Commands
    are fixed constants, not user input, so this mirrors run_doctor's direct
    subprocess pattern rather than the user-command allowlist.
    """
    env = _worker_environment()
    env["PYTHONPATH"] = str(SELF_PATCH_ROOT.parent)
    runs: list[dict[str, Any]] = []
    # Intentionally the full suite, not scoped to the patched file: a self-patch
    # to shared helpers (graph, foundry, verifier allowlist) can break unrelated
    # modules, so every self-patch must prove the whole package still passes.
    commands = [
        ["python3", "-m", "pytest", "-q"],
        ["python3", "-m", "py_compile", str(SELF_PATCH_ROOT / "graph.py")],
    ]
    for argv in commands:
        argv[0] = sys.executable
        try:
            completed = subprocess.run(
                argv,
                cwd=str(REPO_ROOT),
                env=env,
                shell=False,
                text=True,
                capture_output=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return {"status": "fail", "runs": [{"command": " ".join(argv[1:]), "allowed": True, "exit_code": -1, "stdout_tail": "", "stderr_tail": "timeout"}]}
        runs.append({
            "command": " ".join(argv[1:]),
            "allowed": True,
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        })
        if completed.returncode != 0:
            return {"status": "fail", "runs": runs}
    return {"status": "pass", "runs": runs}


def execute_post_rollback_verifier(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        return {**state, "post_rollback_verifier_result": {"status": "blocked", "reason": "Foundry mode is spec-only"}}
    rollback = state.get("rollback_result") or {}
    if rollback.get("status") != "pass":
        result = {"status": "skipped", "reason": "rollback did not execute successfully"}
        next_state = {**state, "post_rollback_verifier_result": result}
        return {**next_state, "loop_summary": _build_loop_summary(next_state)}
    if not state.get("execute_post_rollback_verify"):
        result = {"status": "restored_but_unverified", "reason": "post-rollback verifier not enabled"}
        next_state = {**state, "post_rollback_verifier_result": result}
        return {**next_state, "loop_summary": _build_loop_summary(next_state)}
    budget = state.get("budget_policy", {})
    self_patch = bool(state.get("self_patch"))
    if self_patch:
        # Self-patch lane: mandatory full-suite verification (pytest + compile)
        # from the repo root. A guarded self-patch only stays if the whole
        # package still passes.
        worker = _run_self_patch_full_verify()
    else:
        commands = state.get("post_rollback_commands") or ["python3 -m py_compile graph.py"]
        worker = run_local_worker_commands(
            commands=commands,
            workdir=APP_DIR,
            max_commands=int(budget.get("max_worker_runs", 3)),
            timeout_seconds=min(int(budget.get("max_minutes", 45)) * 60, 300),
        )
    status = "restored_and_healthy" if worker.get("status") == "pass" else "restored_but_unhealthy"
    result = {"status": status, "worker_result": worker}
    next_state = {**state, "post_rollback_verifier_result": result}
    if worker.get("runs"):
        next_state["side_effects_performed"] = _record_side_effect(state, "post_rollback_verifier_commands")
    return {**next_state, "loop_summary": _build_loop_summary(next_state)}

def write_checkpoint(state: MobiusState) -> MobiusState:
    root = foundry.ensure_artifact_root(DEFAULT_CHECKPOINT_DIR, APP_DIR)
    run_id = foundry.validate_run_id(str(state.get("run_id") or _new_run_id()))
    path = root / f"{run_id}_checkpoint.json"
    payload = {
        "schema_version": "mobius.checkpoint.v1.0",
        "phase": "checkpoint_after_quality_review",
        "run_id": run_id,
        "objective": state.get("objective"),
        "context_hint": state.get("context_hint"),
        "answers": state.get("answers", {}),
        "mode": state.get("mode"),
        "execution_authorized": state.get("execution_authorized", False),
        "side_effects_performed": state.get("side_effects_performed", []),
        "parent_run_id": state.get("parent_run_id"),
        "resume_diagnostics": state.get("resume_diagnostics", {}),
        "decision": state.get("decision"),
        "goal_type": state.get("goal_type"),
        "goal_rubric": state.get("goal_rubric", {}),
        "rubric_score": state.get("rubric_score", {}),
        "approval_packet": state.get("approval_packet", {}),
        "agent_foundry_contract": state.get("agent_foundry_contract", {}),
        "foundry_intake": state.get("foundry_intake", {}),
        "risk_assessment": state.get("risk_assessment", {}),
        "approval_gates": state.get("approval_gates", []),
        "pending_approval_gates": state.get("pending_approval_gates", []),
        "readiness": state.get("readiness", {}),
        "runtime_recommendation": state.get("runtime_recommendation", {}),
        "agent_spec": state.get("agent_spec", {}),
        "agent_spec_paths": {
            "json": state.get("agent_spec_json_path"),
            "markdown": state.get("agent_spec_markdown_path"),
        },
        "json_spec_path": state.get("json_spec_path"),
        "budget_policy": state.get("budget_policy", {}),
        "execution_loop": state.get("execution_loop", {}),
        "loop_summary": state.get("loop_summary", _build_loop_summary(state)),
        "quality_score": state.get("quality_score"),
        "quality_status": state.get("quality_status"),
        "report_path": state.get("report_path") or str(DEFAULT_REPORT_DIR / f"{run_id}_mobius_spec.md"),
        "checkpoint_path": str(path),
    }
    foundry.atomic_write_new(path, json.dumps(_safe_json_value(payload), indent=2))
    return {
        **state,
        "checkpoint_path": str(path),
        "report_path": str(payload["report_path"]),
    }


def record_run_history(state: MobiusState) -> MobiusState:
    root = foundry.ensure_artifact_root(DEFAULT_HISTORY_DIR, APP_DIR)
    history_path = root / RUN_HISTORY_PATH.name
    if history_path.is_symlink():
        raise ValueError("run history path must not be a symlink")
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "product_version": RELEASE_VERSION,
        "run_id": state.get("run_id"),
        "objective": state.get("objective"),
        "mode": state.get("mode"),
        "execution_authorized": state.get("execution_authorized", False),
        "side_effects_performed": state.get("side_effects_performed", []),
        "parent_run_id": state.get("parent_run_id"),
        "goal_type": state.get("goal_type"),
        "scaffold_context": state.get("scaffold_context"),
        "decision": state.get("decision"),
        "risk_level": state.get("risk_level"),
        "risk_assessment": state.get("risk_assessment", {}),
        "rubric_score": (state.get("rubric_score") or {}).get("score"),
        "product_status": (state.get("product_status") or {}).get("status"),
        "loop_status": (state.get("loop_summary") or {}).get("status"),
        "keep_going_status": (state.get("keep_going_result") or {}).get("status"),
        "keep_going_stop_reason": (state.get("keep_going_result") or {}).get("stop_reason") or (state.get("keep_going_result") or {}).get("reason"),
        "foundry_completeness": (state.get("foundry_intake") or {}).get("completeness", {}),
        "runtime_recommendation": state.get("runtime_recommendation", {}),
        "readiness": state.get("readiness", {}),
        "approval_gates": state.get("approval_gates", []),
        "pending_approval_gates": state.get("pending_approval_gates", []),
        "report_path": state.get("report_path"),
        "brief_path": state.get("brief_path"),
        "quality_status": state.get("quality_status"),
        "recommended_next_action": state.get("recommended_next_action"),
        "json_spec_path": state.get("json_spec_path"),
        "checkpoint_path": state.get("checkpoint_path"),
        "agent_spec_paths": {
            "json": state.get("agent_spec_json_path"),
            "markdown": state.get("agent_spec_markdown_path"),
        },
        "agent_spec_json_path": state.get("agent_spec_json_path"),
        "agent_spec_markdown_path": state.get("agent_spec_markdown_path"),
    }
    foundry.append_jsonl_no_follow(history_path, _safe_json_value(entry))
    return {**state, "run_history_path": str(history_path)}


SHELL_CONTROL_PATTERN = re.compile(r"[;&|`$<>\n\r]")
ALLOWED_PYTEST_FLAGS = {
    "-q",
    "-v",
    "-vv",
    "-x",
    "--disable-warnings",
    "--collect-only",
}


def _path_is_within_workdir(value: str, workdir: Path) -> bool:
    path_part = value.split("::", 1)[0]
    if not path_part:
        return False
    candidate = (workdir / path_part).resolve()
    return candidate == workdir or workdir in candidate.parents


def _parse_allowlisted_command(command: str, workdir: Path | str) -> tuple[list[str] | None, str | None]:
    """Return validated argv for a narrow verifier command.

    Worker commands are never passed to a shell. The parser also rejects shell
    control characters and paths that escape the approved work directory.
    """
    if not command or SHELL_CONTROL_PATTERN.search(command):
        return None, "shell control characters are not allowed"
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return None, f"invalid command quoting: {exc}"
    if len(argv) < 3 or argv[:2] != ["python3", "-m"]:
        return None, "command must start with an approved python3 -m module"

    root = Path(workdir).resolve()
    module = argv[2]
    args = argv[3:]
    if module == "py_compile":
        if not args:
            return None, "py_compile requires at least one Python file"
        for arg in args:
            if arg.startswith("-") or not arg.endswith(".py") or not _path_is_within_workdir(arg, root):
                return None, "py_compile accepts only relative .py files inside the approved work directory"
        return argv, None

    if module == "pytest":
        for arg in args:
            if arg in ALLOWED_PYTEST_FLAGS:
                continue
            if arg.startswith("--maxfail=") and arg.removeprefix("--maxfail=").isdigit():
                continue
            if arg.startswith("--tb=") and arg.removeprefix("--tb=") in {"auto", "long", "short", "line", "native", "no"}:
                continue
            if arg.startswith("-"):
                return None, f"pytest option is not allowlisted: {arg}"
            if not _path_is_within_workdir(arg, root):
                return None, "pytest targets must remain inside the approved work directory"
        return argv, None

    return None, f"python module is not allowlisted: {module}"


def _is_command_allowlisted(command: str) -> bool:
    argv, _ = _parse_allowlisted_command(command, APP_DIR)
    return argv is not None


def _worker_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def run_local_worker_commands(commands: list[str], workdir: Path | str, max_commands: int, timeout_seconds: int, allowed_workdirs: tuple[Path, ...] | None = None) -> dict[str, Any]:
    workdir_path = Path(workdir).resolve()
    app_root = APP_DIR.resolve()
    allowed = tuple(p.resolve() for p in (allowed_workdirs or (app_root,)))
    if not any(workdir_path == root or root in workdir_path.parents for root in allowed):
        return {"status": "blocked", "runs": [{"command": "<workdir>", "allowed": False, "reason": "workdir outside approved work roots"}]}

    runs: list[dict[str, Any]] = []
    for command in commands[:max_commands]:
        argv, rejection_reason = _parse_allowlisted_command(command, workdir_path)
        if argv is None:
            runs.append({"command": command, "allowed": False, "reason": rejection_reason or "command not allowlisted"})
            return {"status": "blocked", "runs": runs}
        argv[0] = sys.executable
        completed = subprocess.run(
            argv,
            cwd=str(workdir_path),
            env=_worker_environment(),
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        runs.append({
            "command": command,
            "allowed": True,
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        })
        if completed.returncode != 0:
            return {"status": "fail", "runs": runs}
    return {"status": "pass", "runs": runs}


def execute_local_worker_adapter(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        return {**state, "local_worker_result": {"status": "blocked", "reason": "Foundry mode is spec-only"}}
    if state.get("keep_going"):
        return {**state, "local_worker_result": {"status": "skipped", "reason": "deferred to keep-going loop"}}
    if not state.get("execute_local"):
        return {**state, "local_worker_result": {"status": "skipped", "reason": "execute_local not enabled"}}
    budget = state.get("budget_policy", {})
    commands = state.get("worker_commands") or ["python3 -m py_compile graph.py"]
    if state.get("self_patch"):
        # Self-patch lane: worker commands must be scoped to the source tree
        # (REPO_ROOT), not APP_DIR, so allowlisted verifiers run where the
        # patch actually lives.
        workdir = REPO_ROOT
        allowed_workdirs = (APP_DIR, REPO_ROOT)
    else:
        workdir = APP_DIR
        allowed_workdirs = None
    result = run_local_worker_commands(
        commands=commands,
        workdir=workdir,
        max_commands=int(budget.get("max_worker_runs", 3)),
        timeout_seconds=min(int(budget.get("max_minutes", 45)) * 60, 300),
        allowed_workdirs=allowed_workdirs,
    )
    updates: MobiusState = {**state, "local_worker_result": result}
    if any(run.get("allowed") is True for run in result.get("runs", [])):
        updates["side_effects_performed"] = _record_side_effect(state, "local_worker_commands")
    return updates


def run_keep_going_loop(state: MobiusState) -> MobiusState:
    action, reason = keep_going.should_run(state)
    if action != "run":
        status = "skipped" if action == "skip" else "blocked"
        return {**state, "keep_going_result": {"status": status, "reason": reason, "iteration_count": 0}}
    workdir = APP_DIR

    def runner(commands: list[str], max_commands: int, timeout_seconds: int) -> dict[str, Any]:
        return run_local_worker_commands(
            commands=commands,
            workdir=workdir,
            max_commands=max_commands,
            timeout_seconds=timeout_seconds,
        )

    result = keep_going.run_loop(state, runner)
    last_worker = result.get("last_worker_result") or {}
    updates: MobiusState = {
        **state,
        "keep_going_result": result,
        "local_worker_result": last_worker,
    }
    if any(run.get("allowed") is True for run in last_worker.get("runs", [])):
        updates["side_effects_performed"] = _record_side_effect(state, "keep_going_loop")
    return updates


def quality_review_spec(state: MobiusState) -> MobiusState:
    if state.get("mode") == "foundry_spec_only":
        intake = state.get("foundry_intake") or {}
        risk = state.get("risk_assessment") or {}
        complete = bool((intake.get("completeness") or {}).get("complete"))
        has_provenance = all(
            item.get("source_field") and item.get("evidence")
            for item in risk.get("actions", [])
        )
        artifact_present = bool(state.get("agent_spec_json_path") and state.get("agent_spec_markdown_path"))
        score = (50 if complete else 0) + (20 if has_provenance or not risk.get("actions") else 0) + (20 if artifact_present else 0) + (10 if state.get("execution_authorized") is False else 0)
        status = "pass" if complete and artifact_present and score >= 80 else "needs_revision"
        return {**state, "quality_score": score, "quality_status": status}
    score = 0
    required = ["objective", "goal_type", "scaffold_context", "recommended_stack", "scaffold_rationale", "non_goals"]
    spec = state.get("working_spec", {})
    score += sum(10 for k in required if spec.get(k))
    if state.get("success_criteria"):
        score += 15
    if state.get("verifier_plan"):
        score += 10
    if state.get("budget_policy"):
        score += 10
    if state.get("execution_loop"):
        score += 10
    if state.get("json_spec_path") and state.get("checkpoint_path"):
        score += 10
    if state.get("patch_evaluation"):
        score += 10
    if state.get("decision") in {"ready_to_execute", "spec_ready"}:
        score += 5
    score = min(score, 100)
    # Only a completed spec is eligible for a quality pass. Interview or
    # approval-gate decisions are not evaluated yet.
    if state.get("decision") in {"ready_to_execute", "spec_ready"}:
        status = "pass" if score >= 80 else "needs_revision"
    else:
        status = "not_evaluated"
    return {**state, "quality_score": score, "quality_status": status}


def _markdown_report(state: MobiusState) -> str:
    return reporting.render_markdown_report(state)


def write_report(state: MobiusState) -> MobiusState:
    root = foundry.ensure_artifact_root(DEFAULT_REPORT_DIR, APP_DIR)
    run_id = foundry.validate_run_id(str(state.get("run_id") or _new_run_id()))
    next_action = operator_surface.recommended_next_action(state)
    updated: MobiusState = {**state, "recommended_next_action": next_action}
    trace_path = root / f"{run_id}_mobius_spec.md"
    brief_path = root / f"{run_id}_brief.md"
    updated["report_path"] = str(trace_path)
    updated["brief_path"] = str(brief_path)
    foundry.atomic_write_new(trace_path, _markdown_report(updated))
    foundry.atomic_write_new(brief_path, operator_surface.render_operator_brief(updated))
    return updated


def build_graph(node_order: list[str] | None = None):
    if StateGraph is None:
        raise RuntimeError("langgraph is not installed")
    order = node_order or GRAPH_NODE_ORDER
    graph = StateGraph(MobiusState)
    for node in order:
        graph.add_node(node, globals()[node])
    for a, b in zip(order, order[1:]):
        graph.add_edge(a, b)
    graph.add_edge(order[-1], END)
    graph.set_entry_point(order[0])
    return graph.compile()


def _effective_agent_spec_dir() -> Path:
    configured = DEFAULT_AGENT_SPEC_DIR.absolute()
    app = APP_DIR.absolute()
    if configured == app or app in configured.parents:
        return configured
    return app / "agent_specs"


def _expected_run_artifacts(run_id: str, include_agent_spec: bool) -> list[Path]:
    paths = [
        foundry.ensure_artifact_root(DEFAULT_SPEC_DIR, APP_DIR) / f"{run_id}_mobius_spec.json",
        foundry.ensure_artifact_root(DEFAULT_CHECKPOINT_DIR, APP_DIR) / f"{run_id}_checkpoint.json",
        foundry.ensure_artifact_root(DEFAULT_REPORT_DIR, APP_DIR) / f"{run_id}_mobius_spec.md",
        foundry.ensure_artifact_root(DEFAULT_REPORT_DIR, APP_DIR) / f"{run_id}_brief.md",
    ]
    if include_agent_spec:
        agent_root = foundry.ensure_artifact_root(_effective_agent_spec_dir(), APP_DIR)
        paths.extend([
            agent_root / f"{run_id}_agent_spec.json",
            agent_root / f"{run_id}_agent_spec.md",
        ])
    return paths


def _preflight_run_artifacts(run_id: str, include_agent_spec: bool) -> list[Path]:
    paths = _expected_run_artifacts(run_id, include_agent_spec)
    collisions = [str(path) for path in paths if path.exists() or path.is_symlink()]
    if collisions:
        raise FileExistsError(f"refusing run because artifact paths already exist: {', '.join(collisions)}")
    return paths


def run_graph(
    objective: str,
    context_hint: str | None = None,
    run_id: str | None = None,
    execute_local: bool = False,
    worker_commands: list[str] | None = None,
    execute_patch: bool = False,
    patch_request: dict[str, Any] | None = None,
    execute_rollback: bool = False,
    execute_post_rollback_verify: bool = False,
    post_rollback_commands: list[str] | None = None,
    propose_patch: bool = False,
    approval_decisions: dict[str, bool] | None = None,
    bounded_loop: bool = False,
    keep_going: bool = False,
    execute_change_set: bool = False,
    change_set_request: dict[str, Any] | None = None,
    answers: dict[str, Any] | None = None,
    resume_checkpoint: str | None = None,
    foundry_mode: bool | None = None,
    self_patch: bool = False,
) -> MobiusState:
    resume_data: dict[str, Any] = {}
    if resume_checkpoint:
        resume_data = foundry.load_resume_checkpoint(resume_checkpoint)
        objective = objective.strip() or str(resume_data.get("objective") or "")
        context_hint = context_hint if context_hint is not None else resume_data.get("context_hint")
        merged_answers = foundry.validate_answers(resume_data.get("answers") or {})
        merged_answers.update(foundry.normalize_answers(answers))
        answers = foundry.validate_answers(merged_answers)

    objective, context_hint = foundry.validate_text_inputs(objective, context_hint)
    foundry.reject_secret_values(objective, context_hint)
    spec_only_foundry = bool(foundry_mode) if foundry_mode is not None else bool(answers or resume_checkpoint or foundry.is_agent_request(objective))
    selected_run_id = foundry.validate_run_id(run_id) if run_id else _new_run_id()
    _preflight_run_artifacts(selected_run_id, spec_only_foundry)
    initial: MobiusState = {
        "objective": objective,
        "context_hint": context_hint,
        "run_id": selected_run_id,
        "answers": foundry.validate_answers(answers),
        "resumed_from_checkpoint": resume_checkpoint or "",
        "parent_run_id": str(resume_data.get("parent_run_id") or ""),
        "resume_diagnostics": {"ignored_untrusted_fields": resume_data.get("ignored_derived_fields", [])},
        "mode": "foundry_spec_only" if spec_only_foundry else "bounded_control_loop",
        "execution_authorized": False if spec_only_foundry else bool(execute_local or execute_patch or execute_change_set or keep_going or bounded_loop),
        "side_effects_performed": [],
        "local_worker_result": {"status": "skipped", "reason": "Foundry spec-only mode"} if spec_only_foundry else {},
        "single_change_patch_result": {"status": "skipped", "reason": "Foundry spec-only mode"} if spec_only_foundry else {},
        "atomic_change_set_result": {"status": "skipped", "reason": "Foundry spec-only mode"} if spec_only_foundry else {},
        "rollback_result": {"status": "skipped", "reason": "Foundry spec-only mode"} if spec_only_foundry else {},
        "post_rollback_verifier_result": {"status": "skipped", "reason": "Foundry spec-only mode"} if spec_only_foundry else {},
        # Agent Foundry is intake/spec-only even if execution flags are
        # accidentally combined with its CLI invocation.
        "execute_local": False if spec_only_foundry else execute_local,
        "worker_commands": [] if spec_only_foundry else (worker_commands or []),
        "self_patch": False if spec_only_foundry else self_patch,
        "execute_patch": False if spec_only_foundry else execute_patch,
        "patch_request": {} if spec_only_foundry else (patch_request or {}),
        "execute_rollback": False if spec_only_foundry else (execute_rollback or bool((approval_decisions or {}).get("rollback"))),
        "execute_post_rollback_verify": False if spec_only_foundry else execute_post_rollback_verify,
        "post_rollback_commands": [] if spec_only_foundry else (post_rollback_commands or []),
        "propose_patch": False if spec_only_foundry else propose_patch,
        "approval_decisions": {} if spec_only_foundry else (approval_decisions or {}),
        "bounded_loop": False if spec_only_foundry else bounded_loop,
        "keep_going": False if spec_only_foundry else bool(keep_going or bounded_loop),
        "execute_change_set": False if spec_only_foundry else execute_change_set,
        "change_set_request": {} if spec_only_foundry else (change_set_request or {}),
    }
    tracker_token, owned_artifacts = foundry.begin_artifact_tracking()
    try:
        return build_graph(FOUNDRY_NODE_ORDER if spec_only_foundry else GRAPH_NODE_ORDER).invoke(initial)
    except Exception:
        foundry.cleanup_owned_artifacts(owned_artifacts)
        raise
    finally:
        foundry.end_artifact_tracking(tracker_token)



def resume_from_checkpoint(checkpoint_path: str) -> MobiusState:
    """Inspect a v1 checkpoint through the strict loader.

    This compatibility helper never restores derived authority, approvals,
    decisions, execution flags, or artifact paths. Call ``run_graph`` with
    ``resume_checkpoint=...`` to recompute a new spec-only revision.
    """
    payload = foundry.load_resume_checkpoint(checkpoint_path)
    return {
        "objective": payload["objective"],
        "context_hint": payload["context_hint"],
        "answers": payload["answers"],
        "parent_run_id": str(payload.get("parent_run_id") or ""),
        "resume_package": {
            "can_resume": True,
            "checkpoint_path": str(Path(checkpoint_path)),
            "ignored_untrusted_fields": payload.get("ignored_derived_fields", []),
            "recommended_next_action": "Call run_graph(..., resume_checkpoint=path); all risk, approval, readiness, runtime, decision, execution, and artifact fields will be recomputed.",
        },
        "resumed_from_checkpoint": str(Path(checkpoint_path)),
    }

def run_doctor() -> dict[str, Any]:
    checks: dict[str, str] = {}
    checks["langgraph_runtime"] = "pass" if StateGraph is not None and END is not None else "fail"
    graph_compile = subprocess.run([sys.executable, "-m", "py_compile", str(Path(__file__).resolve())], text=True, capture_output=True, timeout=60)
    checks["graph_py_compile"] = "pass" if graph_compile.returncode == 0 else "fail"
    repo_root = Path(__file__).resolve().parents[2]
    test_sources = list((repo_root / "tests").glob("test_*.py"))
    checks["pytest_collects_source"] = "pass" if test_sources else "not_applicable"
    wrapper = Path(__file__).resolve().parent / "cli.py"
    wrapper_compile = subprocess.run([sys.executable, "-m", "py_compile", str(wrapper)], text=True, capture_output=True, timeout=60)
    checks["wrapper_callable"] = "pass" if wrapper.exists() and wrapper_compile.returncode == 0 else "fail"
    app_root = APP_DIR.resolve()
    if app_root.parent == app_root:
        checks["app_root_safety"] = "not_applicable"
    else:
        outside = app_root.parent / f".mobius-doctor-outside-{_new_run_id()}"
        safety = apply_single_change_patch(str(outside), "before", "after", "doctor")
        checks["app_root_safety"] = "pass" if (
            safety.get("status") == "blocked"
            and safety.get("reason") == "patch target outside approved patch root"
            and not outside.exists()
        ) else "fail"
    rejected_argv, _ = _parse_allowlisted_command(
        "python3 -m pytest --version; printf MOBIUS_PREFIX_BYPASS",
        APP_DIR,
    )
    checks["worker_command_safety"] = "pass" if rejected_argv is None else "fail"
    try:
        foundry.ensure_artifact_root(DEFAULT_HISTORY_DIR, APP_DIR)
        checks["artifact_root_safety"] = "pass"
        checks["history_writable"] = "pass"
    except (OSError, ValueError):
        checks["artifact_root_safety"] = "fail"
        checks["history_writable"] = "fail"
    return {
        "product_version": RELEASE_VERSION,
        "status": "pass" if all(v in {"pass", "not_applicable"} for v in checks.values()) else "fail",
        "checks": checks,
        "app_dir": str(APP_DIR),
        "history_path": str(RUN_HISTORY_PATH),
    }


def summarize_for_cli(state: MobiusState) -> str:
    completeness = (state.get("foundry_intake") or {}).get("completeness") or {}
    runtime = state.get("runtime_recommendation") or {}
    pending = state.get("pending_approval_gates") or []
    return json.dumps({
        "decision": state.get("decision"),
        "risk_level": state.get("risk_level"),
        "run_id": state.get("run_id"),
        "mode": operator_surface.public_mode(state.get("mode")),
        "execution_authorized": state.get("execution_authorized", False),
        "recommended_next_action": state.get("recommended_next_action") or operator_surface.recommended_next_action(state),
        "interview_questions": state.get("interview_questions") or [],
        "pending_approval_gates": [gate.get("action") for gate in pending],
        "intake_complete": completeness.get("complete"),
        "missing": completeness.get("missing") or [],
        "runtime": runtime.get("selected"),
        "brief_path": state.get("brief_path"),
        "checkpoint_path": state.get("checkpoint_path"),
        "agent_spec": state.get("agent_spec_json_path") or None,
    }, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Möbius v1 pre-agent constitution")
    parser.add_argument("objective")
    parser.add_argument("--context", default=None)
    parser.add_argument("--execute-local", action="store_true", help="Run allowlisted local worker commands inside the Mobius app root")
    parser.add_argument("--worker-command", action="append", default=[], help="Allowlisted worker command; may be repeated")
    parser.add_argument("--execute-patch", action="store_true", help="Apply one exact allowlisted local patch before verification")
    parser.add_argument("--patch-file", default=None)
    parser.add_argument("--patch-old", default=None)
    parser.add_argument("--patch-new", default=None)
    parser.add_argument("--patch-description", default="")
    parser.add_argument("--execute-rollback", action="store_true", help="Restore from patch backup only when evaluator recommends rollback")
    args = parser.parse_args()
    patch_request = {}
    if args.execute_patch:
        patch_request = {
            "file_path": args.patch_file,
            "old_string": args.patch_old,
            "new_string": args.patch_new,
            "description": args.patch_description,
        }
    result = run_graph(
        args.objective,
        args.context,
        execute_local=args.execute_local,
        worker_commands=args.worker_command,
        execute_patch=args.execute_patch,
        patch_request=patch_request,
        execute_rollback=args.execute_rollback,
    )
    print(summarize_for_cli(result))
