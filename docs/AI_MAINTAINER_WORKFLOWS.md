# AI-Assisted Maintainer Workflows

AI coding tools may assist project maintenance, but repository safety and review rules remain authoritative.

## Appropriate uses

Examples include:

- pull-request review assistance;
- regression-test suggestions;
- failure triage;
- dependency-update review;
- migration review;
- documentation synchronization;
- release-note drafting;
- security-oriented code review;
- narrowly scoped maintenance automation.

## Guardrails

AI-generated changes are not trusted by default. They must follow the same review, test, provenance, security, and release gates as human-written changes.

AI tools must not:

- receive or publish live credentials or private operational data;
- bypass publication or release gates;
- silently alter frozen-source identity;
- treat generated output as evidence of trading profitability;
- autonomously enable live-trading behavior;
- replace required human authorization for production-impacting operations.

## Intended Codex use

For maintainer workflows, Codex would be most useful where repository context is large and changes need cross-file review: PR analysis, test generation, regression investigation, release validation, documentation consistency, dependency review, and security hardening.

The purpose is to reduce open-source maintenance burden while keeping human review and repository controls in charge.
