#!/usr/bin/env python3
"""Möbius — pre-agent constitution.

Turns a vague objective into an inspectable spec, a human-readable brief,
and (when needed) interview questions. It never builds or runs agents, runs
commands, or edits files outside its own .mobius/ artifact folder.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
from typing import Any, Literal, TypedDict
import json
import re

from . import RELEASE_VERSION
from . import assist as model_assist
from . import foundry
from . import operator_surface
from . import reporting

GoalType = Literal["code", "research", "writing", "system_admin", "notes_project", "business_ops", "unknown"]
RiskLevel = Literal["low", "medium", "high"]
ScaffoldContext = Literal["internal", "client_work", "public_repo", "throwaway_spike", "notes_only", "unknown"]
Decision = Literal["spec_ready", "needs_interview", "human_approval_required"]

APP_DIR = Path(os.environ.get("MOBIUS_APP_DIR", Path.cwd() / ".mobius")).absolute()
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
    "quality_review_spec",
    "write_checkpoint",
    "write_report",
    "record_run_history",
]

CODE_TERMS = {"build", "code", "app", "script", "cli", "api", "test", "repo", "implement", "fix", "debug", "verify", "self", "check"}
RESEARCH_TERMS = {"research", "compare", "evaluate", "analyze", "find", "source", "summarize", "investigate"}
WRITING_TERMS = {"write", "draft", "article", "post", "copy", "brief", "memo", "proposal", "digest", "newsletter"}
SYSTEM_TERMS = {"server", "cron", "config", "env", "service", "logs", "backup", "dashboard"}
NOTES_TOOL_TERMS = {"obsidian", "vault"}
BUSINESS_TERMS = {"client", "lead", "sales", "campaign", "sponsor", "launch"}


class MobiusState(TypedDict, total=False):
    objective: str
    context_hint: str | None
    run_id: str
    goal_type: GoalType
    goal_rubric: dict[str, Any]
    rubric_score: dict[str, Any]
    approval_packet: dict[str, Any]
    run_history_path: str
    scaffold_context: ScaffoldContext
    risk_level: RiskLevel
    ambiguity_score: int
    assumptions: list[str]
    scaffold_recommendation: dict[str, Any]
    working_spec: dict[str, Any]
    agent_foundry_contract: dict[str, Any]
    answers: dict[str, Any]
    assist: dict[str, Any]
    suggested_answers_path: str
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
    json_spec_path: str
    checkpoint_path: str
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
    parent_run_id: str
    errors: list[str]


def _stem(token: str) -> str:
    # Plural/third-person "s" only, so "writes" matches "write" and "tests" matches "test".
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    return {_stem(token) for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())}


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
    # "Build an agent that writes a digest" is a writing job, not a code job:
    # classify what the agent would do, not the request to build one.
    task = foundry.agent_task_text(state.get("objective", ""))
    text = f"{task} {state.get('context_hint') or ''}".lower()
    if _contains_any(text, CODE_TERMS):
        gt: GoalType = "code"
    elif _contains_any(text, RESEARCH_TERMS):
        gt = "research"
    elif _contains_any(text, WRITING_TERMS):
        gt = "writing"
    elif _contains_any(text, SYSTEM_TERMS):
        gt = "system_admin"
    elif _contains_any(text, NOTES_TOOL_TERMS):
        gt = "notes_project"
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
        "notes_project": {
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
        "notes_only": {
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
        "notes_only": "notes_only",
        "notes": "notes_only",
        # older spelling
        "obsidian": "notes_only",
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
        context = "notes_only"
    elif "internal" in text or "local" in text or state.get("goal_type") in {"code", "system_admin", "research", "writing"}:
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
        spec["agent_intake"] = {
            "status": "active_spec_only",
            "front_door": "raw_agent_idea_to_interviewed_agent_spec",
            "output_contract": "Agent Spec plus one advisory runtime recommendation; no build or execution",
        }
    if goal_type == "code":
        spec["expected_artifacts"] = ["source code", "tests", "wrapper or run command", "final run report"]
    elif goal_type == "research":
        spec["expected_artifacts"] = ["source-grounded findings", "comparison/scoring", "notes or report artifact"]
    elif goal_type == "writing":
        spec["expected_artifacts"] = ["draft", "quality review", "saved document"]
    elif goal_type == "notes_project":
        spec["expected_artifacts"] = ["Markdown note/update", "link/index update", "read-back verification"]
    else:
        spec["expected_artifacts"] = ["clarified spec", "success criteria", "final report"]
    if spec.get("agent_intake"):
        spec["expected_artifacts"] = list(dict.fromkeys([*spec.get("expected_artifacts", []), "Agent Spec", "interview questions", "build path decision", "registration plan"]))
    return {**state, "working_spec": spec}


def build_agent_foundry_contract(state: MobiusState) -> MobiusState:
    """Build the spec-only agent intake after risk is known."""
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

    intake = foundry.build_intake(objective, state.get("context_hint"), state.get("answers"), _model_drafts(state))
    risk_assessment = state.get("risk_assessment") or foundry.assess_risk_sources(
        objective,
        state.get("context_hint"),
        state.get("answers"),
        model_findings=_model_findings(state),
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


def _model_findings(state: MobiusState) -> list[dict[str, Any]]:
    assist = state.get("assist") or {}
    return list(assist.get("capabilities") or []) if assist.get("status") == "ok" else []


def _model_drafts(state: MobiusState) -> dict[str, Any]:
    assist = state.get("assist") or {}
    return dict(assist.get("draft_answers") or {}) if assist.get("status") == "ok" else {}


def detect_risk_and_ambiguity(state: MobiusState) -> MobiusState:
    objective = state.get("objective", "")
    assessment = foundry.assess_risk_sources(
        objective,
        state.get("context_hint"),
        state.get("answers"),
        model_findings=_model_findings(state),
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
        unconfirmed = list((state.get("risk_assessment") or {}).get("unconfirmed_signals") or [])
        qs.extend(foundry.interview_questions_for_dimensions(missing))
        qs.extend(foundry.interview_questions_for_signals(unconfirmed))
        if missing or unconfirmed:
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
        qs.append("What artifact should count as done: code/app, CLI, report, note, PR, or something else?")
        qs.append("What is the smallest useful version you would accept for v0?")
    if risk in {"medium", "high"}:
        qs.append("Should the work be draft-only, or may it change local files after taking a backup?")
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
    """Propose cost and runaway limits for whatever eventually does this work.

    Möbius itself runs once and stops; these limits belong in the spec so the
    eventual agent or person starts bounded.
    """
    text = state.get("objective", "").lower()
    risk_reasons: list[str] = []
    if any(term in text for term in ["forever", "never-ending", "never ending", "continuous", "keep improving", "indefinitely"]):
        risk_reasons.append("Objective implies forever/continuous looping; require bounded budget review.")
    if state.get("risk_level") != "low":
        risk_reasons.append(f"Risk level is {state.get('risk_level')}; budget and approval gates should be stricter.")
    if state.get("ambiguity_score", 0) >= 4:
        risk_reasons.append("Ambiguous objectives burn time and tokens; settle the spec first.")

    policy = {
        "applies_to": "the eventual implementation, not this Möbius run",
        "max_iterations": 3,
        "max_minutes": 45,
        "max_consecutive_failures": 2,
        "require_progress_delta_each_iteration": True,
        "requires_budget_review": bool(risk_reasons),
        "risk_reasons": risk_reasons,
        "runaway_stop_conditions": [
            "no measurable progress after one iteration",
            "same failure repeats twice",
            "work needs broader scope than approved",
            "cost or usage cannot be measured",
            "estimated budget reaches its warning threshold",
            "human approval boundary encountered",
        ],
    }
    if risk_reasons and state.get("decision") in {"spec_ready"} and (state.get("foundry_intake") or {}).get("status") == "not_applicable":
        existing_questions = list(state.get("interview_questions") or [])
        existing_questions.append("This sounds open-ended. What caps should the work have on iterations, time, and cost?")
        return {**state, "budget_policy": policy, "decision": "needs_interview", "interview_questions": existing_questions}
    return {**state, "budget_policy": policy}


def design_execution_loop(state: MobiusState) -> MobiusState:
    budget = state.get("budget_policy", {})
    loop = {
        "max_iterations": budget.get("max_iterations", 3),
        "max_minutes": budget.get("max_minutes", 45),
        "applies_to": "the eventual implementation, not this Möbius run",
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
    if state.get("decision") == "human_approval_required":
        required.append("human")
    seen: list[str] = []
    for item in required:
        if item not in seen:
            seen.append(item)
    approvals: dict[str, bool] = {}
    packet = {
        "version": "mobius.approval_packet.v2.0",
        "required_approvals": seen,
        "granted": {key: bool(approvals.get(key)) for key in seen},
        "missing": [key for key in seen if not approvals.get(key) and key != "human"],
        "human_required": "human" in seen,
    }
    return {**state, "approval_packet": packet}


def finalize_foundry_spec(state: MobiusState) -> MobiusState:
    """Write standalone Agent Specs only after every intake dimension and risk signal resolves."""
    intake = state.get("foundry_intake") or {}
    if intake.get("status") == "not_applicable" or not (intake.get("completeness") or {}).get("complete"):
        return {**state, "agent_spec": {}}
    if (state.get("risk_assessment") or {}).get("unconfirmed_signals"):
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
        "assist": state.get("assist") or None,
        "safety_boundary": (state.get("working_spec") or {}).get("non_goals", []),
    }
    foundry.atomic_write_new(path, json.dumps(_safe_json_value(payload), indent=2))
    return {**state, "json_spec_path": str(path)}


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
        "assist": _assist_summary(state.get("assist")),
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
    if state.get("decision") in {"spec_ready"}:
        score += 5
    score = min(score, 100)
    # Only a completed spec is eligible for a quality pass. Interview or
    # approval-gate decisions are not evaluated yet.
    if state.get("decision") in {"spec_ready"}:
        status = "pass" if score >= 80 else "needs_revision"
    else:
        status = "not_evaluated"
    return {**state, "quality_score": score, "quality_status": status}


def _markdown_report(state: MobiusState) -> str:
    return reporting.render_markdown_report(state)


def _assist_summary(assist: dict[str, Any] | None) -> dict[str, Any] | None:
    if not assist:
        return None
    keys = ("status", "model", "request_id", "usage", "error")
    return {key: assist.get(key) for key in keys if assist.get(key) is not None}


def _suggested_answers(state: MobiusState) -> dict[str, Any]:
    missing = list(((state.get("foundry_intake") or {}).get("completeness") or {}).get("missing") or [])
    return model_assist.suggested_answers(state.get("assist"), dict(state.get("answers") or {}), missing)


def write_report(state: MobiusState) -> MobiusState:
    root = foundry.ensure_artifact_root(DEFAULT_REPORT_DIR, APP_DIR)
    run_id = foundry.validate_run_id(str(state.get("run_id") or _new_run_id()))
    updated: MobiusState = dict(state)  # type: ignore[assignment]
    suggested = _suggested_answers(state)
    if suggested:
        suggested_path = root / f"{run_id}_suggested_answers.json"
        foundry.atomic_write_new(suggested_path, json.dumps(suggested, indent=2, ensure_ascii=False))
        updated["suggested_answers_path"] = str(suggested_path)
    updated["recommended_next_action"] = operator_surface.recommended_next_action(updated)
    trace_path = root / f"{run_id}_mobius_spec.md"
    brief_path = root / f"{run_id}_brief.md"
    updated["report_path"] = str(trace_path)
    updated["brief_path"] = str(brief_path)
    foundry.atomic_write_new(trace_path, _markdown_report(updated))
    foundry.atomic_write_new(brief_path, operator_surface.render_operator_brief(updated))
    return updated


class Pipeline:
    """Run the steps in a fixed order; each step takes the state and returns the next one."""

    def __init__(self, steps: list[Any]):
        self.steps = steps

    def invoke(self, state: MobiusState) -> MobiusState:
        for step in self.steps:
            state = step(state)
        return state


def build_graph(node_order: list[str] | None = None) -> Pipeline:
    return Pipeline([globals()[name] for name in node_order or GRAPH_NODE_ORDER])


def _effective_agent_spec_dir() -> Path:
    configured = DEFAULT_AGENT_SPEC_DIR.absolute()
    app = APP_DIR.absolute()
    if configured == app or app in configured.parents:
        return configured
    return app / "agent_specs"


def _expected_run_artifacts(run_id: str, include_agent_spec: bool, include_suggestions: bool = False) -> list[Path]:
    paths = [
        foundry.ensure_artifact_root(DEFAULT_SPEC_DIR, APP_DIR) / f"{run_id}_mobius_spec.json",
        foundry.ensure_artifact_root(DEFAULT_CHECKPOINT_DIR, APP_DIR) / f"{run_id}_checkpoint.json",
        foundry.ensure_artifact_root(DEFAULT_REPORT_DIR, APP_DIR) / f"{run_id}_mobius_spec.md",
        foundry.ensure_artifact_root(DEFAULT_REPORT_DIR, APP_DIR) / f"{run_id}_brief.md",
    ]
    if include_suggestions:
        paths.append(foundry.ensure_artifact_root(DEFAULT_REPORT_DIR, APP_DIR) / f"{run_id}_suggested_answers.json")
    if include_agent_spec:
        agent_root = foundry.ensure_artifact_root(_effective_agent_spec_dir(), APP_DIR)
        paths.extend([
            agent_root / f"{run_id}_agent_spec.json",
            agent_root / f"{run_id}_agent_spec.md",
        ])
    return paths


def _preflight_run_artifacts(run_id: str, include_agent_spec: bool, include_suggestions: bool = False) -> list[Path]:
    paths = _expected_run_artifacts(run_id, include_agent_spec, include_suggestions)
    collisions = [str(path) for path in paths if path.exists() or path.is_symlink()]
    if collisions:
        raise FileExistsError(f"refusing run because artifact paths already exist: {', '.join(collisions)}")
    return paths


def run_graph(
    objective: str,
    context_hint: str | None = None,
    run_id: str | None = None,
    answers: dict[str, Any] | None = None,
    resume_checkpoint: str | None = None,
    foundry_mode: bool | None = None,
    assist: dict[str, Any] | None = None,
) -> MobiusState:
    """Run the pipeline once and write its artifacts.

    ``assist`` is the result of ``assist.request_suggestions`` when the
    person passed ``--assist``; it is advisory and recorded in the spec.
    """
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
    _preflight_run_artifacts(selected_run_id, spec_only_foundry, bool(assist and assist.get("status") == "ok"))
    initial: MobiusState = {
        "objective": objective,
        "context_hint": context_hint,
        "run_id": selected_run_id,
        "answers": foundry.validate_answers(answers),
        "resumed_from_checkpoint": resume_checkpoint or "",
        "parent_run_id": str(resume_data.get("parent_run_id") or ""),
        "resume_diagnostics": {"ignored_untrusted_fields": resume_data.get("ignored_derived_fields", [])},
        "mode": "foundry_spec_only" if spec_only_foundry else "bounded_control_loop",
        # Möbius writes specs and stops; it never runs commands or edits files.
        # The only outside contact is the opt-in --assist request, recorded here.
        "execution_authorized": False,
        "side_effects_performed": ["network: Anthropic API (--assist)"] if model_assist.made_network_call(assist) else [],
        "assist": assist or {},
    }
    tracker_token, owned_artifacts = foundry.begin_artifact_tracking()
    try:
        return build_graph(GRAPH_NODE_ORDER).invoke(initial)
    except Exception:
        foundry.cleanup_owned_artifacts(owned_artifacts)
        raise
    finally:
        foundry.end_artifact_tracking(tracker_token)


def run_doctor() -> dict[str, Any]:
    checks: dict[str, str] = {}
    missing_steps = [name for name in GRAPH_NODE_ORDER if not callable(globals().get(name))]
    checks["pipeline_steps"] = "fail" if missing_steps else "pass"
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
        **({"assist": _assist_summary(state.get("assist"))} if state.get("assist") else {}),
        **({"suggested_answers": state["suggested_answers_path"]} if state.get("suggested_answers_path") else {}),
    }, indent=2)


