# Architecture

```text
your sentence
    → classify / spec / risk / intake interview if this is an agent idea
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
| `graph.py` | Fixed list of steps | A chat agent |
| `foundry.py` | Intake questions, risk, checkpoints | Building or activating an agent |
| `operator_surface.py` | Short brief, outcome log, learning report | Permission to execute |
| `reporting.py` | Markdown write-up of a run | A dump of every internal contract |
| `keep_going.py` | Optional local test retries | Writing new code |

## Files Möbius writes

All default writes stay under `.mobius/` (or `MOBIUS_APP_DIR` if you set it).

- `runs/<id>_brief.md` — the short decision surface
- `runs/<id>_mobius_spec.md` — the full write-up
- `specs/<id>_mobius_spec.json` — machine-readable spec
- `checkpoints/<id>_checkpoint.json` — answers you can resume
- `history/runs.jsonl` — one line per run
- `history/outcomes.jsonl` — your accept/edit/reject/ignored notes

## Safety

The code enforces the boundary. Prompts only describe intent. Default runs do not use the network, send messages, buy anything, or write to production.
