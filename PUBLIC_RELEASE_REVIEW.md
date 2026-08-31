# Public release review checklist

Use this checklist before and immediately after changing GitHub repository visibility to **public**.

## Security (required)

- [ ] Run a **full git-history secret scan** (`gitleaks`, `trufflehog`, or GitHub secret scanning after visibility flip).
- [ ] Confirm [SECURITY.md](SECURITY.md) reporting path works (enable GitHub private vulnerability reporting).
- [ ] Verify wheel-only install: `pip install dist/mobius-1.0.0-*.whl && mobius --doctor` (no extra deps).
- [ ] Confirm `langgraph>=0.2` appears in wheel `Requires-Dist` metadata (CI checks this).
- [ ] Read patch boundaries in README: default lane stays under `.mobius/`; `--self-patch` is opt-in on `src/mobius/`.

## Repository hygiene

- [x] Fresh public history: single root commit on a new empty GitHub repository (no prior PRs, branches, or private commits).
- [ ] Confirm no `.env`, keys, tokens, client data, or internal hostnames in tracked files.
- [ ] Confirm `.gitignore` covers `.mobius/`, build artifacts, and secrets.

## Legal and metadata

- [ ] Confirm [LICENSE](LICENSE) copyright holder is correct.
- [ ] Decide whether to publish to PyPI under the `mobius` name (may conflict with existing packages — check first).
- [ ] Update `pyproject.toml` `authors` and `[project.urls]` if needed.

## Product decisions

- [ ] **Self-patch lane** (`--self-patch`) is opt-in and loud. Confirm you want it in the public tree.
- [ ] Confirm v1 scope matches your expectations: spec, intake interview, stop.

## Verification (run locally)

```bash
python -m pip install -e '.[dev]'
pytest -q
mobius --doctor
python -m build --wheel

# Wheel-only smoke (matches CI)
python -m venv /tmp/mobius-wheel-test
/tmp/mobius-wheel-test/bin/pip install dist/mobius-1.0.0-*.whl
/tmp/mobius-wheel-test/bin/mobius --doctor
```

Expected: all tests pass, doctor passes, wheel builds as `mobius-1.0.0-*.whl`, wheel install doctor passes without manual LangGraph install.

## Documentation pass

- [ ] Read [README.md](README.md) as a first-time visitor — especially "If you are new to building agents".
- [ ] Skim [docs/README.md](docs/README.md), [docs/architecture.md](docs/architecture.md), and [docs/agent_intake.md](docs/agent_intake.md).

## GitHub settings (when ready)

- [ ] Set repository description and topics (`ai-agents`, `governance`, `langgraph`, `safety`).
- [ ] Enable **Private vulnerability reporting** (Settings → Code security and analysis).
- [ ] Enable Issues (optional).
- [ ] Add branch protection on `main` (require CI).
- [ ] Change visibility: **Settings → General → Danger zone → Change visibility → Public**.

## After going public

- [x] README CI badge uses live workflow status (shields.io GitHub Actions badge).
- [ ] Tag `v1.0.0` and create a GitHub Release with [CHANGELOG.md](CHANGELOG.md) excerpt.
- [ ] Publish to PyPI if desired (`twine upload dist/*`).
- [ ] Announce with clear boundaries: spec-only default, no autonomous execution.

---

**Status:** v1.0.0 ready for public visibility. Flip visibility in GitHub Settings when the checklist above is complete.
