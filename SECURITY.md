# Security Policy

Möbius writes inspectable specs under `.mobius/`. It does not contact third parties, read your mail, run commands, or change files outside `.mobius/`.

## Supported versions

| Version | Supported |
|---------|-----------|
| 2.0.x   | Yes       |
| 1.0.x   | Security fixes only |
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

Version 2.0.0 removed every execution path (local commands, patches, change sets, rollbacks, the keep-going loop, and self-patching). If you find a way to make Möbius run a command or write outside `.mobius/`, that is a vulnerability. Please report it.

## Scope notes

- Möbius is spec-only. There are no execution flags.
- 1.0.x shipped opt-in, allowlisted execution lanes (including `--self-patch`); they are not present in 2.x.
