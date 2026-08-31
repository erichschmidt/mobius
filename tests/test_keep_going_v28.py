from __future__ import annotations

from mobius import graph as mobius
from mobius import keep_going


def isolate_runtime(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "DEFAULT_REPORT_DIR", app / "runs")
    monkeypatch.setattr(mobius, "DEFAULT_SPEC_DIR", app / "specs")
    monkeypatch.setattr(mobius, "DEFAULT_CHECKPOINT_DIR", app / "checkpoints")
    monkeypatch.setattr(mobius, "DEFAULT_HISTORY_DIR", app / "history")
    monkeypatch.setattr(mobius, "DEFAULT_AGENT_SPEC_DIR", app / "agent_specs")
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")


def test_should_run_skips_when_disabled():
    action, reason = keep_going.should_run({"keep_going": False})
    assert action == "skip"
    assert "not enabled" in reason


def test_should_run_blocks_interview_and_missing_commands():
    action, _ = keep_going.should_run({
        "keep_going": True,
        "decision": "needs_interview",
        "execute_local": True,
        "worker_commands": ["python3 -m py_compile probe.py"],
    })
    assert action == "block"
    action, reason = keep_going.should_run({
        "keep_going": True,
        "decision": "ready_to_execute",
        "execute_local": True,
        "worker_commands": [],
    })
    assert action == "block"
    assert "worker-command" in reason


def test_run_loop_stops_on_same_failure_twice():
    calls = {"n": 0}

    def runner(commands, max_commands, timeout_seconds):
        calls["n"] += 1
        return {"status": "fail", "runs": [{"command": commands[0], "allowed": True, "exit_code": 1}]}

    result = keep_going.run_loop({
        "worker_commands": ["python3 -m py_compile bad.py"],
        "budget_policy": {"max_iterations": 3, "max_worker_runs": 1, "max_minutes": 1, "max_consecutive_failures": 2},
        "verifier_plan": ["compile probe"],
    }, runner)
    assert result["status"] == "stopped"
    assert result["stop_reason"] == "same failure repeats twice"
    assert result["iteration_count"] == 2
    assert calls["n"] == 2


def test_run_loop_completes_on_first_pass():
    def runner(commands, max_commands, timeout_seconds):
        return {"status": "pass", "runs": [{"command": commands[0], "allowed": True, "exit_code": 0}]}

    result = keep_going.run_loop({
        "worker_commands": ["python3 -m py_compile probe.py"],
        "budget_policy": {"max_iterations": 3, "max_worker_runs": 1, "max_minutes": 1},
    }, runner)
    assert result["status"] == "completed"
    assert result["iteration_count"] == 1
    assert result["stop_reason"] == "verifier passed"


def test_keep_going_pass_on_real_local_file(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    app = tmp_path / ".mobius"
    app.mkdir()
    (app / "probe.py").write_text("value = 1\n")
    state = mobius.run_graph(
        "Prepare a bounded local-only smoke test",
        "internal",
        run_id="kg_pass",
        execute_local=True,
        keep_going=True,
        worker_commands=["python3 -m py_compile probe.py"],
    )
    result = state["keep_going_result"]
    assert state["decision"] == "spec_ready"
    assert result["status"] == "completed"
    assert result["iteration_count"] == 1
    assert result["last_worker_result"]["status"] == "pass"
    assert "keep_going_loop" in state.get("side_effects_performed", [])


def test_keep_going_stops_after_repeated_compile_failure(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    app = tmp_path / ".mobius"
    app.mkdir()
    (app / "bad.py").write_text("def broken(\n")
    state = mobius.run_graph(
        "Prepare a bounded local-only smoke test",
        "internal",
        run_id="kg_fail",
        execute_local=True,
        keep_going=True,
        worker_commands=["python3 -m py_compile bad.py"],
    )
    result = state["keep_going_result"]
    assert result["status"] == "stopped"
    assert result["stop_reason"] == "same failure repeats twice"
    assert result["iteration_count"] == 2


def test_keep_going_blocks_when_interview_required(tmp_path, monkeypatch):
    isolate_runtime(tmp_path, monkeypatch)
    app = tmp_path / ".mobius"
    app.mkdir()
    (app / "probe.py").write_text("value = 1\n")
    state = mobius.run_graph(
        "Build a complex app and keep improving it forever",
        "internal",
        run_id="kg_block",
        execute_local=True,
        keep_going=True,
        worker_commands=["python3 -m py_compile probe.py"],
    )
    result = state["keep_going_result"]
    assert result["status"] == "blocked"
    assert result["iteration_count"] == 0
    assert state.get("side_effects_performed") in (None, [])
