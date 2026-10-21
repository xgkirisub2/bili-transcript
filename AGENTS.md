# Agent install guide

This repository ships a Python CLI (`bili-transcript`) and a skill for Bilibili video transcript fetching.

> There is no built-in "paste a URL and it silently installs" behavior in Claude Code or Codex. The user must ask you to install the skill and approve the commands. The goal of this file is to make that flow as short as possible.

## 1. Install the CLI

Detect whether the machine has an NVIDIA GPU:

```bash
nvidia-smi
```

- GPU available: install the CUDA extra.
- No GPU / macOS: install the base package.

```bash
# NVIDIA GPU
uv tool install "bili-transcript[cuda] @ git+https://github.com/xgkirisub2/bili-transcript.git"

# CPU / macOS
uv tool install "bili-transcript @ git+https://github.com/xgkirisub2/bili-transcript.git"
```

If `uv` is missing:

- Windows: `winget install --id astral-sh.uv -e`
- macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

If `bili-transcript` is not on PATH, run `uv tool update-shell`, or use `uv tool run bili-transcript ...`.

## 2A. Claude Code

The recommended path is a plugin marketplace (official lifecycle: install, enable, update, uninstall):

```bash
claude plugin marketplace add xgkirisub2/bili-transcript
claude plugin install bili-transcript@bili-transcript --scope user
```

Then reload plugins in the current session (`/reload-plugins`) or restart Claude Code. The skill is available as `/bili-transcript:bili-transcript`, and Claude can also invoke it from its description.

If the `claude` CLI is not available from your shell, ask the user to run these two commands in Claude Code:

```text
/plugin marketplace add xgkirisub2/bili-transcript
/plugin install bili-transcript@bili-transcript
```

Alternatively, copy the skill directly (no plugin lifecycle):

```bash
bili-transcript install-skill --claude
```

This writes `~/.claude/skills/bili-transcript/SKILL.md`.

## 2B. Codex

```bash
bili-transcript install-skill --codex
```

This writes:

- `~/.codex/skills/bili-transcript/SKILL.md`
- `~/.agents/skills/bili-transcript/SKILL.md`

## 3. Verify

```bash
bili-transcript doctor
```

For Claude Code, `claude plugin list` (or `/plugin` in-session) should show `bili-transcript`.

## 4. Login (first use)

Bilibili requires a logged-in session for AI subtitles.

```bash
bili-transcript login --qr-only
```

Show `~/.bili-transcript/config/login_qr.png` to the user, ask them to scan it with the Bilibili mobile app and confirm, then:

```bash
bili-transcript login --poll
```

`login --poll` waits up to 180 seconds. If it expires, generate a new QR code.

## 5. Use

```bash
bili-transcript status
bili-transcript fetch "<BV/URL>" --json
```

The command returns local paths:

- `transcript_txt`
- `transcript_json`
- `transcript_srt`
- `meta_path`
- `transcript_source`
- `partial`
- `timings`

Do not paste the full transcript into chat unless the user asks. Report the paths and a short quality note (subtitle/ASR, complete/partial).

## Scope

The tool only fetches and converts. It does **not** impose a summary format. If the user asks for analysis, read the transcript and decide the structure yourself. Do not write `summary.md` unless the user explicitly asks for it.

## Safety

- Never commit, print, or share `~/.bili-transcript/config/credentials.json`.
- Do not commit downloaded audio, `~/.bili-transcript/data/`, or model files.
- Use the tool for personal study/research and comply with Bilibili's terms and local copyright law.
