"""Möbius v1 Agent Foundry intake, risk, readiness, and artifact helpers.

The Foundry is deliberately spec-only. It classifies requested authority and
writes bounded artifacts; it never builds, registers, schedules, deploys, or
executes the proposed agent.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os
import re
import stat
import unicodedata
import uuid
import fcntl

FOUNDRY_DIMENSIONS = (
    "goal", "trigger", "inputs", "outputs", "tools", "memory", "cadence",
    "human_gate", "risk_boundary", "success_criteria", "verification_plan",
    "registration_path",
)

INTERVIEW_QUESTIONS: dict[str, str] = {
    "goal": "What should this agent accomplish in one sentence?",
    "trigger": "How should it start (manual command, schedule, event, or webhook)?",
    "inputs": "What data or systems may it read? Name paths, inboxes, APIs, or records.",
    "outputs": "What must it produce or send (files, emails, posts)? Draft-only or live?",
    "tools": "Which bounded tools or APIs would it need?",
    "memory": "What may it remember, where should that live, and for how long?",
    "cadence": "How often should it run (one-shot, daily, weekly, always-on)?",
    "human_gate": "When must a human approve before it acts?",
    "risk_boundary": "What is explicitly forbidden (send, publish, delete, production, credentials)?",
    "success_criteria": "How will you know the output is good enough?",
    "verification_plan": "What tests or checks would prove it worked?",
    "registration_path": "Where should the approved runbook or agent record live?",
}

APPROVAL_GATE_QUESTIONS: dict[str, str] = {
    "external_send": "Who may receive outbound messages, and what requires your sign-off before each send?",
    "publish": "What may be published publicly, and who must approve it first?",
    "outreach_contact": "Who may be contacted, through which channels, and with what approval step?",
    "purchase_payment_trade": "Are purchases, payments, or trades ever allowed? If so, under what limits?",
    "credentials_secrets": "Will it handle credentials or secrets? If yes, how are they stored and who may access them?",
    "production_changes": "What production systems may change, and who must approve each change?",
    "destructive_deletion": "What deletions are allowed, and what backup or approval is required first?",
    "system_of_record_writes": "Which systems of record may be written, and what fields or records are in scope?",
    "sensitive_data_access": "What customer or sensitive data may it read, and what privacy boundaries apply?",
    "local_writes": "Which local files or folders may it create or edit?",
}


def interview_question_for_dimension(name: str) -> str:
    return INTERVIEW_QUESTIONS.get(name, f"What should the agent do for `{name}`?")


def interview_questions_for_dimensions(names: list[str]) -> list[str]:
    return [interview_question_for_dimension(name) for name in names]


def interview_question_for_gate(action: str) -> str:
    return APPROVAL_GATE_QUESTIONS.get(
        action,
        f"Resolve the pending approval gate for `{action}`: approve, reject, or narrow scope.",
    )


def interview_questions_for_gates(gates: list[dict[str, Any]]) -> list[str]:
    return [interview_question_for_gate(str(gate.get("action") or "unknown")) for gate in gates]
LIST_DIMENSIONS = {"inputs", "outputs", "tools", "success_criteria", "verification_plan"}
READINESS_DIMENSIONS = (
    "spec_completeness", "safety_readiness", "verification_evidence", "operational_readiness",
)
READINESS_STATUSES = {"not_evaluated", "pass", "fail", "blocked"}
APPROVAL_STATUSES = {"not_required", "pending", "approved", "edited", "rejected", "expired"}
RUNTIME_OPTIONS = {
    "prompt_cron", "script", "langgraph", "kanban", "mcp_worker", "do_not_build_agent",
}
CHECKPOINT_SCHEMA = "mobius.checkpoint.v1.0"
MAX_JSON_BYTES = 1_000_000
MAX_TEXT_CHARS = 8_000
MAX_LIST_ITEMS = 50
MAX_JSON_DEPTH = 12
SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")

ACTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("external_send", r"\b(?:send(?:ing|s)?|email(?:ing|s|ed)?|message(?:s|d|ing)?|deliver(?:ing|ed|s)?|upload(?:ing|ed|s)?)\b"),
    ("publish", r"\b(?:publish(?:ing|ed|es)?|post(?:ing|ed|s)?|make public|publicly release)\b"),
    ("outreach_contact", r"\b(?:outreach|contact(?:ing|ed|s)?|call(?:ing|ed|s)?|prospect(?:ing|ed|s)?|dm(?:ing|s|ed)?)\b"),
    ("purchase_payment_trade", r"\b(?:purchase(?:s|d|ing)?|buy(?:ing|s)?|pay(?:ment|ments|ing|s|ed)?|trade(?:s|d|ing)?|charge(?:s|d|ing)?|transfer(?:s|red|ring)?)\b"),
    ("credentials_secrets", r"\b(?:credential(?:s)?|secret(?:s)?|token(?:s)?|api[ _-]?key(?:s)?|password(?:s)?|private key)\b"),
    ("production_changes", r"\b(?:production|prod\b|deploy(?:ment|ing|ed|s)?|release(?:s|d|ing)?|live system|rotate credentials)\b"),
    ("destructive_deletion", r"\b(?:delete(?:s|d|ing)?|remove(?:s|d|ing)?|destroy(?:s|ed|ing)?|drop(?:s|ped|ping)?|purge(?:s|d|ing)?|truncate(?:s|d|ing)?)\b"),
    ("system_of_record_writes", r"\b(?:writ(?:e|es|ing|ten)|updat(?:e|es|ed|ing)|edit(?:s|ed|ing)?|chang(?:e|es|ed|ing)|modif(?:y|ies|ied|ying)|mutat(?:e|es|ed|ing)|creat(?:e|es|ed|ing)|delet(?:e|es|ed|ing)|sync(?:s|ed|ing)?|push(?:es|ed|ing)?|add(?:s|ed|ing)?|log(?:s|ged|ging)?|set(?:s|ting)?|assign(?:s|ed|ing)?|merg(?:e|es|ed|ing)|import(?:s|ed|ing)?)\b[^.;\n]{0,55}\b(?:hubspot|crm|erp|database|tickets?|customer\s+records?|system\s+of\s+record|source\s+of\s+truth)\b|\b(?:hubspot|crm|erp|database|tickets?|customer\s+records?|system\s+of\s+record|source\s+of\s+truth)\b[^.;\n]{0,55}\b(?:writ(?:e|es|ing|ten)|updat(?:e|es|ed|ing)|edit(?:s|ed|ing)?|chang(?:e|es|ed|ing)|modif(?:y|ies|ied|ying)|mutat(?:e|es|ed|ing)|creat(?:e|es|ed|ing)|delet(?:e|es|ed|ing)|sync(?:s|ed|ing)?|push(?:es|ed|ing)?|add(?:s|ed|ing)?|log(?:s|ged|ging)?|set(?:s|ting)?|assign(?:s|ed|ing)?|merg(?:e|es|ed|ing)|import(?:s|ed|ing)?)\b"),
    ("local_writes", r"\b(?:write(?:s|written|writing)?|save(?:s|d|ing)?|create(?:s|d|ing)?|edit(?:s|ed|ing)?|update(?:s|d|ing)?)\b[^.;\n]{0,40}\b(?:local|file(?:s)?|markdown|json|project folder|disk)\b|\b(?:local|file(?:s)?|markdown|json)\b[^.;\n]{0,30}\b(?:write|save|create|edit|update)\b"),
)
HIGH_RISK_ACTIONS = {
    "external_send", "publish", "outreach_contact", "purchase_payment_trade",
    "credentials_secrets", "production_changes", "destructive_deletion",
    "system_of_record_writes",
}
PROHIBITED_RE = re.compile(
    r"(?:must\s+not|do(?:es)?\s+not|don['’]t|never|forbid(?:den)?|prohibit(?:ed)?|disallow(?:ed)?|not\s+(?:allowed|permitted)\s+to|no\s+(?:external\s+)?(?:action|send|sending|email|post|publish|purchase|contact|credential|production|delete|write))",
    re.IGNORECASE,
)
POST_PROHIBITED_RE = re.compile(
    r"(?:"
    r"\b(?:is|are)\s+(?:strictly\s+)?(?:prohibited|forbidden|disallowed|not\s+(?:allowed|permitted))\b"
    r"|\bnot\s+permitted\s+to\b"
    r"|\bno\s+(?:(?:sending|posting|publishing|contacting|deleting|writing)\s+)?(?:emails?|messages?|posts?|publishing|purchases?|contact|deletions?|writes?)\b"
    r"|\bnothing\s+(?:is|will\s+be|should\s+be|may\s+be)\b"
    r"|\b(?:is|are|will\s+be|should\s+be|must\s+be)\s+not\s+(?:sent|published|emailed|posted|purchased|deleted)\b"
    r"|\bnot\s+(?:sent|published|emailed|posted)\b"
    r")",
    re.IGNORECASE,
)
APPROVAL_RE = re.compile(
    r"(?:ask\s+(?:me\s+)?before|approval\s+(?:is\s+)?required|require(?:s|d)?\s+(?:human\s+)?approval|only\s+after\s+(?:(?:i|human|legal|manager)\s+)?(?:approv(?:al|e)|sign[- ]?off)|subject\s+to\s+approval|with\s+explicit\s+approval|human[- ]gated|before\s+each\s+send|without\s+(?:human\s+|my\s+|explicit\s+)?approval|unless\s+(?:human\s+|explicitly\s+)?approved|approved\s+by\s+(?:a\s+)?(?:human|manager|owner))",
    re.IGNORECASE,
)
MENTION_RE = re.compile(
    r"(?:example|policy example|mention|discuss|describe|document|consider|risk\s+of|whether|possibility\s+of|about|quoted?)",
    re.IGNORECASE,
)
DOUBLE_NEGATION_RE = re.compile(r"(?:don['’]t|do\s+not|never|not)\s+not\s+", re.IGNORECASE)
AGENT_RE = re.compile(r"\b(?:agent|bot|worker|scout|assistant|automation)\b", re.IGNORECASE)
AGENT_CREATION_RE = re.compile(
    r"\b(?:build|create|design|make|set\s*up|launch|instantiate)\b[^.\n]{0,100}\b(?:agent|bot|worker|scout|assistant|automation)\b|\b(?:i\s+)?(?:want|need|would\s+like|am\s+looking\s+for)\b[^.\n]{0,50}\b(?:agent|bot|worker|scout|assistant|automation)\b|^\s*(?:an?\s+)?(?:agent|bot|worker|scout|assistant|automation)\s+(?:that|to|for)\b|^\s*automate\b",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:ghp|github_pat|glpat)-?[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
    re.compile(r"(?i)\b(?:client[_ -]?secret|access[_ -]?token|aws[_ -]?secret[_ -]?access[_ -]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_-]{8,}(?:[._-][A-Za-z0-9_-]{8,}){1,}"),
)

OwnedArtifact = tuple[Path, int, int, int, int]
_ARTIFACT_TRACKER: ContextVar[list[OwnedArtifact] | None] = ContextVar(
    "mobius_artifact_tracker", default=None
)


def is_agent_request(objective: str) -> bool:
    return bool(AGENT_CREATION_RE.search(objective or ""))


def begin_artifact_tracking() -> tuple[Token, list[OwnedArtifact]]:
    owned: list[OwnedArtifact] = []
    return _ARTIFACT_TRACKER.set(owned), owned


def end_artifact_tracking(token: Token) -> None:
    _ARTIFACT_TRACKER.reset(token)


def cleanup_owned_artifacts(owned: list[OwnedArtifact]) -> None:
    """Remove owned entries through their original verified parent directory."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    for path, device, inode, parent_device, parent_inode in reversed(owned):
        dir_fd: int | None = None
        try:
            dir_fd = os.open(path.parent, directory_flags)
            parent = os.fstat(dir_fd)
            if parent.st_dev != parent_device or parent.st_ino != parent_inode:
                continue
            current = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
            if current.st_dev == device and current.st_ino == inode:
                os.unlink(path.name, dir_fd=dir_fd)
        except FileNotFoundError:
            continue
        except OSError:
            continue
        finally:
            if dir_fd is not None:
                os.close(dir_fd)


def validate_run_id(run_id: str) -> str:
    value = unicodedata.normalize("NFKC", str(run_id or ""))
    if not SAFE_RUN_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError("run_id must match [A-Za-z0-9][A-Za-z0-9_-]{0,79}")
    return value


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def _json_depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"JSON nesting exceeds maximum depth {MAX_JSON_DEPTH}")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _json_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _json_depth(child, depth + 1)
    return depth


def _contains_secret(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def reject_secret_values(*values: Any) -> None:
    if any(_contains_secret(value) for value in values if value is not None):
        raise ValueError("secret-looking value detected; remove credentials before Foundry intake")


def validate_text_inputs(objective: Any, context_hint: Any) -> tuple[str, str | None]:
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("objective must be a non-empty string")
    if len(objective) > MAX_TEXT_CHARS:
        raise ValueError(f"objective exceeds {MAX_TEXT_CHARS} characters")
    if "\x00" in objective:
        raise ValueError("objective contains a null byte")
    if context_hint is not None:
        if not isinstance(context_hint, str):
            raise ValueError("context must be a string")
        if len(context_hint) > MAX_TEXT_CHARS:
            raise ValueError(f"context exceeds {MAX_TEXT_CHARS} characters")
        if "\x00" in context_hint:
            raise ValueError("context contains a null byte")
    return objective, context_hint


def validate_answers(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Foundry answers must be a JSON object")
    raw = dict(payload)
    if "answers" in raw:
        nested = raw.pop("answers")
        if not isinstance(nested, dict):
            raise ValueError("answers must be an object")
        nested = dict(nested)
        nested.update(raw)
        raw = nested
    unknown = sorted(set(raw) - set(FOUNDRY_DIMENSIONS))
    if unknown:
        raise ValueError(f"unknown Foundry answer keys: {', '.join(unknown)}")
    _json_depth(raw)
    reject_secret_values(raw)
    clean: dict[str, Any] = {}
    for name, value in raw.items():
        if name in LIST_DIMENSIONS:
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be a string or a list of at most {MAX_LIST_ITEMS} strings")
            normalized = [item.strip() for item in value if item.strip()]
            if any(len(item) > MAX_TEXT_CHARS for item in normalized):
                raise ValueError(f"{name} contains an overlong value")
            clean[name] = normalized
        else:
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            value = value.strip()
            if len(value) > MAX_TEXT_CHARS:
                raise ValueError(f"{name} exceeds {MAX_TEXT_CHARS} characters")
            clean[name] = value
    return clean


def normalize_answers(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Compatibility alias that now performs strict validation."""
    return validate_answers(payload)


def read_bounded_json(path_value: str | Path, *, require_checkpoint: bool = False) -> dict[str, Any]:
    path = Path(path_value)
    if path.is_symlink() or not path.exists() or not path.is_file():
        raise ValueError("input JSON must be an existing regular non-symlink file")
    size = path.stat().st_size
    if size > MAX_JSON_BYTES:
        raise ValueError(f"input JSON exceeds {MAX_JSON_BYTES} bytes")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("input JSON root must be an object")
    _json_depth(payload)
    if require_checkpoint and payload.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError(f"unsupported checkpoint schema: {payload.get('schema_version')!r}")
    return payload


def load_resume_checkpoint(path_value: str | Path) -> dict[str, Any]:
    payload = read_bounded_json(path_value, require_checkpoint=True)
    objective = payload.get("objective")
    context = payload.get("context_hint")
    if not isinstance(objective, str) or (context is not None and not isinstance(context, str)):
        raise ValueError("checkpoint objective/context types are invalid")
    reject_secret_values(objective, context)
    answers = validate_answers(payload.get("answers") or {})
    ignored = sorted(set(payload) & {
        "risk_level", "risk_assessment", "readiness", "runtime_recommendation",
        "approval_gates", "pending_approval_gates", "decision", "agent_spec",
        "agent_spec_paths", "execute_local", "execute_patch", "execute_change_set",
        "execute_rollback", "worker_commands", "patch_request", "change_set_request",
        "report_path", "checkpoint_path", "json_spec_path", "run_id",
    })
    parent_candidate = payload.get("run_id")
    parent_run_id: str | None = None
    if isinstance(parent_candidate, str):
        try:
            parent_run_id = validate_run_id(parent_candidate)
        except ValueError:
            parent_run_id = None
    return {
        "objective": objective,
        "context_hint": context,
        "answers": answers,
        "parent_run_id": parent_run_id,
        "ignored_derived_fields": ignored,
    }


def _field_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value or "")


def _excerpt(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(text.rfind(".", 0, start), text.rfind(";", 0, start), text.rfind("\n", 0, start))
    right_candidates = [p for p in (text.find(".", end), text.find(";", end), text.find("\n", end)) if p >= 0]
    left = max(left + 1, start - radius)
    right = min(right_candidates) + 1 if right_candidates else min(len(text), end + radius)
    return " ".join(text[left:right].strip(" ,").split())


def _classification(text: str, start: int, end: int) -> tuple[str, bool]:
    prefix = text[max(0, start - 110):start]
    tail = text[end:min(len(text), end + 110)]
    nearest_break = max(prefix.rfind(";"), prefix.rfind("."), prefix.rfind("\n"), prefix.lower().rfind(" but "))
    clause_prefix = prefix[nearest_break + 1:] if nearest_break >= 0 else prefix
    suffix_breaks = [position for position in (tail.find(";"), tail.find("."), tail.find("\n"), tail.lower().find(" but ")) if position >= 0]
    clause_suffix = tail[:min(suffix_breaks)] if suffix_breaks else tail
    around = clause_prefix + text[start:end] + clause_suffix
    ambiguous = bool(DOUBLE_NEGATION_RE.search(around))
    if MENTION_RE.search(clause_prefix) and not re.search(r"\b(?:this agent|the agent|it)\b[^.;]{0,30}\b(?:will|must|should|can)\b", clause_prefix, re.IGNORECASE):
        return "mentioned", ambiguous
    if APPROVAL_RE.search(clause_prefix) or APPROVAL_RE.search(clause_suffix) or APPROVAL_RE.search(around):
        return "approval_gated", ambiguous
    if PROHIBITED_RE.search(clause_prefix) or POST_PROHIBITED_RE.search(around):
        return "prohibited", ambiguous
    return "requested", ambiguous


def assess_risk_sources(objective: str, context: str | None, answers: dict[str, Any] | None) -> dict[str, Any]:
    normalized = validate_answers(answers)
    sources: list[tuple[str, str]] = [("objective", objective or "")]
    if context:
        sources.append(("context", context))
    sources.extend((f"answers.{name}", _field_text(value)) for name, value in normalized.items())
    occurrences: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for source_field, text in sources:
        for action, pattern in ACTION_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                classification, ambiguous = _classification(text, match.start(), match.end())
                evidence = _excerpt(text, match.start(), match.end())
                key = (action, classification, source_field, evidence.casefold())
                if key in seen:
                    continue
                seen.add(key)
                occurrences.append({
                    "canonical_action": action,
                    "classification": classification,
                    "source_field": source_field,
                    "evidence": evidence,
                    "ambiguous": ambiguous,
                    # v2.5 compatibility aliases
                    "action": action,
                    "disposition": classification,
                })
    effective: dict[str, dict[str, Any]] = {}
    contradictions: list[dict[str, Any]] = []
    for action, _ in ACTION_PATTERNS:
        items = [item for item in occurrences if item["canonical_action"] == action]
        if not items:
            continue
        classes = {item["classification"] for item in items}
        ambiguous = any(item["ambiguous"] for item in items)
        conflict = ambiguous or ("prohibited" in classes and bool(classes & {"requested", "approval_gated"}))
        if conflict:
            authority = "blocked_conflict"
            contradictions.append({"canonical_action": action, "classifications": sorted(classes), "reason": "Conflicting or ambiguous authority requires human resolution."})
        elif "approval_gated" in classes:
            authority = "approval_gated"
        elif "requested" in classes:
            authority = "requested"
        elif "prohibited" in classes:
            authority = "prohibited"
        else:
            authority = "mentioned"
        effective[action] = {"authority": authority, "source_count": len(items)}
    requested_authority = sorted(action for action, item in effective.items() if item["authority"] in {"requested", "approval_gated", "blocked_conflict"})
    if contradictions or set(requested_authority) & HIGH_RISK_ACTIONS:
        level = "high"
    elif requested_authority:
        level = "medium"
    else:
        level = "low"
    all_text = "\n".join(text for _, text in sources).lower()
    exposure: list[str] = []
    if re.search(r"\b(?:pii|personal\s+data|customer\s+(?:data|records?|information)|client\s+(?:data|records?|information)|crm\s+(?:data|records?|export))\b", all_text):
        exposure.append("customer_data")
    if re.search(r"\b(?:credential|secret|token|password|api\s+key)s?\b", all_text):
        exposure.append("credentials")
    if re.search(r"\b(?:public\s+content|publish|post\s+publicly)\b", all_text):
        exposure.append("public_content")
    if level == "low" and "customer_data" in exposure:
        level = "medium"
    return {
        "version": "mobius.risk_assessment.v1.0",
        "level": level,
        "actions": occurrences,
        "effective_authority": effective,
        "contradictions": contradictions,
        "requested_authority": requested_authority,
        "data_exposure": exposure,
        "basis": "Risk is recomputed from objective, context, and all validated answer fields with source provenance. Prohibitions do not lower affirmative authority; contradictions block.",
    }


def assess_risk(text: str) -> dict[str, Any]:
    """Compatibility wrapper for objective-only callers."""
    return assess_risk_sources(text, None, {})


def _answer_status(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def build_intake(objective: str, context: str | None, answers: dict[str, Any] | None) -> dict[str, Any]:
    normalized = validate_answers(answers)
    dimensions: dict[str, dict[str, Any]] = {}
    inferred: dict[str, Any] = {"goal": objective.strip()} if objective.strip() else {}
    cadence = re.search(r"\b(daily|weekly|monthly|hourly|one[- ]shot|manual|event[- ]driven)\b", objective, re.IGNORECASE)
    if cadence:
        inferred["cadence"] = cadence.group(1).lower().replace("-", "_").replace(" ", "_")
    if APPROVAL_RE.search(objective):
        inferred["human_gate"] = "Objective explicitly requires approval before at least one action."
    if PROHIBITED_RE.search(objective):
        inferred["risk_boundary"] = "Objective contains explicit prohibited actions; see risk evidence."
    for name in FOUNDRY_DIMENSIONS:
        if _answer_status(normalized.get(name)):
            dimensions[name] = {"status": "answered", "value": normalized[name], "source": f"answers.{name}"}
        elif _answer_status(inferred.get(name)):
            dimensions[name] = {"status": "inferred", "value": inferred[name], "source": "objective"}
        else:
            dimensions[name] = {"status": "missing", "value": None, "source": None}
    missing = [name for name, item in dimensions.items() if item["status"] == "missing"]
    return {
        "version": "mobius.foundry_intake.v1.0",
        "objective": objective,
        "context": context,
        "answers": normalized,
        "dimensions": dimensions,
        "completeness": {
            "complete": not missing,
            "answered": [name for name, item in dimensions.items() if item["status"] == "answered"],
            "inferred": [name for name, item in dimensions.items() if item["status"] == "inferred"],
            "missing": missing,
            "resolved_count": len(FOUNDRY_DIMENSIONS) - len(missing),
            "total_count": len(FOUNDRY_DIMENSIONS),
        },
    }


def _canonical_scope(action: str, objective: str, answers: dict[str, Any], revision: int) -> dict[str, Any]:
    return {"action": action, "objective": objective, "answers": answers, "spec_revision": revision}


def _scope_digest(scope: dict[str, Any]) -> str:
    canonical = json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def build_approval_gates(risk: dict[str, Any], answers: dict[str, Any] | None, *, objective: str = "", revision: int = 1) -> list[dict[str, Any]]:
    normalized = validate_answers(answers)
    effective = risk.get("effective_authority") or {}
    gated_actions = sorted(action for action, item in effective.items() if action in HIGH_RISK_ACTIONS and item.get("authority") in {"requested", "approval_gated", "blocked_conflict"})
    if "customer_data" in risk.get("data_exposure", []) and "sensitive_data_access" not in gated_actions:
        gated_actions.append("sensitive_data_access")
        gated_actions.sort()
    gates: list[dict[str, Any]] = []
    for action in gated_actions:
        scope = _canonical_scope(action, objective, normalized, revision)
        digest = _scope_digest(scope)
        gates.append({
            "gate_id": f"approval:{action}:{digest[:12]}",
            "id": f"approval:{action}:{digest[:12]}",
            "action": action,
            "scope_digest": digest,
            "spec_revision": revision,
            "status": "pending",
            "approver": None,
            "approved_at": None,
            "expires_at": None,
            "reason": "Requested or conflicting authority crosses a human approval boundary. Checkpoint-supplied approvals are never trusted.",
        })
    return gates


def select_runtime(intake: dict[str, Any], risk: dict[str, Any], gates: list[dict[str, Any]]) -> dict[str, Any]:
    values = {name: item.get("value") for name, item in intake.get("dimensions", {}).items()}
    text = json.dumps(values, default=str).lower()
    blocked = bool(risk.get("contradictions")) or any(gate["status"] != "approved" for gate in gates)
    if not intake.get("completeness", {}).get("complete"):
        selected, reasons = "do_not_build_agent", ["Intake is incomplete; resolve required dimensions first."]
    elif blocked:
        selected, reasons = "do_not_build_agent", ["Safety or approval state blocks implementation; preserve this as a review-only specification."]
    elif "mcp" in text:
        selected, reasons = "mcp_worker", ["The declared tool boundary explicitly requires an MCP worker."]
    elif any(term in text for term in ("kanban", "project tracking", "issue tracker")):
        selected, reasons = "kanban", ["The workflow is organized around durable project or issue tracking."]
    elif any(term in text for term in ("stateful", "branching", "multi-step", "multi step", "checkpoint")):
        selected, reasons = "langgraph", ["The workflow declares multi-step or stateful orchestration."]
    elif any(term in text for term in ("daily", "weekly", "monthly", "hourly", "cron")) and not any(term in text for term in ("database", "api write", "shell")):
        selected, reasons = "prompt_cron", ["The complete low-risk workflow is recurring and does not require stateful orchestration."]
    else:
        selected, reasons = "script", ["The complete low-risk workflow is deterministic and bounded."]
    return {"selected": selected, "reasons": reasons, "advisory_only": True}


def evaluate_readiness(intake: dict[str, Any], risk: dict[str, Any], gates: list[dict[str, Any]], runtime: dict[str, Any], answers: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    complete = bool(intake.get("completeness", {}).get("complete"))
    unresolved = bool(risk.get("contradictions")) or any(gate["status"] in {"pending", "edited", "rejected", "expired"} for gate in gates)
    readiness = {
        "spec_completeness": {"status": "pass" if complete else "fail", "reason": "All twelve intake dimensions are resolved." if complete else "Required intake dimensions remain missing."},
        "safety_readiness": {"status": "blocked" if unresolved else ("pass" if complete else "not_evaluated"), "reason": "Contradictory authority or approval gates are unresolved." if unresolved else ("Risk boundaries contain no unresolved high-risk authority." if complete else "Safety cannot be finalized until intake is complete.")},
        "verification_evidence": {"status": "not_evaluated", "reason": "A written verification plan is not execution evidence; v1 does not build or test the proposed agent."},
        "operational_readiness": {"status": "blocked" if unresolved else "not_evaluated", "reason": "Möbius v1 is spec-only; operational readiness requires a separate approved build and evidence-producing test phase."},
    }
    assert all(item["status"] in READINESS_STATUSES for item in readiness.values())
    return readiness


def build_agent_spec(run_id: str, objective: str, context: str | None, intake: dict[str, Any], risk: dict[str, Any], gates: list[dict[str, Any]], readiness: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    run_id = validate_run_id(run_id)
    values = {name: item.get("value") for name, item in intake["dimensions"].items()}
    title_source = str(values.get("goal") or objective).strip()
    safety_blocked = readiness["safety_readiness"]["status"] == "blocked"
    return {
        "schema_version": "mobius.agent_spec.v1.0",
        "run_id": run_id,
        "spec_revision": 1,
        "type": "Agent Spec",
        "mode": "foundry_spec_only",
        "status": "blocked" if safety_blocked else "spec_ready",
        "execution_authorized": False,
        "title": title_source.split(".")[0][:100] or f"Agent {run_id}",
        "objective": objective,
        "context": context,
        "goal": values["goal"], "trigger": values["trigger"], "inputs": values["inputs"],
        "outputs": values["outputs"], "tools": values["tools"], "memory": values["memory"],
        "cadence": values["cadence"], "gates": values["human_gate"],
        "risk_boundaries": values["risk_boundary"], "success_criteria": values["success_criteria"],
        "verification": values["verification_plan"], "registration_destination": values["registration_path"],
        "risk_assessment": risk, "approval_gates": gates, "readiness": readiness, "runtime": runtime,
        "limitations": [
            "This artifact is a specification only.",
            "No agent was built, deployed, scheduled, registered, or permitted to take an external action.",
            "The registration destination is declarative data and was not written.",
            "Verification and operational readiness remain unevaluated until a separate approved build/test phase produces evidence.",
        ],
    }


def render_agent_spec_markdown(spec: dict[str, Any]) -> str:
    def block(name: str, value: Any) -> list[str]:
        return [f"## {name}", "", "```json", json.dumps(value, indent=2, ensure_ascii=False), "```", ""]
    lines = [
        f"# Agent Spec: {spec['title']}", "", f"- **Schema:** `{spec['schema_version']}`",
        f"- **Mode:** `{spec['mode']}`", f"- **Status:** `{spec['status']}`",
        f"- **Execution authorized:** `{str(spec['execution_authorized']).lower()}`",
        f"- **Runtime recommendation:** `{spec['runtime']['selected']}`",
        f"- **Risk level:** `{spec['risk_assessment']['level']}`", "",
        "> Spec-only artifact: no build, deployment, schedule, registration, or external action occurred.", "",
    ]
    for name, key in (
        ("Goal", "goal"), ("Trigger", "trigger"), ("Inputs", "inputs"), ("Outputs", "outputs"),
        ("Tools and Permissions", "tools"), ("Memory", "memory"), ("Cadence", "cadence"),
        ("Human Gates", "gates"), ("Safety Boundaries", "risk_boundaries"),
        ("Success Criteria", "success_criteria"), ("Verification Plan", "verification"),
        ("Registration Destination", "registration_destination"), ("Risk Assessment", "risk_assessment"),
        ("Approval Gates", "approval_gates"), ("Readiness", "readiness"),
        ("Runtime Decision", "runtime"), ("Limitations", "limitations"),
    ):
        lines.extend(block(name, spec[key]))
    return "\n".join(lines)


def ensure_artifact_root(directory: Path, app_root: Path) -> Path:
    root = directory.absolute()
    app = app_root.absolute()
    if root != app and app not in root.parents:
        raise ValueError("artifact directory escapes Mobius app root")
    current = app
    if current.exists() and current.is_symlink():
        raise ValueError("Mobius app root must not be a symlink")
    for part in root.relative_to(app).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError("artifact path contains a symlink")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or root.resolve() != root:
        raise ValueError("artifact directory must be a real contained directory")
    return root


def atomic_write_new(path: Path, content: str) -> None:
    """Publish a new artifact without following the target or parent symlink.

    The parent directory is pinned by descriptor for the entire operation. A
    same-directory temporary file is fsynced and hard-linked into place with
    exclusive destination semantics, then the directory entry is fsynced.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    dir_fd = os.open(path.parent, directory_flags)
    temp_name = f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        try:
            existing = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
        fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600, dir_fd=dir_fd)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temp_name, path.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd, follow_symlinks=False)
            published = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
            parent = os.fstat(dir_fd)
            tracker = _ARTIFACT_TRACKER.get()
            if tracker is not None:
                tracker.append((path, published.st_dev, published.st_ino, parent.st_dev, parent.st_ino))
            os.fsync(dir_fd)
        finally:
            try:
                os.unlink(temp_name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
    finally:
        os.close(dir_fd)


PAIR_PUBLICATION_CHECKS = {
    "first_prepared_reopened_exact_bytes": True,
    "second_prepared_reopened_exact_bytes": True,
    "pinned_parent_identity_verified_before_links": True,
    "both_entries_linked_through_pinned_parent": True,
    "pinned_parent_identity_verified_after_links": True,
    "both_published_entries_verified_as_owned_inodes": True,
    "pinned_parent_fsynced": True,
}


def capture_directory_identity(directory: Path) -> tuple[int, int]:
    """Capture a real directory's device/inode identity without following its final component."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(directory, flags)
    except OSError as exc:
        raise ValueError(f"cannot safely pin directory identity: {directory}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"expected a real directory: {directory}")
        return info.st_dev, info.st_ino
    finally:
        os.close(fd)


def capture_contained_directory_identities(
    directory: Path, app_root: Path,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Pin ``app_root`` and traverse to ``directory`` without following descendants."""
    root = directory.absolute()
    app = app_root.absolute()
    if root != app and app not in root.parents:
        raise ValueError("artifact directory escapes Mobius app root")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        app_fd = os.open(app, flags)
    except OSError as exc:
        raise ValueError(f"cannot safely pin app root: {app}") from exc
    current_fd = os.dup(app_fd)
    try:
        app_info = os.fstat(app_fd)
        for component in root.relative_to(app).parts:
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except OSError as exc:
                raise ValueError("artifact path contains a symlink or non-directory component") from exc
            os.close(current_fd)
            current_fd = next_fd
        root_info = os.fstat(current_fd)
        return (app_info.st_dev, app_info.st_ino), (root_info.st_dev, root_info.st_ino)
    finally:
        os.close(current_fd)
        os.close(app_fd)


def publish_artifact_pair(
    directory: Path,
    first_name: str,
    first_content: str,
    second_name: str,
    second_content: str,
    *,
    expected_app_root: Path | None = None,
    expected_app_root_identity: tuple[int, int] | None = None,
    expected_directory_identity: tuple[int, int] | None = None,
) -> dict[str, bool]:
    """Transactionally publish two exact byte snapshots in one pinned directory.

    The pathname must resolve to the directory pinned at entry immediately before
    linking and again after both links. Prepared files are reopened through the
    held descriptor and byte-compared before publication. On every publication
    error, rollback examines and removes only entries owned by this call through
    that same descriptor, even if the original pathname was renamed or replaced.
    """
    names = (first_name, second_name)
    if any(name in {"", ".", ".."} or Path(name).name != name for name in names) or first_name == second_name:
        raise ValueError("artifact names must be distinct non-empty basenames")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    dir_fd = os.open(directory, flags)
    pinned = os.fstat(dir_fd)
    pinned_identity = (pinned.st_dev, pinned.st_ino)
    temp_names: list[str] = []
    owned: list[tuple[str, int, int]] = []

    if expected_directory_identity is not None and pinned_identity != expected_directory_identity:
        os.close(dir_fd)
        raise OSError("artifact directory identity changed before publication")
    if (expected_app_root is None) != (expected_app_root_identity is None):
        os.close(dir_fd)
        raise ValueError("expected app-root path and identity must be supplied together")

    def require_identity(path: Path, expected: tuple[int, int], label: str) -> None:
        pathname_fd: int | None = None
        try:
            pathname_fd = os.open(path, flags)
            current = os.fstat(pathname_fd)
        except OSError as exc:
            raise OSError(f"{label} pathname identity check failed") from exc
        finally:
            if pathname_fd is not None:
                os.close(pathname_fd)
        if (current.st_dev, current.st_ino) != expected:
            raise OSError(f"{label} pathname identity changed")

    def require_pathname_identities() -> None:
        if expected_app_root is not None and expected_app_root_identity is not None:
            current_app, current_directory = capture_contained_directory_identities(
                directory, expected_app_root,
            )
            if current_app != expected_app_root_identity:
                raise OSError("app root pathname identity changed")
            if current_directory != pinned_identity:
                raise OSError("artifact directory pathname identity changed")
            return
        require_identity(directory, pinned_identity, "artifact directory")

    def reopen_exact(temp_name: str, expected: bytes) -> tuple[int, int]:
        fd = os.open(temp_name, os.O_RDONLY | nofollow, dir_fd=dir_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("prepared artifact is not a regular file")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 65_536)
                if not chunk:
                    break
                chunks.append(chunk)
            if b"".join(chunks) != expected:
                raise ValueError("prepared artifact bytes changed before publication")
            return info.st_dev, info.st_ino
        finally:
            os.close(fd)

    try:
        require_pathname_identities()
        for name in names:
            try:
                os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise FileExistsError(f"refusing to overwrite existing artifact: {directory / name}")

        prepared: list[tuple[str, str, int, int]] = []
        for name, content in ((first_name, first_content), (second_name, second_content)):
            expected = content.encode("utf-8")
            temp_name = f".{name}.{uuid.uuid4().hex}.tmp"
            temp_names.append(temp_name)
            fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600, dir_fd=dir_fd)
            try:
                view = memoryview(expected)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short artifact write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            device, inode = reopen_exact(temp_name, expected)
            prepared.append((temp_name, name, device, inode))

        try:
            require_pathname_identities()
            for temp_name, name, device, inode in prepared:
                os.link(temp_name, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd, follow_symlinks=False)
                owned.append((name, device, inode))
            require_pathname_identities()
            for _temp_name, name, device, inode in prepared:
                published = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                if (published.st_dev, published.st_ino) != (device, inode):
                    raise OSError("published artifact inode verification failed")
            os.fsync(dir_fd)
        except Exception:
            for name, device, inode in reversed(owned):
                try:
                    current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == (device, inode):
                        os.unlink(name, dir_fd=dir_fd)
                except FileNotFoundError:
                    pass
            os.fsync(dir_fd)
            raise
        checks = dict(PAIR_PUBLICATION_CHECKS)
        if expected_app_root is not None and expected_directory_identity is not None:
            checks["expected_root_and_directory_identities_verified"] = True
        return checks
    finally:
        for temp_name in temp_names:
            try:
                os.unlink(temp_name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
        os.close(dir_fd)


def append_jsonl_no_follow(path: Path, payload: dict[str, Any]) -> None:
    """Append one locked JSONL record through a pinned, non-symlink path."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow)
    fd: int | None = None
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | nofollow, 0o600, dir_fd=dir_fd)
        if os.fstat(fd).st_nlink != 1:
            raise ValueError("run history must not be a hard-linked file")
        line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            view = memoryview(line)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.fsync(dir_fd)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(dir_fd)


def write_agent_spec(spec: dict[str, Any], directory: Path, app_root: Path | None = None) -> tuple[str, str]:
    run_id = validate_run_id(str(spec["run_id"]))
    root = ensure_artifact_root(directory, app_root or directory.parent)
    json_path = root / f"{run_id}_agent_spec.json"
    markdown_path = root / f"{run_id}_agent_spec.md"
    local_tracking = _ARTIFACT_TRACKER.get() is None
    token: Token | None = None
    owned: list[OwnedArtifact] = []
    if local_tracking:
        token, owned = begin_artifact_tracking()
    try:
        atomic_write_new(json_path, json.dumps(spec, indent=2, ensure_ascii=False))
        atomic_write_new(markdown_path, render_agent_spec_markdown(spec))
    except Exception:
        if local_tracking:
            cleanup_owned_artifacts(owned)
        raise
    finally:
        if token is not None:
            end_artifact_tracking(token)
    return str(json_path), str(markdown_path)


def contract(status: str, risk_level: str) -> dict[str, Any]:
    return {
        "version": "mobius.agent_foundry.v1.0", "status": status,
        "mode": "foundry_spec_only", "execution_authorized": False,
        "front_door": "raw_agent_idea_to_interviewed_agent_spec",
        "purpose": "Produce a truthful, resumable, spec-only Agent Spec before any separately approved build.",
        "interview_dimensions": list(FOUNDRY_DIMENSIONS),
        "dimension_statuses": ["answered", "inferred", "missing"],
        "readiness_dimensions": list(READINESS_DIMENSIONS),
        "readiness_statuses": sorted(READINESS_STATUSES),
        "approval_statuses": sorted(APPROVAL_STATUSES),
        "runtime_options": sorted(RUNTIME_OPTIONS),
        "agent_spec_template": {"frontmatter": {"type": "Agent Spec", "status": "draft", "runtime": None, "risk_level": risk_level, "execution_authorized": False}},
        "build_path_decision_table": {
            "one_model_call": "prompt_cron", "simple_scriptable": "script",
            "multi_step_stateful": "langgraph", "needs_project_tracking": "kanban",
            "mcp_tool_worker": "mcp_worker", "unsafe_or_not_an_agent": "do_not_build_agent",
        },
        "spec_only_boundary": "No building, deployment, scheduling, registration, contacting, publishing, purchasing, or production writes.",
    }
