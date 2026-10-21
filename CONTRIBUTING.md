# Contributing

Thanks for taking a look. This project is intentionally small: a CLI, a thin Bilibili API layer, a local ASR wrapper, and a Claude Code skill.

## Development setup

```bash
git clone https://github.com/<your-name>/bili-transcript.git
cd bili-transcript
uv sync          # CPU
# or: uv sync --extra cuda
```

Run the unit tests (no network, no model download):

```bash
uv run python -m unittest discover -s tests -v
```

Check the CLI:

```bash
uv run python -m bili_transcript --help
uv run python -m bili_transcript doctor
```

## Guidelines

- Keep the default path fast: **subtitles first, audio only as a fallback**. Do not add a full-video download to the normal flow.
- The tool fetches and converts; do not bake a summary/analysis format into the default skill.
- Do not commit credentials, `~/.bili-transcript/data/`, downloaded media, model files, or `.venv`.
- Preserve the locked defaults in `src/bili_transcript/config.py` unless a benchmark justifies a change. Update `tests/test_core.py` if defaults change.
- User-facing messages may be Chinese or English; keep them clear and actionable.
- Avoid adding heavy dependencies unless they remove a larger dependency or clearly improve reliability.
- If you change Bilibili API behavior, describe the endpoint and add a fallback where possible.

## Pull requests

1. Fork and create a branch.
2. Make the change with a focused diff.
3. Run the unit tests.
4. Describe the motivation, the behavior change, and any manual verification (video URL, timing, subtitle source).
5. Do not include cookies or personal data in logs/screenshots.

## Reporting issues

Include:

- input URL (or a minimal equivalent);
- `bili-transcript doctor` output (remove any credentials);
- whether the video has subtitles;
- the full error message and the relevant `timings` from `--json`.
