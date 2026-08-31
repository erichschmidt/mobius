"""Mobius v2.7 operator decision surface.

Keeps the daily loop usable: a short brief per run, an append-only outcome
log, and a learning report. Does not execute work, patch code, or grant
lifecycle authority.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
import json

from . import RELEASE_VERSION
from . import foundry

ALLOWED_OUTCOMES = ("accepted", "edited", "rejected", "ignored")
OPERATOR_BRIEF_MAX_LINES = 40
MAX_OUTCOME_NOTE_CHARS = 2000
OUTCOMES_FILENAME = "outcomes.jsonl"
RUNS_FILENAME = "runs.jsonl"


def public_mode(mode: str | None) -> str:
    if mode == "foundry_spec_only":
        return "intake"
    if mode == "bounded_control_loop":
        return "spec"
    return mode or "spec"


def recommended_next_action(state: Mapping[str, Any]) -> str:
    run_id = state.get("run_id") or "<run_id>"
    pending = state.get("pending_approval_gates") or []
    questions = state.get("interview_questions") or []
    decision = state.get("decision")
    quality = state.get("quality_status")
    intake = state.get("foundry_intake") or {}
    incomplete = bool((intake.get("completeness") or {}).get("missing"))
    if decision == "needs_interview" or (questions and incomplete):
        if pending:
            return (
                f"Answer the interview questions and review the pending approval gates, "
                f"then resume run `{run_id}`."
            )
        return f"Answer the interview questions and resume run `{run_id}`."
    if pending or decision == "human_approval_required":
        return f"A human must resolve the pending approval gates for run `{run_id}`. Do not build or execute."
    if quality == "needs_revision":
        return f"Revise the spec until quality is pass, then re-run `{run_id}`."
    if decision in {"spec_ready", "ready_to_execute"}:
        return (
            f"Spec is ready. Möbius did not execute anything. "
            f"If the brief helped: mobius --record-outcome {run_id} --outcome accepted"
        )
    return (
        f"Review the brief, then record an outcome: "
        f"mobius --record-outcome {run_id} --outcome accepted|edited|rejected|ignored"
    )


def render_operator_brief(state: Mapping[str, Any]) -> str:
    questions = list(state.get("interview_questions") or [])[:5]
    pending = list(state.get("pending_approval_gates") or [])[:5]
    next_action = state.get("recommended_next_action") or recommended_next_action(state)
    objective = " ".join(str(state.get("objective") or "").split())
    if len(objective) > 240:
        objective = objective[:237] + "..."
    lines = [
        f"# Mobius brief — {state.get('run_id')}",
        "",
        f"**Decision:** `{state.get('decision')}`",
        f"**Risk:** `{state.get('risk_level')}`",
        f"**Quality:** `{state.get('quality_status')}` ({state.get('quality_score')}/100)",
        f"**Mode:** `{public_mode(state.get('mode'))}`",
        f"**Goal type:** `{state.get('goal_type')}` / `{state.get('scaffold_context')}`",
        "",
        "## Objective",
        "",
        objective or "(none)",
        "",
        "## Do next",
        "",
        next_action,
        "",
        "## Pending approvals",
        "",
    ]
    if pending:
        for gate in pending:
            action = gate.get("action") or gate.get("canonical_action") or "gate"
            lines.append(f"- {action}: {foundry.interview_question_for_gate(str(action))}")
    else:
        lines.append("- none")
    lines.append("")
    if questions:
        lines += ["## Interview questions", ""]
        lines += [f"{index}. {question}" for index, question in enumerate(questions, 1)]
        lines.append("")
    lines += [
        "## Files",
        "",
        f"- brief: `{state.get('brief_path')}`",
        f"- trace: `{state.get('report_path')}`",
        f"- spec: `{state.get('json_spec_path')}`",
        "",
        f"Record later: `mobius --record-outcome {state.get('run_id')} --outcome accepted|edited|rejected|ignored`",
        "",
    ]
    clipped = lines[:OPERATOR_BRIEF_MAX_LINES]
    return "\n".join(clipped) + ("\n" if clipped else "")


def _read_jsonl_no_follow(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink():
        raise ValueError(f"{path.name} must not be a symlink")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name} line {line_number} is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path.name} line {line_number} is not a JSON object")
            rows.append(payload)
    return rows


def record_outcome(
    run_id: str,
    outcome: str,
    note: str = "",
    *,
    history_dir: Path,
    app_dir: Path,
) -> dict[str, Any]:
    validated_run_id = foundry.validate_run_id(run_id)
    outcome_key = str(outcome or "").strip().lower()
    if outcome_key not in ALLOWED_OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(ALLOWED_OUTCOMES)}")
    note_text = str(note or "")
    if len(note_text) > MAX_OUTCOME_NOTE_CHARS:
        raise ValueError(f"note exceeds {MAX_OUTCOME_NOTE_CHARS} characters")
    if "\x00" in note_text:
        raise ValueError("note must not contain NUL")
    foundry.reject_secret_values(note_text)
    root = foundry.ensure_artifact_root(history_dir, app_dir)
    path = root / OUTCOMES_FILENAME
    if path.is_symlink():
        raise ValueError("outcomes path must not be a symlink")
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "product_version": RELEASE_VERSION,
        "run_id": validated_run_id,
        "outcome": outcome_key,
        "note": note_text,
    }
    foundry.append_jsonl_no_follow(path, entry)
    return {
        "status": "recorded",
        "run_id": validated_run_id,
        "outcome": outcome_key,
        "outcomes_path": str(path),
        "product_version": RELEASE_VERSION,
    }


def _latest_outcome_by_run(outcomes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in outcomes:
        run_id = row.get("run_id")
        if isinstance(run_id, str) and run_id:
            latest[run_id] = row
    return latest


def _bucket_rates(matched: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in matched:
        key = str(row.get(field) or "unknown")
        bucket = buckets.setdefault(
            key,
            {"n": 0, "accepted": 0, "edited": 0, "rejected": 0, "ignored": 0, "acceptance_rate": 0.0},
        )
        bucket["n"] += 1
        outcome = row.get("outcome")
        if outcome in ALLOWED_OUTCOMES:
            bucket[outcome] += 1
    for bucket in buckets.values():
        bucket["acceptance_rate"] = round(bucket["accepted"] / bucket["n"], 4) if bucket["n"] else 0.0
    return buckets


def build_learning_report(*, history_dir: Path, app_dir: Path) -> dict[str, Any]:
    root = foundry.ensure_artifact_root(history_dir, app_dir)
    runs_path = root / RUNS_FILENAME
    outcomes_path = root / OUTCOMES_FILENAME
    if runs_path.is_symlink() or outcomes_path.is_symlink():
        raise ValueError("history files must not be symlinks")
    runs = _read_jsonl_no_follow(runs_path)
    outcomes = _read_jsonl_no_follow(outcomes_path)
    latest = _latest_outcome_by_run(outcomes)
    run_ids = {str(row.get("run_id")) for row in runs if row.get("run_id")}
    matched: list[dict[str, Any]] = []
    unmatched_runs: list[str] = []
    for row in runs:
        run_id = str(row.get("run_id") or "")
        if not run_id:
            continue
        if run_id in latest:
            outcome_row = latest[run_id]
            matched.append({
                **row,
                "outcome": outcome_row.get("outcome"),
                "outcome_note": outcome_row.get("note") or "",
            })
        else:
            unmatched_runs.append(run_id)
    orphan_outcomes = sorted(run_id for run_id in latest if run_id not in run_ids)
    by_outcome = {name: 0 for name in ALLOWED_OUTCOMES}
    for row in matched:
        outcome = row.get("outcome")
        if outcome in by_outcome:
            by_outcome[outcome] += 1
    rejection_notes = [
        row["outcome_note"]
        for row in matched
        if row.get("outcome") == "rejected" and row.get("outcome_note")
    ]
    return {
        "product_version": RELEASE_VERSION,
        "status": "ok",
        "runs_total": len(runs),
        "outcomes_total": len(outcomes),
        "matched": len(matched),
        "unmatched_runs": unmatched_runs,
        "orphan_outcomes": orphan_outcomes,
        "by_outcome": by_outcome,
        "by_goal_type": _bucket_rates(matched, "goal_type"),
        "by_scaffold_context": _bucket_rates(matched, "scaffold_context"),
        "by_decision": _bucket_rates(matched, "decision"),
        "rejection_notes": rejection_notes,
        "runs_path": str(runs_path),
        "outcomes_path": str(outcomes_path),
    }
