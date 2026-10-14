# Changelog

All notable changes to Möbius are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [2.1.0] - 2026-10-13

Möbius now asks instead of guessing. Risky actions are declared on a checklist, the interview happens in the terminal, and Claude can optionally draft the answers.

### Added

- `capabilities`, a thirteenth intake question: a checklist of what the agent may do (send, publish, contact, move money, handle secrets, change production, delete, write to a system of record, run shell commands, read sensitive data, write local files), or `none`. Declared capabilities are authoritative and gated.
- Risky wording that the checklist does not cover becomes a question that quotes it. Answer by declaring the capability or listing it in the new optional `dismissed_signals` key. Dismissals are recorded and shown in the brief.
- An interactive interview when Möbius runs in a terminal. Press Enter to skip a question. `--no-input` turns it off; scripts and pipes are unchanged.
- `--assist` (opt-in, `pip install 'mobius[assist]'`): one Claude call drafts answers, flags risky actions, and suggests follow-up questions.
  - Findings count only with a verbatim quote, and can only add risk.
  - Drafts stay `suggested` until you accept them, and are also written to `<id>_suggested_answers.json`.
  - The model, request ID, and token usage are recorded.
- New risk wording: shell commands (`shell_commands`), sharing and forwarding, wiring money and refunds, and "after I approve" style approvals.

### Changed

- No runtime dependencies. LangGraph is gone; the fixed steps run in a plain loop.
- Agent requests are classified by what the agent does, so "Build an agent that writes a digest" is `writing`, not `code`.
- Budget and execution-loop sections describe the eventual implementation, not Möbius. Two questions that asked whether Möbius may change files or use metered APIs were reworded.
- `--doctor` no longer starts subprocesses (it used to run `py_compile`, which wrote `__pycache__` outside `.mobius/`).
- The package is marked POSIX-only, which it already was in practice.
- Answer files from 2.0 lack `capabilities`, so they resume as `needs_interview` with that one question open.
- CI now tests Python 3.11–3.14 on Linux and macOS.

### Fixed

- Agent Spec items were never added to `expected_artifacts` (a key renamed in 2.0 was still checked under its old name).
- Mentioning "deep agent" or "decision ledger" rendered empty `{}` sections in the write-up.
- `python -m mobius.graph` crashed on removed arguments; that entry point is gone.

### Removed

- Over 800 lines of 1.0-era code that never ran: venture loop, deep-agent harness, subagent matrix, dashboard and ledger contracts, and an unused two-file publisher.

## [2.0.0] - 2026-10-09

Möbius now does exactly what it says: write the spec, ask the questions, stop. It never runs commands or edits files outside `.mobius/`.

### Removed

- All execution lanes: `--execute-local`, `--worker-command`, `--execute-patch` and the `--patch-*` flags, `--propose-patch`, `--approve-patch`, `--execute-change-set`, `--approve-change-set`, `--change-set-json`, `--execute-rollback`, `--approve-rollback`, `--execute-post-rollback-verify`, `--post-rollback-command`, `--keep-going` / `--bounded-loop`, and `--self-patch`. They were opt-in and allowlisted in 1.0.0, but a tool for writing the rules *before* anyone builds an agent shouldn't carry its own execution loop. They remain available at tag [`v1.0.0`](https://github.com/erichschmidt/mobius/releases/tag/v1.0.0).
- The `ready_to_execute` decision value (it was never produced).
- The patch and worker-command safety probes in `--doctor` (the code they tested is gone).

### Changed

- `--foundry` is now `--agent-intake`. The old flag still works but is hidden.
- Report headings say "Agent Intake", "Approval Gates", and "Readiness".
- Spec JSON: `agent_foundry` is now `agent_intake`; the method ledger lists generic `recommended_practices` instead of tool-specific skill names (schema `mobius.method_basis_ledger.v3.0`).
- Notes-tool categories are now `notes_project` and `notes_only` (`--context obsidian` still works).

## [1.0.0] - 2026-08-31

Initial public release. Write the rules for an AI agent before anyone writes the agent: spec, interview, stop.

### Added

- Agent intake: twelve questions, action-aware risk, resumable checkpoints, and standalone Agent Spec artifacts.
- Operator brief (`_brief.md`) per run with interview and approval-gate questions.
- Spec and checkpoint files under `.mobius/` (JSON + Markdown).
- `--record-outcome` and `--learning-report` for human feedback on briefs.
- `--keep-going`: retry allowlisted local tests a few times, then stop.
- `mobius --doctor` health checks for runtime, CLI, patch boundaries, and artifact safety.
- Opt-in local execution and self-patch lanes (off by default; explicit flags required).

[Unreleased]: https://github.com/erichschmidt/mobius/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/erichschmidt/mobius/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/erichschmidt/mobius/releases/tag/v2.0.0
[1.0.0]: https://github.com/erichschmidt/mobius/releases/tag/v1.0.0
