<p align="center">
  <img src="assets/mobius-hero.png" alt="Möbius — write the rules before you build an agent" width="100%">
</p>

# Möbius

**Write the rules for an AI agent before anyone writes the agent.**

Möbius is a command-line tool. You give it a sentence describing an agent you want. It writes a spec, flags risky actions, and asks the questions you still need to answer. Then it **stops**.

It does not generate the agent. It does not send mail, call the internet, or change any of your systems.

[![CI](https://img.shields.io/github/actions/workflow/status/erichschmidt/mobius/ci.yml?branch=main&label=CI)](https://github.com/erichschmidt/mobius/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

```bash
pip install -e .    # from this repo; PyPI publish is optional
mobius "Build an agent that writes a weekly digest of local project notes"
```

---

## If you are new to building agents

An **agent** is software that can act for you: read files, send messages, change records, run on a schedule.

Coding assistants make that sound easy. You type a sentence. They start writing code.

That is where most agent projects go wrong. The interesting part is not the code. It is the agreement nobody wrote down:

| Question | Why it has to be written down |
|---|---|
| When does it run? | Manual, weekly, or always-on are different products with different risk. |
| What may it read and write? | “Local notes” is a start. “Everything I can access” is not a permission. |
| What is forbidden? | “Don’t do anything bad” cannot be enforced. |
| Who approves mistakes? | A message sent to the wrong person cannot be unsent. |
| What counts as success? | Without criteria you cannot tell whether it worked or only looked busy. |

When those answers are missing, the assistant **guesses**. You get folders of plausible code before anyone agreed what the agent is allowed to do.

Möbius is the step that is usually skipped: lock the contract first.

---

## What you get

For a typical first run like the weekly digest, Möbius will decide `needs_interview` — not because it failed, but because the sentence left most of those questions open.

You get:

1. A **decision**: `needs_interview` (answer more questions), `spec_ready` (the contract is complete and local-only), or `human_approval_required` (the idea includes a risky action that a person must approve).
2. A short **brief** — decision, risk, next step, and the questions still open.
3. Files under `.mobius/` you can read, resume, and share.

You do **not** get a running agent.

| File | What it is |
|---|---|
| `.mobius/runs/<id>_brief.md` | The short brief |
| `.mobius/runs/<id>_mobius_spec.md` | The full write-up of this run |
| `.mobius/specs/<id>_mobius_spec.json` | The same spec as JSON |
| `.mobius/checkpoints/<id>_checkpoint.json` | Saved answers so you can resume |
| `.mobius/history/runs.jsonl` | One line per run |

The terminal prints JSON with `decision`, `risk_level`, `recommended_next_action`, and `brief_path`.

---

## Install and first run

```bash
git clone https://github.com/erichschmidt/mobius.git
cd mobius
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

mobius --doctor
mobius "Build an agent that writes a weekly digest of local project notes"
```

`--doctor` checks that the install works and that writes stay inside `.mobius/`.

Saying “build an agent” is enough. Möbius treats that as an agent idea and runs **intake only**: classify the request, score risk, interview, write files, exit.

To finish the intake, answer the twelve questions (goal, trigger, inputs, outputs, tools, memory, cadence, human gate, risk boundary, success criteria, verification plan, registration path) and resume:

```bash
mobius --resume-checkpoint .mobius/checkpoints/<id>_checkpoint.json \
  --answers-json examples/weekly-digest-answers.json
```

[`examples/weekly-digest-answers.json`](examples/weekly-digest-answers.json) is a complete, local-only answer set you can copy.

After a run you can record whether the brief helped:

```bash
mobius --record-outcome <run_id> --outcome accepted
mobius --learning-report
```

---

## How a run works

Möbius is a fixed sequence of steps, not a chat. It does not improvise extra actions.

1. Classify the goal (code, writing, research, …) and the setting (`internal`, `client_work`, `public_repo`, …).
2. Draft a working spec: objective, non-goals, success criteria.
3. Detect risky actions in your words — send, publish, production writes, credentials — and keep the evidence for each.
4. If this is an agent idea, run the twelve-question intake. Incomplete answers stay `needs_interview`. Risky requested actions stay `human_approval_required`.
5. Write the brief, the spec, and a checkpoint. **Stop.**

```text
your sentence → classify + spec + risk + interview if needed → decision → files → exit
```

---

## What Möbius will not do

By default Möbius will not:

- build, deploy, or turn on an agent
- send mail, post publicly, buy anything, or contact anyone
- read your mail or other accounts
- call the network
- change files outside `.mobius/`

A few optional flags exist for local test retries and explicit patches. They are off unless you pass them. Read the brief before using any of them.

---

## Requirements

- Python **3.11+**
- [LangGraph](https://github.com/langchain-ai/langgraph) ≥ 0.2 (installed automatically)

---

## Status

**1.0.0** — spec, interview, stop. That is the product.

---

## Documentation

- [Architecture](docs/architecture.md)
- [Agent intake](docs/agent_intake.md) — the twelve questions, risk rules, and artifacts
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

---

## License

MIT — see [LICENSE](LICENSE).
