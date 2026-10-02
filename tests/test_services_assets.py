"""Testy białej listy lokalnych zasobów graficznych."""

from pathlib import Path

from services.assets import build_manifest, resolve_asset


def create_file(path: Path) -> Path:
    """Tworzy pusty plik wraz z katalogiem nadrzędnym."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_manifest_collects_only_allowed_categories(tmp_path: Path) -> None:
    allowed = create_file(tmp_path / "01_navigation" / "home.png")
    create_file(tmp_path / "05_ui_charts" / "chart.png")

    manifest = build_manifest(tmp_path)

    assert manifest == {"01_navigation/home.png": allowed.resolve()}


def test_manifest_skips_non_png_files(tmp_path: Path) -> None:
    create_file(tmp_path / "01_navigation" / "home.txt")
    create_file(tmp_path / "01_navigation" / "home.svg")
    image = create_file(tmp_path / "01_navigation" / "home.PNG")

    assert build_manifest(tmp_path) == {"01_navigation/home.PNG": image.resolve()}


def test_manifest_returns_empty_for_missing_root(tmp_path: Path) -> None:
    assert build_manifest(tmp_path / "nie_istnieje") == {}


def test_resolve_asset_returns_path_for_valid_key(tmp_path: Path) -> None:
    image = create_file(tmp_path / "01_navigation" / "home.png")
    manifest = build_manifest(tmp_path)

    assert resolve_asset("01_navigation/home.png", manifest) == image.resolve()


def test_resolve_asset_rejects_invalid_references(tmp_path: Path) -> None:
    manifest = {"01_navigation/home.png": create_file(tmp_path / "home.png")}

    references = (
        "01_navigation/missing.png",
        "../01_navigation/home.png",
        "/01_navigation/home.png",
        "01_navigation\\home.png",
        "01_navigation/home.svg",
    )

    for reference in references:
        assert resolve_asset(reference, manifest) is None


def test_resolve_asset_rejects_file_outside_manifest(tmp_path: Path) -> None:
    outside = create_file(tmp_path / "01_navigation" / "outside.png")

    assert resolve_asset("01_navigation/outside.png", {}) is None
    assert outside.is_file()


def test_resolve_asset_rejects_path_traversal(tmp_path: Path) -> None:
    manifest = {"01_navigation/home.png": create_file(tmp_path / "home.png")}

    assert resolve_asset("01_navigation/../../../etc/passwd", manifest) is None


def test_resolve_asset_returns_none_for_deleted_file(tmp_path: Path) -> None:
    image = create_file(tmp_path / "01_navigation" / "home.png")
    manifest = build_manifest(tmp_path)
    image.unlink()

    assert resolve_asset("01_navigation/home.png", manifest) is None
