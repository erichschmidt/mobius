"""Ask the agent-intake questions in the terminal before a run.

Uses only pure functions from ``foundry``: nothing is written while the
person answers. The CLI then runs once with whatever they gave. An empty
answer skips a question, and skipped questions stay open in the brief.
"""
from __future__ import annotations

from typing import Any, Callable

from . import foundry

Ask = Callable[[str], str]
Say = Callable[[str], None]

SKIP_WORDS = {"-", "skip"}


class _EndOfInput(Exception):
    """The person closed input (Ctrl-D); stop asking and keep what we have."""


def run_interview(
    objective: str,
    context: str | None,
    answers: dict[str, Any] | None,
    *,
    ask: Ask,
    say: Say,
    assist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``answers`` plus whatever the person filled in."""
    answers = foundry.validate_answers(answers)
    suggestions = dict((assist or {}).get("draft_answers") or {})
    findings = list((assist or {}).get("capabilities") or [])
    intake = foundry.build_intake(objective, context, answers)
    missing = intake["completeness"]["missing"]
    if missing:
        say(f"\nMöbius intake: {len(missing)} open question(s). Press Enter to skip one.\n")
    try:
        for name in missing:
            if name == "capabilities":
                suggested = sorted({str(item.get("action")) for item in findings} & set(foundry.CAPABILITIES))
                value = _ask_capabilities(ask, say, suggested)
            else:
                value = _ask_dimension(name, suggestions.get(name), ask, say)
            if value is not None:
                answers[name] = value
        _confirm_signals(objective, context, answers, findings, ask, say)
    except _EndOfInput:
        say("\nInput closed; running with the answers so far.")
    return foundry.validate_answers(answers)


def _read(ask: Ask, prompt: str) -> str:
    try:
        return ask(prompt).strip()
    except EOFError:
        raise _EndOfInput from None


def _ask_dimension(name: str, suggestion: Any, ask: Ask, say: Say) -> Any:
    say(foundry.interview_question_for_dimension(name))
    is_list = name in foundry.LIST_DIMENSIONS
    if is_list:
        say("  (separate several items with ';')")
    if suggestion:
        shown = "; ".join(suggestion) if isinstance(suggestion, list) else str(suggestion)
        say(f"  suggested: {shown}")
        say("  (Enter accepts the suggestion; '-' skips)")
    while True:
        raw = _read(ask, "> ")
        if raw.lower() in SKIP_WORDS or (not raw and not suggestion):
            return None
        value: Any = suggestion if not raw else ([part.strip() for part in raw.split(";") if part.strip()] if is_list else raw)
        try:
            return foundry.validate_answers({name: value})[name]
        except ValueError as exc:
            say(f"  Not accepted: {exc}. Try again, or press '-' to skip.")


def _ask_capabilities(ask: Ask, say: Say, suggested: list[str]) -> list[str] | None:
    say("Which of these may the agent do?")
    for number, action in enumerate(foundry.CAPABILITIES, 1):
        say(f"  {number:>2}. {foundry.CAPABILITY_LABELS[action]}")
    say("Enter the numbers that apply (e.g. '1 4'), '0' for none of them, or Enter to skip.")
    if suggested:
        numbers = " ".join(str(foundry.CAPABILITIES.index(action) + 1) for action in suggested)
        say(f"  suggested from your description: {numbers}  (type them to accept)")
    while True:
        raw = _read(ask, "> ")
        if not raw or raw.lower() in SKIP_WORDS:
            return None
        if raw == "0":
            return [foundry.NO_CAPABILITIES]
        try:
            picked = []
            for token in raw.replace(",", " ").split():
                picked.append(foundry.CAPABILITIES[int(token) - 1] if token.isdigit() and int(token) >= 1 else token)
            return foundry.validate_answers({"capabilities": picked})["capabilities"]
        except (ValueError, IndexError) as exc:
            say(f"  Not accepted: {exc}. Use numbers from the list.")


def _confirm_signals(
    objective: str,
    context: str | None,
    answers: dict[str, Any],
    findings: list[dict[str, Any]],
    ask: Ask,
    say: Say,
) -> None:
    """Ask about risky wording the declared capabilities do not cover."""
    if answers.get("capabilities") is None:
        return
    risk = foundry.assess_risk_sources(objective, context, answers, model_findings=findings)
    asked: set[str] = set()
    for signal in risk["unconfirmed_signals"]:
        action = signal["canonical_action"]
        if action in asked:
            continue
        asked.add(action)
        say(f'\nYour description says "{signal["evidence"]}".')
        raw = _read(ask, f"Will the agent {foundry.CAPABILITY_LABELS[action]}? [y/n, Enter to leave open] ").lower()
        if raw in {"y", "yes"}:
            declared = [item for item in answers["capabilities"] if item != foundry.NO_CAPABILITIES]
            answers["capabilities"] = [*declared, action]
        elif raw in {"n", "no"}:
            answers["dismissed_signals"] = [*answers.get("dismissed_signals", []), action]
