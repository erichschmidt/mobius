#!/usr/bin/env python3
"""CLI wrapper for Möbius."""
from __future__ import annotations

import argparse
import json
import sys

from typing import Any

from . import assist as model_assist
from . import foundry
from . import graph as module
from . import interview
from . import operator_surface


def _say(text: str) -> None:
    print(text, file=sys.stderr)


def _ask(prompt: str) -> str:
    # Prompts go to stderr so stdout stays clean JSON.
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def _effective_inputs(objective: str, context: str | None, answers: dict[str, Any], resume_checkpoint: str | None):
    """What the run will see: checkpoint values first, overridden by this invocation."""
    if resume_checkpoint:
        data = foundry.load_resume_checkpoint(resume_checkpoint)
        objective = objective.strip() or str(data.get("objective") or "")
        context = context if context is not None else data.get("context_hint")
        answers = foundry.validate_answers({**data.get("answers", {}), **answers})
    objective, context = foundry.validate_text_inputs(objective, context)
    foundry.reject_secret_values(objective, context, answers)
    return objective, context, answers


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Möbius — turn a vague agent idea into a spec, then stop. "
                    "It never runs commands or edits your files, and it only calls the network "
                    "if you pass --assist.",
    )
    parser.add_argument("objective", nargs="?", help="What you want an agent to do, in a sentence")
    parser.add_argument("--context", default=None, help="Optional context hint, e.g. internal, client_work, public_repo")
    parser.add_argument("--answers-json", default=None, help="JSON file with answers to the agent-intake questions")
    parser.add_argument("--resume-checkpoint", default=None, help="Resume and merge answers into a prior Möbius checkpoint")
    parser.add_argument("--agent-intake", action="store_true",
                        help="Treat the objective as an agent idea and run the intake interview")
    # Deprecated alias for --agent-intake, kept so older commands keep working.
    parser.add_argument("--foundry", action="store_true", dest="agent_intake", help=argparse.SUPPRESS)
    parser.add_argument("--record-outcome", default=None, metavar="RUN_ID",
                        help="Append an accept/edit/reject/ignored outcome for an existing run_id")
    parser.add_argument("--outcome", default=None, choices=list(operator_surface.ALLOWED_OUTCOMES),
                        help="Outcome recorded by --record-outcome")
    parser.add_argument("--note", default="", help="Optional note stored with --record-outcome")
    parser.add_argument("--learning-report", action="store_true",
                        help="Print acceptance rates joined from runs.jsonl and outcomes.jsonl")
    parser.add_argument("--doctor", action="store_true", help="Check the install and that writes stay inside .mobius/")
    parser.add_argument("--no-input", action="store_true",
                        help="Never ask questions in the terminal; just write the brief and exit")
    parser.add_argument("--assist", action="store_true",
                        help="Ask Claude to draft answers and flag risks (sends your sentence and answers "
                             "to the Anthropic API; needs pip install 'mobius[assist]')")
    args = parser.parse_args()

    outcome_requested = bool(args.record_outcome or args.learning_report)
    if args.learning_report and args.record_outcome:
        parser.error("--learning-report and --record-outcome are mutually exclusive")
    if args.outcome and not args.record_outcome:
        parser.error("--outcome requires --record-outcome")
    if args.note and not args.record_outcome:
        parser.error("--note requires --record-outcome")
    if args.record_outcome and not args.outcome:
        parser.error("--record-outcome requires --outcome")
    if outcome_requested and args.doctor:
        parser.error("outcome/learning-report mode is exclusive from doctor mode")
    if outcome_requested and (args.objective or args.resume_checkpoint or args.agent_intake):
        parser.error("outcome/learning-report mode is exclusive from objective and agent-intake modes")
    if args.assist and (outcome_requested or args.doctor):
        parser.error("--assist only applies to agent intake runs")
    if args.record_outcome:
        try:
            result = operator_surface.record_outcome(
                args.record_outcome,
                args.outcome,
                args.note,
                history_dir=module.DEFAULT_HISTORY_DIR,
                app_dir=module.APP_DIR,
            )
        except (OSError, ValueError) as exc:
            print(f"mobius: outcome input rejected: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.learning_report:
        try:
            result = operator_surface.build_learning_report(
                history_dir=module.DEFAULT_HISTORY_DIR,
                app_dir=module.APP_DIR,
            )
        except (OSError, ValueError) as exc:
            print(f"mobius: learning report rejected: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.doctor:
        result = module.run_doctor()
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "pass" else 1
    if not args.objective and not args.resume_checkpoint:
        parser.error("objective is required unless --doctor or --resume-checkpoint is passed")
    try:
        answers = foundry.validate_answers(foundry.read_bounded_json(args.answers_json)) if args.answers_json else {}
        objective, context, known = _effective_inputs(args.objective or "", args.context, answers, args.resume_checkpoint)
        intake_mode = bool(args.agent_intake or args.answers_json or args.resume_checkpoint or foundry.is_agent_request(objective))
        if args.assist and not intake_mode:
            parser.error("--assist only applies to agent ideas; add --agent-intake")
        assist = None
        if args.assist:
            _say("mobius: asking Claude for suggestions (--assist)...")
            assist = model_assist.request_suggestions(objective, context, known)
            if assist["status"] != "ok":
                _say(f"mobius: --assist {assist['status']}: {assist.get('error')}. Continuing without it.")
        if intake_mode and not args.no_input and sys.stdin.isatty() and sys.stderr.isatty():
            answers = interview.run_interview(objective, context, known, ask=_ask, say=_say, assist=assist)
        state = module.run_graph(
            args.objective or "",
            args.context,
            answers=answers,
            resume_checkpoint=args.resume_checkpoint,
            foundry_mode=True if intake_mode else None,
            assist=assist,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"mobius: input rejected: {exc}\n")
    print(module.summarize_for_cli(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
