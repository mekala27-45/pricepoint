"""Reject the forbidden character in source, docs and generated text."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".tsx", ".ts", ".css", ".html", ".txt", ".svg"}


def violations(root: Path, paths: list[str]) -> list[str]:
    found: list[str] = []
    for name in paths:
        path = root / name
        if path.is_file() and (path.suffix in TEXT_SUFFIXES or not path.suffix):
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if chr(0x2014) in content:
                found.append(name)
    return found


def main() -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    bad = violations(ROOT, tracked)
    if bad:
        raise SystemExit("Forbidden punctuation: " + ", ".join(bad))
    print("Punctuation gate passed")


if __name__ == "__main__":
    main()
