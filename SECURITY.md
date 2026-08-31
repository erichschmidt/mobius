# Security Policy

Möbius writes inspectable specs under `.mobius/` and, by default, does not contact third parties, read your mail, or change production systems.

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a vulnerability

**Do not** open a public GitHub issue for security-sensitive reports.

Use [GitHub private vulnerability reporting](https://github.com/erichschmidt/mobius/security/advisories/new) if enabled, or email the repository owner privately with:

- A description of the issue and impact.
- Steps to reproduce.
- Whether you believe it enables unauthorized execution, data exfiltration, or sandbox escape.

You will receive an acknowledgment and a timeline for fix or decline.

## Safe use

Do **not** use Möbius to, without explicit human approval and additional review:

- change production systems or customer records;
- handle secrets, credentials, or API keys;
- contact third parties (email, post, trade, purchase);
- perform offensive security work.

Opt-in execution paths (`--execute-local`, `--keep-going`, `--self-patch`, patch flags) are bounded and allowlisted. Read the flags and brief before approving.

## Scope notes

- Möbius v1 is spec-only by default. Execution flags are explicit and loud.
- `--self-patch` modifies the package source tree and requires propose, approve, clean git tree, and full test verification.
