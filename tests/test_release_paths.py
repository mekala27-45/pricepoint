"""Installed command modules discover a checkout without writing into site-packages."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.paths import project_root


def checkout(path: Path) -> Path:
    path.mkdir()
    (path / "pyproject.toml").write_text('[project]\nname = "pricepoint"\n', encoding="utf-8")
    (path / "config").mkdir()
    (path / "config/data.json").write_text("{}", encoding="utf-8")
    (path / "artifacts").mkdir()
    return path


def test_installed_wheel_uses_validated_current_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRICEPOINT_ROOT", raising=False)
    source = tmp_path / "site-packages/scripts/paths.py"
    working = checkout(tmp_path / "project")
    assert project_root(cwd=working, source_file=source) == working.resolve()


def test_explicit_root_overrides_current_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    working = checkout(tmp_path / "working")
    explicit = checkout(tmp_path / "explicit")
    monkeypatch.setenv("PRICEPOINT_ROOT", str(explicit))
    assert project_root(cwd=working) == explicit.resolve()


def test_invalid_explicit_root_fails_without_silent_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    working = checkout(tmp_path / "working")
    monkeypatch.setenv("PRICEPOINT_ROOT", str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="PRICEPOINT_ROOT"):
        project_root(cwd=working)


def test_source_checkout_fallback_works_from_another_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRICEPOINT_ROOT", raising=False)
    source_root = checkout(tmp_path / "source")
    assert (
        project_root(cwd=tmp_path, source_file=source_root / "scripts/paths.py")
        == source_root.resolve()
    )


def test_wheel_without_project_has_actionable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRICEPOINT_ROOT", raising=False)
    with pytest.raises(ValueError, match="installed wheels do not contain runtime artifacts"):
        project_root(cwd=tmp_path, source_file=tmp_path / "site-packages/scripts/paths.py")


def test_other_python_project_is_not_mistaken_for_pricepoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRICEPOINT_ROOT", raising=False)
    other = checkout(tmp_path / "other")
    (other / "pyproject.toml").write_text('[project]\nname = "unrelated"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Project files were not found"):
        project_root(cwd=other, source_file=tmp_path / "site-packages/scripts/paths.py")
