# Architecture

```text
your sentence
    → (optional, --assist) one Claude call: draft answers, flag risks, suggest questions
    → (in a terminal) ask the open intake questions
    → classify / spec / risk / intake if this is an agent idea
    → decision
    → brief + write-up + JSON + checkpoint + history
    → exit

later, if you want:
    --record-outcome <run_id> --outcome accepted|edited|rejected|ignored
    --learning-report
```

## Pieces

| File | Job | Not its job |
|---|---|---|
| `graph.py` | Fixed list of steps, run in order by a plain loop | A chat agent |
| `foundry.py` | Intake questions, capabilities, risk, checkpoints | Building or activating an agent |
| `interview.py` | Asks open questions in the terminal before the run | Writing anything |
| `assist.py` | Opt-in Claude call for drafts and risk findings | Deciding anything: its output is advisory |
| `operator_surface.py` | Short brief, outcome log, learning report | Permission to execute |
| `reporting.py` | Markdown write-up of a run | A dump of every internal contract |

## Files Möbius writes

Every write stays under `.mobius/` (or `MOBIUS_APP_DIR` if you set it).

- `runs/<id>_brief.md` — the short decision surface
- `runs/<id>_mobius_spec.md` — the full write-up
- `specs/<id>_mobius_spec.json` — machine-readable spec
- `checkpoints/<id>_checkpoint.json` — answers you can resume
- `history/runs.jsonl` — one line per run
- `history/outcomes.jsonl` — your accept/edit/reject/ignored notes
- `runs/<id>_suggested_answers.json` — only with `--assist`: drafts to edit and pass back

## Safety

The code enforces the boundary. Prompts only describe intent. Möbius does not run commands, send messages, buy anything, or write anywhere outside its artifact folder, and there is no flag that turns any of that on.

The one exception to "offline" is `--assist`, which you must ask for. It sends your sentence and answers (never files) to the Anthropic API in a single request, and records that in the spec's `side_effects_performed`. What comes back is checked in code: risk findings count only with a verbatim quote and can only add risk, and drafted answers stay `suggested` until you accept them.
