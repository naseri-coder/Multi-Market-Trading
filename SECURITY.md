# Security Policy

## Supported status

This repository is a public development snapshot. It is intended for source review, testing, and isolated installation. It is not approved for production or live trading.

## Reporting a vulnerability

Do **not** open a public issue for suspected vulnerabilities, leaked credentials, private operational data, or other security-sensitive findings.

Use GitHub private vulnerability reporting when it is enabled for this repository. If private reporting is unavailable, do not publish sensitive details in an issue or pull request; contact the repository owner through a private channel first.

## Sensitive data

Never commit, attach, or publish:

- populated `.env` files or live credentials
- Telegram bot tokens or administrator identifiers
- database passwords, dumps, or SQLite data
- private keys, certificates, or access tokens
- operational logs containing private data
- realized-trade datasets or private market datasets
- production host details or deployment secrets

The checked-in `.env.example` must contain placeholders only.

## Security boundaries

The publication CI performs conservative tracked-file and credential-pattern checks, but those checks are not a substitute for GitHub secret scanning, dependency review, code scanning, or a dedicated security assessment.

A successful CI run does not constitute approval for production deployment, live trading, or the handling of real credentials and funds.
