from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re

import tomllib

from mobius import graph as mobius

# SHA-256 digests of internal and personal names that must never appear in
# the public tree. Stored as digests so this test does not publish them.
BANNED_NAME_DIGESTS = {
    "8cfde6efdfc4ed5ab1f6acbbd1ba49bf31932f84d0a4c090eb41c7d151e8b180",
    "8eafc0d5167a45068548d5a6716562201e07c8ce7bc17ddd14efda50ca326b14",
    "603fec46699c2950a1d3bea6c79a5eaf7702ce6e2fd51cf2971e3ffa7abce359",
    "003a7a99f8dc0add83b823f6c3bdff93822b97116104d8c073aaf9cf55e0835f",
    "325faa539bfe7d79207f708fd4518b387b2c1c304f416c8b07712b07c70aa950",
    "a73e673b1e218a9d5c84aaed87dce52e3db3ee3b9e7ccac01e03109138bbc772",
    "753d0ada3a49e073e067d99c9744a219d37248a7fe1684cd5d03ea793f17c462",
    "719b215830254ae3cfc5afffb214b3e22d5118eaadefd74290ba9d645416747f",
    "b82ae2a303b7f90be222def503dfe488600951f0a749590d4261feaa0262cf2c",
    "ad276f0fc10748a12664242f2b991de2b34b50e721bac41057cebb9bc562031e",
    "538ac7d510ce10e2977b7ef4c62a336150687f1d3e34a6df8c33e0cdaaccde1c",
}


def banned_names_in(text: str, digests: set[str] = BANNED_NAME_DIGESTS) -> list[str]:
    tokens = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()))
    # Also try each hyphen-separated part, so "foo-bar" catches a banned "foo".
    tokens |= {part for token in tokens for part in token.split("-")}
    return sorted(token for token in tokens if sha256(token.encode()).hexdigest() in digests)


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
    assert "agent foundry" not in lower
    assert banned_names_in(text) == []


def test_changelog_documents_current_release():
    text = Path("CHANGELOG.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "## [2.0.0]" in text
    assert "## [1.0.0]" in text
    assert "initial public release" in lower
    assert "### removed" in lower  # 2.0.0 removed the execution flags
    assert "prior development" not in lower
    assert banned_names_in(text) == []


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


def test_pyproject_has_no_runtime_dependencies_and_matches_package_version():
    from mobius import __version__

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"].get("dependencies", []) == []
    assert "langgraph" not in Path("pyproject.toml").read_text(encoding="utf-8")
    assert data["project"]["version"] == __version__


def test_contributing_is_public_ready():
    text = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "private repository" not in text.lower()
    assert "pytest" in text




def test_weekly_digest_example_exists():
    payload = Path("examples/weekly-digest-answers.json").read_text(encoding="utf-8")
    assert "weekly digest" in payload.lower()
    assert "local" in payload.lower()
    assert not Path("examples/foundry-safe-answers.json").exists()
    assert not Path("docs/agent_foundry.md").exists()
    assert Path("docs/agent_intake.md").is_file()


def test_public_tree_has_no_personal_or_internal_names():
    paths = [*Path("src").rglob("*.py"), *Path("src").rglob("*.json"), *Path("docs").rglob("*.md"),
             *Path("examples").rglob("*.json"), *Path("tests").rglob("*.py"),
             Path("README.md"), Path("CONTRIBUTING.md"), Path("SECURITY.md"), Path("pyproject.toml")]
    hits = []
    for path in paths:
        hits += [str(path) for _ in banned_names_in(path.read_text(encoding="utf-8"))]
    assert hits == []


def test_banned_name_check_catches_words_and_hyphenated_parts():
    canary = {sha256(b"canary").hexdigest()}
    assert banned_names_in("a Canary sang", canary) == ["canary"]
    assert banned_names_in("the canary-yellow wall", canary) == ["canary"]
    assert banned_names_in("canaries are birds", canary) == []


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
