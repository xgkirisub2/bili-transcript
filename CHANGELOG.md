# Changelog

## 0.1.0 — 2026-10-21

Initial open-source release.

- `bili-transcript` CLI: subtitle-first Bilibili transcript fetching, with AI-conclusion and audio-only ASR fallbacks.
- QR-code login with cross-domain ticket handling; optional cookie-string fallback.
- Local faster-whisper transcription with CUDA detection and CPU fallback.
- Timestamped `transcript.txt`, segment-level `transcript.json`, `transcript.srt`, and metadata.
- Bundled Claude Code / Codex skill; `install-skill --all` installs to `~/.claude/skills`, `~/.codex/skills`, and `~/.agents/skills`.
- Data lives in `~/.bili-transcript/`, outside the repository.
- Per-BV/page cache; ASR audio deleted by default.
- Locked default configuration and unit tests.
- Cost/performance notes in `docs/cost-analysis.md`.
