# bili-transcript

Bilibili video transcript fetching and conversion. The CLI fetches subtitles first; only videos without subtitles fall back to audio-only ASR. It does not impose an analysis or summary format.

## Defaults (locked)

- Subtitles first; never download the full video for a transcript.
- ASR: `large-v3-turbo`, `device=auto`, `language=zh`.
- Audio stream priority: `30216`; avoid the slow `30232` stream.
- Delete audio after a successful ASR run; `--keep-audio` retains it.
- Fetch the official Bilibili AI conclusion as auxiliary material when subtitles exist.
- Cache by BV/page. `--json` includes `timings`.

Defaults live in `src/bili_transcript/config.py` (`DEFAULT_*`, `AUDIO_STREAM_PRIORITY`) and are locked by `tests/test_core.py`.

## Install (for agents)

Repository: <https://github.com/xgkirisub2/bili-transcript>

```bash
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"   # NVIDIA GPU
# or: uv tool install "bili-transcript @ git+https://github.com/xgkirisub2/bili-transcript.git"   # CPU / macOS
```

Claude Code plugin marketplace:

```bash
claude plugin marketplace add xgkirisub2/bili-transcript
claude plugin install bili-transcript@bili-transcript --scope user
```

Then `/reload-plugins` or restart Claude Code. The skill appears as `/bili-transcript:bili-transcript`.

Direct skill copy (Claude Code / Codex):

```bash
bili-transcript install-skill --claude
bili-transcript install-skill --codex
bili-transcript install-skill --all
```

`install-skill --all` writes the skill to `~/.claude/skills`, `~/.codex/skills`, and `~/.agents/skills`.

Verify with `bili-transcript doctor`.

## Commands

```bash
bili-transcript status
bili-transcript login
bili-transcript info "<BV/URL>"
bili-transcript fetch "<BV/URL>" --json
bili-transcript install-skill --all
```

Source checkout:

```bash
uv sync --extra cuda   # or uv sync
uv run python -m bili_transcript doctor
uv run python -m unittest discover -s tests -v
```

## Key files

- `src/bili_transcript/cli.py` — CLI and `install-skill`.
- `src/bili_transcript/extract.py` — metadata, subtitles, AI conclusion, audio download.
- `src/bili_transcript/auth.py` — QR login and cross-domain cookie handling.
- `src/bili_transcript/asr.py` — faster-whisper wrapper.
- `src/bili_transcript/installer.py` — skill installation for Claude Code / Codex.
- `skills/bili-transcript/SKILL.md` — canonical skill file.
- `docs/cost-analysis.md` — measured time/storage/cost breakdown.

## Safety

- `~/.bili-transcript/config/credentials.json` contains Bilibili cookies. Never read, print, or commit it.
- Do not commit `~/.bili-transcript/data/`, downloaded media, `.venv`, or model files.
