"""Install the bundled SKILL.md for Claude Code and Codex."""

from __future__ import annotations

import shutil
from pathlib import Path

SKILL_NAME = "bili-transcript"


def _skill_source() -> Path:
    """Locate the bundled skill in a wheel, or in a source checkout."""
    try:
        from importlib.resources import files

        resource = files("bili_transcript.skills").joinpath("bili-transcript", "SKILL.md")
        path = Path(str(resource))
        if path.is_file():
            return path
    except (ImportError, ModuleNotFoundError, TypeError, FileNotFoundError):
        pass

    # Source checkout: src/bili_transcript/installer.py -> repo root.
    repo_root = Path(__file__).resolve().parents[2]
    fallback = repo_root / "skills" / "bili-transcript" / "SKILL.md"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        "Bundled SKILL.md not found. Reinstall bili-transcript or run from a source checkout."
    )


def install_skill(
    targets: set[str],
    project_dir: Path | None = None,
    custom_dir: Path | None = None,
) -> list[Path]:
    """Copy SKILL.md to the requested agent skill directories.

    Returns the destination directories.
    """
    source = _skill_source()
    home = Path.home()
    destinations: list[Path] = []

    if "claude" in targets:
        destinations.append(home / ".claude" / "skills" / SKILL_NAME)
    if "codex" in targets:
        # Codex reads both the legacy global directory and the newer
        # ~/.agents/skills location; install to both for compatibility.
        destinations.append(home / ".codex" / "skills" / SKILL_NAME)
        destinations.append(home / ".agents" / "skills" / SKILL_NAME)
    if "project" in targets:
        root = project_dir or Path.cwd()
        destinations.append(root / ".claude" / "skills" / SKILL_NAME)
        destinations.append(root / ".codex" / "skills" / SKILL_NAME)
        destinations.append(root / ".agents" / "skills" / SKILL_NAME)
    if custom_dir is not None:
        destinations.append(custom_dir / SKILL_NAME)

    if not destinations:
        raise ValueError("No skill install target selected.")

    for destination in destinations:
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / "SKILL.md")

    return destinations
