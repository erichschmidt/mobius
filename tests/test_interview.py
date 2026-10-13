from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobius import cli
from mobius import foundry
from mobius import graph as mobius
from mobius import interview

OBJECTIVE = "Build an agent that writes a weekly digest of local project notes"
LOCAL_WRITES = str(foundry.CAPABILITIES.index("local_writes") + 1)


def scripted(replies):
    """An ask() that plays back replies and raises EOFError when they run out."""
    replies = list(replies)
    prompts: list[str] = []

    def ask(prompt):
        prompts.append(prompt)
        if not replies:
            raise EOFError
        return replies.pop(0)

    return ask, prompts


def run(replies, answers=None, assist=None, objective=OBJECTIVE):
    ask, _ = scripted(replies)
    said: list[str] = []
    result = interview.run_interview(objective, "internal", answers or {}, ask=ask, say=said.append, assist=assist)
    return result, "\n".join(said)


def isolate_runtime(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app / "history")
    monkeypatch.setattr(mobius, "DEFAULT_AGENT_SPEC_DIR", app / "agent_specs")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")


# Replies for every open question of OBJECTIVE, in FOUNDRY_DIMENSIONS order
# (goal and cadence are inferred from the sentence, so they are not asked).
FULL_REPLIES = [
    "Manual command every Friday.",                                  # trigger
    "local Markdown notes in the project folder",                    # inputs
    "a local Markdown digest in the project folder",                 # outputs
    "read-only filesystem",                                          # tools
    LOCAL_WRITES,                                                    # capabilities
    "Keep only the latest digest in the project folder.",            # memory
    "A person reads the local draft. Nothing is sent or published.", # human_gate
    "Never send, publish, purchase, or access credentials.",         # risk_boundary
    "Every active project appears; first run; a second run",         # success_criteria
    "Read the digest back from disk.",                               # verification_plan
    "docs/agents/weekly-digest.md",                                  # registration_path
]


def test_full_interview_resolves_every_dimension():
    answers, _ = run(FULL_REPLIES)
    intake = foundry.build_intake(OBJECTIVE, "internal", answers)
    assert intake["completeness"]["complete"] is True
    assert answers["capabilities"] == ["local_writes"]
    assert answers["success_criteria"] == ["Every active project appears", "first run", "a second run"]


def test_enter_skips_and_skipped_questions_stay_open():
    answers, _ = run([""] * 20)
    intake = foundry.build_intake(OBJECTIVE, "internal", answers)
    assert "trigger" in intake["completeness"]["missing"]
    assert "capabilities" not in answers


def test_end_of_input_keeps_answers_so_far():
    answers, said = run(["Manual command every Friday."])
    assert answers == {"trigger": "Manual command every Friday."}
    assert "Input closed" in said


def test_zero_declares_no_capabilities_and_bad_numbers_are_asked_again():
    replies = ["", "", "", "", "99", "0"]
    answers, said = run(replies)
    assert answers["capabilities"] == ["none"]
    assert "Not accepted" in said


def test_invalid_text_answer_is_rejected_and_asked_again():
    answers, said = run(["token: sk-abcdefghijklmnopqrstuvwxyz123456", "Manual command."])
    assert answers["trigger"] == "Manual command."
    assert "secret-looking" in said


@pytest.mark.parametrize(("reply", "declared", "dismissed"), [
    ("y", ["external_send"], None),
    ("n", ["none"], ["external_send"]),
    ("", ["none"], None),
])
def test_wording_the_checklist_does_not_cover_is_confirmed_or_dismissed(reply, declared, dismissed):
    objective = "Build an agent that summarizes the Slack channel and shares it with the team"
    answers, said = run(["0", reply], answers={**_all_but("capabilities")}, objective=objective)
    assert "shares it with the team" in said
    assert answers["capabilities"] == declared
    assert answers.get("dismissed_signals") == dismissed


def test_model_suggestions_are_offered_and_enter_accepts_them():
    assist = {"status": "ok", "draft_answers": {"trigger": "Manual command."}, "capabilities": []}
    answers, said = run(["", "-"], assist=assist)
    assert answers["trigger"] == "Manual command."
    assert "suggested: Manual command." in said
    assert "inputs" not in answers


def test_suggested_capabilities_are_shown_but_not_taken_without_typing():
    assist = {"status": "ok", "draft_answers": {}, "capabilities": [{"action": "local_writes", "evidence": "writes"}]}
    answers, said = run([""] * 4 + [""], assist=assist)
    assert f"suggested from your description: {LOCAL_WRITES}" in said
    assert "capabilities" not in answers


def _all_but(*skip):
    payload = json.loads(Path("examples/weekly-digest-answers.json").read_text(encoding="utf-8"))
    return {key: value for key, value in payload.items() if key not in skip}


def test_cli_never_prompts_without_a_terminal(tmp_path, monkeypatch, capsys):
    isolate_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("prompted without a terminal"))
    monkeypatch.setattr("sys.argv", ["mobius", OBJECTIVE, "--context", "internal"])
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "needs_interview"


def test_cli_no_input_skips_the_interview_even_in_a_terminal(tmp_path, monkeypatch, capsys):
    isolate_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("prompted despite --no-input"))
    monkeypatch.setattr("sys.argv", ["mobius", OBJECTIVE, "--context", "internal", "--no-input"])
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "needs_interview"


def test_cli_interview_in_a_terminal_reaches_spec_ready(tmp_path, monkeypatch, capsys):
    isolate_runtime(tmp_path, monkeypatch)
    replies = iter(FULL_REPLIES)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    monkeypatch.setattr("sys.argv", ["mobius", OBJECTIVE, "--context", "internal"])
    assert cli.main() == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["decision"] == "spec_ready"
    assert summary["agent_spec"]
    assert "open question" in captured.err
