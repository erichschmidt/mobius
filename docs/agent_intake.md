# Agent intake

When the objective is an agent idea, Möbius runs a **spec-only intake**. It writes a contract you can resume and review. It does not build, register, schedule, deploy, or run the proposed agent.

The implementation lives in `foundry.py`. That filename is historical. The product name is Möbius; this page is the intake.

## Flow

```text
raw agent idea
→ classify the goal and setting
→ score risk from the objective, context, and answers
→ fill twelve intake questions
→ flag contradictions and approval gates
→ evaluate readiness (mostly “not evaluated” until a later build)
→ write a standalone Agent Spec when every question is answered
→ write checkpoint, brief, and history
→ stop
```

Risk is scored before the Agent Spec so the spec cannot claim “unknown” after the fact.

## The twelve questions

| Field | Question |
|---|---|
| `goal` | What should the agent accomplish? |
| `trigger` | How does it start? |
| `inputs` | What sources or data does it read? |
| `outputs` | What artifact, message, or state should it produce? |
| `tools` | Which tools, APIs, or files would it need? |
| `memory` | What may be retained, and where? |
| `cadence` | One-shot, recurring, always-on, or event-driven? |
| `human_gate` | When must a future implementation stop for approval? |
| `risk_boundary` | What is forbidden or needs a person to approve? |
| `success_criteria` | What makes the output good enough? |
| `verification_plan` | What later evidence would prove it worked? |
| `registration_path` | Where would an approved runbook live? (declarative only — Möbius does not write there) |

Each field is `answered`, `inferred`, or `missing`. Missing fields produce `needs_interview`. No standalone Agent Spec is written until all twelve resolve.

## CLI

```bash
mobius "Build an agent that writes a weekly digest of local project notes" \
  --context internal \
  --answers-json examples/weekly-digest-answers.json
```

Resume a partial intake:

```bash
mobius --resume-checkpoint .mobius/checkpoints/<run>_checkpoint.json \
  --answers-json /path/to/remaining-answers.json
```

A resumed run:

- loads only the objective, context, and validated answers
- ignores checkpoint risk, approvals, readiness, paths, execution flags, and decisions
- merges newly supplied answers
- recomputes every derived field
- gets a new run ID (and records a parent ID when one is safe)

Answer JSON must be a regular file (not a symlink), at most 1 MB. Unknown keys and secret-looking values are rejected before anything is written.

`--foundry` forces intake even if the sentence does not say “agent”. Saying “build an agent” already does that.

## Risk

Each spotted action is recorded with evidence:

```json
{
  "canonical_action": "external_send",
  "classification": "requested",
  "source_field": "answers.outputs",
  "evidence": "Email the customer"
}
```

Classifications: `requested`, `prohibited`, `approval_gated`, `mentioned`.

A prohibition does not erase a request in another field. Conflict becomes `blocked_conflict`, raises risk, and blocks safety readiness.

Covered families: external send/upload, publishing, outreach, purchases, credentials, production changes, destructive deletion, system-of-record writes, local writes.

This is phrase-level matching, not full language understanding. Ambiguous wording should be rewritten.

## Approval gates

High-risk requested, gated, or conflicting authority creates a `pending` gate with a `gate_id` and a SHA-256 `scope_digest`. Changing the scope changes the digest.

Answers cannot self-approve. Approval state stored in a checkpoint is ignored.

## Readiness

| Dimension | Meaning in v1 |
|---|---|
| `spec_completeness` | Passes only when all twelve questions are resolved. |
| `safety_readiness` | Blocks on contradictory or unresolved gated authority. |
| `verification_evidence` | Stays `not_evaluated`. A written plan is not proof a run worked. |
| `operational_readiness` | Stays `not_evaluated` or `blocked`. v1 builds nothing. |

A safe completed intake is `spec_ready`, not `ready_to_execute`. Every Agent Spec has `execution_authorized: false`.

## Runtime recommendation

Exactly one **advisory** runtime is chosen: `prompt_cron`, `script`, `langgraph`, `kanban`, `mcp_worker`, or `do_not_build_agent`.

Incomplete, contradictory, credential-sensitive, or approval-blocked intake selects `do_not_build_agent`. This is advice for a later build. Möbius does not start any of these runtimes.

## Artifact safety

Intake writes stay under `.mobius/`:

- run IDs are allowlisted
- roots and destinations cannot be symlinks
- files are created, never overwritten
- `registration_path` is stored as text only

```text
.mobius/agent_specs/<run>_agent_spec.json
.mobius/agent_specs/<run>_agent_spec.md
.mobius/specs/<run>_mobius_spec.json
.mobius/checkpoints/<run>_checkpoint.json
.mobius/runs/<run>_brief.md
.mobius/runs/<run>_mobius_spec.md
.mobius/history/runs.jsonl
```

## Spec-only enforcement

Intake runs omit patch, change-set, local-worker, and rollback steps. Those functions also return `blocked` if called while the run is in spec-only mode.

An Agent Spec never authorizes a later executor.
