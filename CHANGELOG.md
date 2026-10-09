# Changelog

All notable changes to Möbius are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

[2.0.0]: https://github.com/erichschmidt/mobius/releases/tag/v2.0.0
[1.0.0]: https://github.com/erichschmidt/mobius/releases/tag/v1.0.0
