# Contributing

Thanks for your interest in Möbius. This project is intentionally conservative about autonomy and safety — contributions should preserve those boundaries.

## Before you start

1. Read [`README.md`](README.md) and [`docs/architecture.md`](docs/architecture.md).
2. Run the health check: `mobius --doctor`
3. Run tests: `pytest -q`

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,assist]'
```

Möbius is POSIX-only (Linux, macOS). The `assist` extra is only needed to run `tests/test_assist.py`; those tests use a fake client and never call the network.

From the repo without installing:

```bash
PYTHONPATH=src python -m mobius.cli --doctor
PYTHONPATH=src pytest -q
```

## Pull requests

- Keep changes focused. One concern per PR when possible.
- Add or update tests for behavior changes.
- Do not commit secrets, credentials, client data, or personal host paths.
- Preserve default safety: no network unless `--assist` is passed, no production writes, no execution.
- Update [`CHANGELOG.md`](CHANGELOG.md) for user-visible changes.

## What we are unlikely to accept

- Broadening execution authority in the default graph path.
- Removing approval gates or intake interviews for agent creation.
- Network calls, account integrations, or messaging in core flows without explicit opt-in design.

## Security

See [`SECURITY.md`](SECURITY.md). Report vulnerabilities privately to the repository owner — do not open public issues with exploit details or secrets.
