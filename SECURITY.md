# Security Policy

## Reporting a vulnerability

Please do not open a public issue for suspected vulnerabilities, leaked credentials, private operational data, or other security-sensitive findings.

Until a dedicated private reporting channel is published, repository maintainers should handle security reports through GitHub's private security reporting facilities when enabled.

## Sensitive data

Do not commit or publish:

- `.env` files or live credentials
- Telegram bot tokens or administrator identifiers
- database passwords, dumps, or SQLite data
- private keys, certificates, or access tokens
- operational logs containing private data
- realized-trade datasets or private market datasets
- production host details or deployment secrets

The checked-in `.env.example` is intended to contain placeholders only.

## Scope

This repository is a source release candidate. A security review does not constitute approval for live trading or production deployment.
