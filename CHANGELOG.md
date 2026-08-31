# Changelog

All notable changes to Möbius are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

[1.0.0]: https://github.com/erichschmidt/mobius/releases/tag/v1.0.0
