"""Logika bezpiecznego udostępniania zasobów graficznych."""

import logging
from pathlib import Path


ASSETS_ROOT = Path("trener_biegowy_ai_assets")
ASSET_MEDIA_TYPE = "image/png"
ALLOWED_CATEGORIES = frozenset(
    {
        "01_navigation",
        "02_health_status",
        "03_activity",
        "07_ui_icons",
        "09_illustrations",
        "10_sports_weather",
    }
)

LOGGER = logging.getLogger(__name__)


def build_manifest(root: Path | None = None) -> dict[str, Path]:
    """Buduje białą listę obrazów PNG z dozwolonych katalogów."""
    assets_root = ASSETS_ROOT if root is None else root
    manifest: dict[str, Path] = {}

    for category in ALLOWED_CATEGORIES:
        category_path = assets_root / category
        try:
            entries = category_path.iterdir()
            for entry in entries:
                if entry.is_file() and entry.suffix.lower() == ".png":
                    manifest[f"{category}/{entry.name}"] = entry.resolve()
        except OSError as error:
            LOGGER.warning("Nie można odczytać katalogu zasobów %s: %s", category_path, error)

    return manifest


def resolve_asset(reference: str, manifest: dict[str, Path]) -> Path | None:
    """Zwraca istniejący obraz wskazany dokładnym kluczem manifestu."""
    if (
        ".." in reference
        or "\\" in reference
        or "\x00" in reference
        or reference.startswith("/")
        or not reference.endswith(".png")
    ):
        return None

    asset_path = manifest.get(reference)
    if asset_path is None or not asset_path.is_file():
        return None

    return asset_path
