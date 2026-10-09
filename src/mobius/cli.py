#!/usr/bin/env python3
"""CLI wrapper for Möbius."""
from __future__ import annotations

import argparse
import json
import sys

from . import foundry
from . import graph as module
from . import operator_surface


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Möbius — turn a vague agent idea into a spec, then stop. "
                    "It never runs commands, edits your files, or calls the network.",
    )
    parser.add_argument("objective", nargs="?", help="What you want an agent to do, in a sentence")
    parser.add_argument("--context", default=None, help="Optional context hint, e.g. internal, client_work, public_repo")
    parser.add_argument("--answers-json", default=None, help="JSON file with answers to the agent-intake questions")
    parser.add_argument("--resume-checkpoint", default=None, help="Resume and merge answers into a prior Möbius checkpoint")
    parser.add_argument("--agent-intake", action="store_true",
                        help="Treat the objective as an agent idea and run the twelve-question intake")
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
        state = module.run_graph(
            args.objective or "",
            args.context,
            answers=answers,
            resume_checkpoint=args.resume_checkpoint,
            foundry_mode=True if (args.agent_intake or args.answers_json or args.resume_checkpoint) else None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"mobius: input rejected: {exc}\n")
    print(module.summarize_for_cli(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
