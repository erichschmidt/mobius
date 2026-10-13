# Agent intake

When the objective is an agent idea, Möbius runs a **spec-only intake**. It writes a contract you can resume and review. It does not build, register, schedule, deploy, or run the proposed agent.

The implementation lives in `foundry.py`. That filename is historical. The product name is Möbius; this page is the intake.

## Flow

```text
raw agent idea
→ classify the goal and setting
→ score risk from the objective, context, and answers
→ ask the thirteen intake questions (in the terminal, or from an answers file)
→ ask about risky wording the capabilities checklist does not cover
→ flag contradictions and approval gates
→ evaluate readiness (mostly “not evaluated” until a later build)
→ write a standalone Agent Spec when every question and risk signal is resolved
→ write checkpoint, brief, and history
→ stop
```

Risk is scored before the Agent Spec so the spec cannot claim “unknown” after the fact.

## The thirteen questions

| Field | Question |
|---|---|
| `goal` | What should the agent accomplish? |
| `trigger` | How does it start? |
| `inputs` | What sources or data does it read? |
| `outputs` | What artifact, message, or state should it produce? |
| `tools` | Which tools, APIs, or files would it need? |
| `capabilities` | Which risky things may it do? A checklist; see below. |
| `memory` | What may be retained, and where? |
| `cadence` | One-shot, recurring, always-on, or event-driven? |
| `human_gate` | When must a future implementation stop for approval? |
| `risk_boundary` | What is forbidden or needs a person to approve? |
| `success_criteria` | What makes the output good enough? |
| `verification_plan` | What later evidence would prove it worked? |
| `registration_path` | Where would an approved runbook live? (declarative only — Möbius does not write there) |

Each field is `answered`, `inferred`, `suggested`, or `missing`. `suggested` means `--assist` drafted a value that you have not accepted yet; it counts as missing. Missing fields produce `needs_interview`. No standalone Agent Spec is written until all thirteen resolve.

## Capabilities: ask, don't guess

`capabilities` is a list drawn from a fixed vocabulary, or `["none"]`:

| Name | The agent may… |
|---|---|
| `external_send` | send messages or files to anyone (email, chat, uploads) |
| `publish` | publish or post anything publicly |
| `outreach_contact` | contact people (calls, DMs, prospecting) |
| `purchase_payment_trade` | spend, pay, trade, or move money |
| `credentials_secrets` | handle credentials, tokens, or other secrets |
| `production_changes` | deploy or change production systems |
| `destructive_deletion` | delete or remove data or files |
| `system_of_record_writes` | write to a CRM, database, ticket system, or other system of record |
| `shell_commands` | run shell commands or scripts |
| `sensitive_data_access` | read customer, personal, or other sensitive data |
| `local_writes` | create or edit local files |

Declared capabilities are the authority. Everything except `local_writes` gets a pending approval gate.

Möbius still scans your wording. When a phrase suggests a capability you did not declare, it becomes a question that quotes the phrase:

> Your description says "…shares it with the team". Will the agent send messages or files to anyone? If yes, add `external_send` to capabilities; if not, add it to dismissed_signals.

Until you answer, the run stays `needs_interview` and the wording still counts as requested. To answer in a file:

```json
{
  "capabilities": ["local_writes"],
  "dismissed_signals": ["external_send"]
}
```

Dismissals are recorded in the risk assessment (`dismissed_signals`, with the quoted evidence) and listed in the brief. A capability cannot be both declared and dismissed. If you declare a capability that your `risk_boundary` forbids, that is a contradiction and blocks the spec.

Answer files from 2.0 have no `capabilities`, so they resume as `needs_interview` with that one question open.

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

`--agent-intake` forces intake even if the sentence does not say “agent”. Saying “build an agent” already does that. (`--foundry` is an older alias that still works.)

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

Covered families: external send/upload/share, publishing, outreach, purchases and money movement, credentials, production changes, destructive deletion, system-of-record writes, shell commands, local writes.

This is phrase-level matching, not full language understanding. It will miss things and flag harmless phrases, which is why the capabilities checklist is the authority and the wording only raises questions. With `--assist`, Claude's findings are added as `source_field: "model"`, but only when their quoted evidence appears verbatim in your text. Model findings can add risk; they never remove it.

## Approval gates

High-risk requested, gated, or conflicting authority creates a `pending` gate with a `gate_id` and a SHA-256 `scope_digest`. Changing the scope changes the digest.

Answers cannot self-approve. Approval state stored in a checkpoint is ignored.

## Readiness

| Dimension | Meaning in v1 |
|---|---|
| `spec_completeness` | Passes only when all thirteen questions are resolved. |
| `safety_readiness` | Blocks on contradictory or unresolved gated authority; `not_evaluated` while risky wording is unconfirmed. |
| `verification_evidence` | Stays `not_evaluated`. A written plan is not proof a run worked. |
| `operational_readiness` | Stays `not_evaluated` or `blocked`. Möbius builds nothing. |

A safe completed intake is `spec_ready`. Every Agent Spec has `execution_authorized: false`.

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
.mobius/runs/<run>_suggested_answers.json   # only with --assist
.mobius/history/runs.jsonl
```

## Spec-only enforcement

Möbius has no patch, change-set, local-worker, or rollback steps at all. They were removed in 2.0.0, so there is nothing to switch on.

An Agent Spec never authorizes a later executor.
