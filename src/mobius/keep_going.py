"""Mobius v2.8 bounded keep-going loop.

After a ready spec, retry allowlisted local verifiers a few times, then stop.
Does not generate code, send messages, touch production, or leave the app root.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

MAX_KEEP_GOING_ITERATIONS = 3
MAX_KEEP_GOING_WORKER_RUNS = 3
MAX_KEEP_GOING_TIMEOUT_SECONDS = 120

WorkerRunner = Callable[[list[str], int, int], dict[str, Any]]


def should_run(state: Mapping[str, Any]) -> tuple[str, str]:
    """Return ('run'|'skip'|'block', reason)."""
    if not state.get("keep_going"):
        return "skip", "keep_going not enabled"
    if state.get("mode") == "foundry_spec_only":
        return "skip", "intake mode is spec-only"
    if state.get("self_patch"):
        return "block", "keep-going cannot be combined with --self-patch"
    decision = state.get("decision")
    if decision not in {"ready_to_execute", "spec_ready"}:
        return "block", f"keep-going blocked by decision `{decision}`"
    if state.get("interview_questions"):
        return "block", "keep-going blocked: interview questions are still open"
    if state.get("pending_approval_gates"):
        return "block", "keep-going blocked: pending approval gates"
    if not state.get("execute_local"):
        return "block", "keep-going requires --execute-local"
    commands = [item for item in (state.get("worker_commands") or []) if str(item).strip()]
    if not commands:
        return "block", "keep-going requires --worker-command"
    return "run", "ok"


def plan_next_task(state: Mapping[str, Any], iteration: int) -> str:
    plan = [str(item) for item in (state.get("verifier_plan") or []) if item]
    criteria = [str(item) for item in (state.get("success_criteria") or []) if item]
    index = iteration - 1
    if 0 <= index < len(plan):
        return plan[index]
    if 0 <= index < len(criteria):
        return criteria[index]
    return f"Run allowlisted verifier (iteration {iteration})"


def _failure_signature(result: Mapping[str, Any]) -> tuple[Any, ...]:
    runs = result.get("runs") or []
    parts = [(run.get("exit_code"), run.get("reason"), run.get("allowed")) for run in runs]
    return (result.get("status"), tuple(parts))


def run_loop(state: Mapping[str, Any], runner: WorkerRunner) -> dict[str, Any]:
    budget = state.get("budget_policy") or {}
    max_iterations = min(int(budget.get("max_iterations", MAX_KEEP_GOING_ITERATIONS)), MAX_KEEP_GOING_ITERATIONS)
    max_worker_runs = min(int(budget.get("max_worker_runs", MAX_KEEP_GOING_WORKER_RUNS)), MAX_KEEP_GOING_WORKER_RUNS)
    timeout_seconds = min(int(budget.get("max_minutes", 45)) * 60, MAX_KEEP_GOING_TIMEOUT_SECONDS)
    max_consecutive = min(int(budget.get("max_consecutive_failures", 2)), 2)
    commands = [str(item) for item in (state.get("worker_commands") or []) if str(item).strip()][:max_worker_runs]

    iterations: list[dict[str, Any]] = []
    last_signature: tuple[Any, ...] | None = None
    consecutive_same = 0
    last_worker: dict[str, Any] = {}
    stop_reason = "max iterations reached without verifier pass"
    status = "stopped"

    for iteration in range(1, max_iterations + 1):
        task = plan_next_task(state, iteration)
        worker = runner(commands, max_worker_runs, timeout_seconds)
        last_worker = worker
        signature = _failure_signature(worker)
        if last_signature is None:
            progress_delta = True
            consecutive_same = 0 if worker.get("status") == "pass" else 1
        elif signature == last_signature:
            progress_delta = False
            consecutive_same += 1
        else:
            progress_delta = True
            consecutive_same = 1 if worker.get("status") != "pass" else 0
        last_signature = signature
        iterations.append({
            "iteration": iteration,
            "task": task,
            "worker_status": worker.get("status"),
            "progress_delta": progress_delta,
            "consecutive_same_failures": consecutive_same,
        })
        if worker.get("status") == "pass":
            status = "completed"
            stop_reason = "verifier passed"
            break
        if worker.get("status") == "blocked":
            status = "blocked"
            first = (worker.get("runs") or [{}])[0]
            stop_reason = str(first.get("reason") or "worker blocked")
            break
        if consecutive_same >= max_consecutive:
            status = "stopped"
            stop_reason = "same failure repeats twice"
            break
        if not progress_delta:
            status = "stopped"
            stop_reason = "no measurable progress after an iteration"
            break
        if iteration == max_iterations:
            status = "stopped"
            stop_reason = "max iterations reached without verifier pass"

    return {
        "status": status,
        "stop_reason": stop_reason,
        "iterations": iterations,
        "iteration_count": len(iterations),
        "max_iterations": max_iterations,
        "last_worker_result": last_worker,
        "commands": commands,
    }
