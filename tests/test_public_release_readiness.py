from __future__ import annotations

from pathlib import Path

import tomllib

from mobius import graph as mobius


def test_readme_is_public_release_ready():
    text = Path("README.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "private prototype" not in lower
    assert "if you are new to building agents" in lower
    assert "weekly digest of local project notes" in lower
    assert "does not generate the agent" in lower or "do **not** get a running agent" in lower
    assert "PUBLIC_RELEASE_REVIEW.md" not in text
    assert "remains **private**" not in text
    assert "inbox" not in lower
    assert "img.shields.io/github/actions/workflow/status/erichschmidt/mobius/ci.yml" in text
    assert "img.shields.io/badge/CI-passing-brightgreen.svg" not in text
    for leftover in ("hermey", "hermes", "silica", "agent foundry", "consciousness"):
        assert leftover not in lower, leftover


def test_changelog_documents_current_release():
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "## [2.0.0]" in text
    assert "## [1.0.0]" in text
    assert "initial public release" in lower
    assert "### removed" in lower  # 2.0.0 removed the execution flags
    assert "prior development" not in lower
    for leftover in ("hermey", "hermes", "silica", "consciousness", "arrowrock", "cybercamp", "surefire"):
        assert leftover not in lower, leftover


def test_public_docs_avoid_foundry_product_name():
    for path in (
        Path("README.md"),
        Path("docs/README.md"),
        Path("docs/architecture.md"),
        Path("docs/agent_intake.md"),
    ):
        text = path.read_text(encoding="utf-8").lower()
        assert "agent foundry" not in text, path
        assert "inbox" not in text, path


def test_public_release_checklist_not_shipped():
    assert not Path("PUBLIC_RELEASE_REVIEW.md").exists()


def test_pyproject_declares_langgraph_dependency():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert any("langgraph" in dep for dep in deps)
    assert data["project"]["version"] == "2.0.0"


def test_product_contract_has_no_internal_tool_names():
    state = mobius.define_product_contract({})
    contract = state["product_contract"]
    assert "Hermes" not in contract["operating_contract"]
    assert "Hermey" not in contract["operating_contract"]
    assert contract["stability"] == "stable"
    assert contract["product_version"] == "2.0"


def test_contributing_is_public_ready():
    text = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "private repository" not in text.lower()
    assert "pytest" in text


def test_no_hermey_references_in_source_tree():
    hits: list[str] = []
    for path in Path("src").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".json"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "hermey" in text.lower():
                hits.append(str(path))
    assert hits == []


def test_weekly_digest_example_exists():
    payload = Path("examples/weekly-digest-answers.json").read_text(encoding="utf-8")
    assert "weekly digest" in payload.lower()
    assert "local" in payload.lower()
    assert not Path("examples/foundry-safe-answers.json").exists()
    assert not Path("docs/agent_foundry.md").exists()
    assert Path("docs/agent_intake.md").is_file()


PERSONAL_OR_INTERNAL_TERMS = (
    "hermes", "hermey", "arrowrock", "surefire", "cybercamp", "sparkworks",
    "notes-first-reasoning", "business-idea-validation", "claude-design",
)


def test_source_has_no_personal_or_internal_names():
    hits = []
    for path in Path("src").rglob("*.py"):
        lower = path.read_text(encoding="utf-8").lower()
        hits += [f"{path}: {term}" for term in PERSONAL_OR_INTERNAL_TERMS if term in lower]
    assert hits == []


def test_report_and_brief_headings_never_say_foundry(tmp_path, monkeypatch):
    app = tmp_path / ".mobius"
    for name, sub in (("DEFAULT_REPORT_DIR", "runs"), ("DEFAULT_SPEC_DIR", "specs"),
                      ("DEFAULT_CHECKPOINT_DIR", "checkpoints"), ("DEFAULT_HISTORY_DIR", "history")):
        monkeypatch.setattr(mobius, name, app / sub)
    monkeypatch.setattr(mobius, "APP_DIR", app)
    monkeypatch.setattr(mobius, "RUN_HISTORY_PATH", app / "history" / "runs.jsonl")
    state = mobius.run_graph("Build an agent that writes a weekly digest of local project notes", "internal", run_id="headings")
    for key in ("report_path", "brief_path"):
        text = Path(state[key]).read_text(encoding="utf-8")
        headings = [line for line in text.splitlines() if line.startswith("#")]
        assert headings and not [h for h in headings if "foundry" in h.lower()], key
