#!/usr/bin/env python3
"""CLI wrapper for Möbius."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import foundry
from . import graph as module
from . import operator_surface


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Möbius — turn a vague agent idea into a spec, then stop",
    )
    parser.add_argument("objective", nargs="?", help="Raw objective to turn into a Mobius loop spec")
    parser.add_argument("--context", default=None, help="Optional context hint, e.g. internal, client_work, public_repo")
    parser.add_argument("--execute-local", action="store_true", help="Run allowlisted local worker commands inside the Mobius app root")
    parser.add_argument("--worker-command", action="append", default=[], help="Allowlisted worker command; may be repeated")
    parser.add_argument("--execute-patch", action="store_true", help="Apply one exact allowlisted local patch before verification")
    parser.add_argument("--patch-file", default=None)
    parser.add_argument("--patch-old", default=None)
    parser.add_argument("--patch-new", default=None)
    parser.add_argument("--patch-description", default="")
    parser.add_argument("--execute-rollback", action="store_true")
    parser.add_argument("--execute-post-rollback-verify", action="store_true")
    parser.add_argument("--post-rollback-command", action="append", default=[])
    parser.add_argument("--propose-patch", action="store_true")
    parser.add_argument("--approve-patch", action="store_true")
    parser.add_argument("--approve-rollback", action="store_true")
    parser.add_argument("--bounded-loop", action="store_true", help="Alias for --keep-going")
    parser.add_argument("--keep-going", action="store_true",
                        help="After a ready spec, retry allowlisted local tests a few times, then stop")
    parser.add_argument("--execute-change-set", action="store_true")
    parser.add_argument("--approve-change-set", action="store_true")
    parser.add_argument("--change-set-json", default=None)
    parser.add_argument("--self-patch", action="store_true",
                        help="Self-patch lane: patch files under src/mobius/ only, "
                             "with mandatory full-suite verification and a clean git tree required")
    parser.add_argument("--answers-json", default=None, help="JSON file containing Foundry interview answers")
    parser.add_argument("--resume-checkpoint", default=None, help="Resume and merge answers into a prior Mobius checkpoint")
    parser.add_argument("--foundry", action="store_true", help="Treat the objective as an agent idea and run spec-only intake")
    parser.add_argument("--record-outcome", default=None, metavar="RUN_ID",
                        help="Append an accept/edit/reject/ignored outcome for an existing run_id")
    parser.add_argument("--outcome", default=None, choices=list(operator_surface.ALLOWED_OUTCOMES),
                        help="Outcome recorded by --record-outcome")
    parser.add_argument("--note", default="", help="Optional note stored with --record-outcome")
    parser.add_argument("--learning-report", action="store_true",
                        help="Print acceptance rates joined from runs.jsonl and outcomes.jsonl")
    parser.add_argument("--doctor", action="store_true")
    args = parser.parse_args()

    outcome_requested = bool(args.record_outcome or args.learning_report)
    normal_requested = bool(
        args.objective or args.context or args.execute_local or args.worker_command or
        args.execute_patch or args.patch_file or args.patch_old or args.patch_new or
        args.execute_rollback or args.execute_post_rollback_verify or args.post_rollback_command or
        args.propose_patch or args.approve_patch or args.approve_rollback or args.bounded_loop or args.keep_going or
        args.execute_change_set or args.approve_change_set or args.change_set_json or
        args.self_patch or args.answers_json or args.resume_checkpoint or args.foundry or args.doctor
    )
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
    if outcome_requested and (args.objective or args.resume_checkpoint or args.foundry or args.self_patch):
        parser.error("outcome/learning-report mode is exclusive from objective, Foundry, and patch modes")
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
    if args.self_patch and not (args.execute_patch or args.execute_change_set):
        parser.error("--self-patch requires --execute-patch or --execute-change-set")
    if args.self_patch and not args.propose_patch:
        parser.error("--self-patch requires --propose-patch (explicit proposal before any apply)")
    if args.self_patch and not (args.approve_patch or args.approve_change_set):
        parser.error("--self-patch requires --approve-patch (or --approve-change-set for change sets)")
    if args.self_patch and not args.execute_post_rollback_verify:
        parser.error("--self-patch requires --execute-post-rollback-verify (mandatory full-suite verification)")
    if (args.keep_going or args.bounded_loop) and args.self_patch:
        parser.error("--keep-going cannot be combined with --self-patch")
    if (args.keep_going or args.bounded_loop) and args.foundry:
        parser.error("--keep-going cannot be combined with --foundry")
    if (args.keep_going or args.bounded_loop) and not args.execute_local:
        parser.error("--keep-going requires --execute-local")
    if (args.keep_going or args.bounded_loop) and not args.worker_command:
        parser.error("--keep-going requires --worker-command")
    if args.doctor:
        result = module.run_doctor()
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "pass" else 1
    if not args.objective and not args.resume_checkpoint:
        parser.error("objective is required unless --doctor or --resume-checkpoint is passed")
    patch_request = {}
    if args.execute_patch:
        patch_request = {"file_path": args.patch_file, "old_string": args.patch_old, "new_string": args.patch_new, "description": args.patch_description}
    try:
        change_set_request = foundry.read_bounded_json(args.change_set_json) if args.change_set_json else {}
        answers = foundry.validate_answers(foundry.read_bounded_json(args.answers_json)) if args.answers_json else {}
        state = module.run_graph(
            args.objective or "",
            args.context,
            execute_local=args.execute_local,
            worker_commands=args.worker_command,
            execute_patch=args.execute_patch,
            patch_request=patch_request,
            execute_rollback=args.execute_rollback,
            execute_post_rollback_verify=args.execute_post_rollback_verify,
            post_rollback_commands=args.post_rollback_command,
            propose_patch=args.propose_patch,
            approval_decisions={"patch": args.approve_patch, "rollback": args.approve_rollback, "change_set": args.approve_change_set},
            bounded_loop=args.bounded_loop,
            keep_going=args.keep_going or args.bounded_loop,
            execute_change_set=args.execute_change_set,
            change_set_request=change_set_request,
            answers=answers,
            resume_checkpoint=args.resume_checkpoint,
            foundry_mode=True if (args.foundry or args.answers_json or args.resume_checkpoint) else None,
            self_patch=args.self_patch,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"mobius: input rejected: {exc}\n")
    print(module.summarize_for_cli(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
