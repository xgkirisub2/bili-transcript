# Security Policy

## Sensitive data

`~/.bili-transcript/config/credentials.json` contains Bilibili login cookies (`SESSDATA`, `bili_jct`, `DedeUserID`, etc.). Treat it like a password:

- It lives outside the repository; never copy it into the repo or commit it.
- Do not paste it into issues, pull requests, screenshots, or logs.
- Do not share it with anyone, including the maintainers.
- Delete it and run `bili-transcript login` again if it may have leaked.

The rest of the project does not collect telemetry or send data to third parties. Transcripts and optional audio stay in `~/.bili-transcript/data/`.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting (Security Advisories) on the repository, or contact the maintainer at the email listed in `pyproject.toml`.

Include:

- a description of the issue;
- steps to reproduce;
- affected version/commit;
- any suggested fix.

## Scope

This is an unofficial client for Bilibili web APIs. It does not bypass paywalls or access controls; it only uses endpoints available to a normal logged-in browser session. Reports about Bilibili's own service should go to Bilibili.

## No warranty

The software is provided under the MIT License, without warranty. You are responsible for complying with Bilibili's terms of service and local copyright law.
