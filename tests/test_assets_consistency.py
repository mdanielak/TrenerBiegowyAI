"""Testy spójności grafik: deklaracje w szablonach, pliki PNG i oryginały."""

from __future__ import annotations

import re
from pathlib import Path

from api.main import _SIGNAL_META
from services.assets import build_manifest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
ASSETS_DIR = PROJECT_ROOT / "trener_biegowy_ai_assets"
ORIGINALS_DIR = ASSETS_DIR / "_originals"

# Pliki prezentacyjne mają dwukrotność rozmiaru wyświetlania, żeby pozostały
# ostre na ekranach o dużej gęstości pikseli.
MIN_PIXEL_RATIO = 2
# Kadry niekwadratowych ilustracji zaokrągla się do pełnych pikseli, więc
# proporcje pliku mogą minimalnie odbiegać od atrybutów width i height.
ASPECT_TOLERANCE = 0.015
# Zabezpieczenie przed cichym rozjechaniem się wzorców: gdyby format tagów
# się zmienił, testy nie mogą przechodzić na pustym zbiorze.
MIN_EXPECTED_TAGS = 40

STATIC_ASSET_TAG = re.compile(
    r'<img class="asset[^"]*" src="/assets/([0-9a-z_]+/[a-z0-9_]+\.png)"'
    r' width="(\d+)" height="(\d+)"'
)
DYNAMIC_SIGNAL_TAG = re.compile(
    r'<img class="asset[^"]*" src="/assets/\{\{ *card\.asset *\}\}" width="(\d+)"'
)
ANY_ASSET_TAG = re.compile(r'<img class="asset[^"]*"[^>]*>')


def png_size(path: Path) -> tuple[int, int]:
    """Odczytuje wymiary PNG z nagłówka IHDR, bez dekodowania obrazu."""
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Plik nie jest obrazem PNG: {path}")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def template_files() -> list[Path]:
    """Zwraca wszystkie szablony HTML projektu."""
    return sorted(TEMPLATES_DIR.glob("*.html"))


def static_references() -> list[tuple[str, int, int, str]]:
    """Zwraca krotki (referencja, szerokość, wysokość, szablon) dla stałych grafik."""
    found: list[tuple[str, int, int, str]] = []
    for template in template_files():
        text = template.read_text(encoding="utf-8")
        for reference, width, height in STATIC_ASSET_TAG.findall(text):
            found.append((reference, int(width), int(height), template.name))
    return found


def signal_asset_size() -> int:
    """Zwraca rozmiar wyświetlania grafik sygnałów wstawianych przez Jinja."""
    text = (TEMPLATES_DIR / "today.html").read_text(encoding="utf-8")
    sizes = DYNAMIC_SIGNAL_TAG.findall(text)
    if not sizes:
        raise AssertionError(
            "Nie znaleziono tagu z dynamiczną grafiką sygnału w today.html. "
            "Jeśli zmieniono sposób wstawiania, zaktualizuj wzorzec DYNAMIC_SIGNAL_TAG."
        )
    return max(int(size) for size in sizes)


def signal_references() -> list[str]:
    """Zwraca referencje grafik sygnałów zdrowotnych z metadanych aplikacji."""
    return sorted({meta["asset"] for meta in _SIGNAL_META.values() if meta.get("asset")})


def display_sizes() -> dict[str, int]:
    """Zwraca największy rozmiar wyświetlania dla każdej używanej grafiki."""
    sizes: dict[str, int] = {}
    for reference, width, height, _ in static_references():
        sizes[reference] = max(sizes.get(reference, 0), width, height)
    signal_size = signal_asset_size()
    for reference in signal_references():
        sizes[reference] = max(sizes.get(reference, 0), signal_size)
    return sizes


def test_templates_expose_expected_number_of_asset_tags() -> None:
    """Wzorce muszą obejmować wszystkie tagi grafik, inaczej reszta testów jest pusta."""
    all_tags = sum(
        len(ANY_ASSET_TAG.findall(template.read_text(encoding="utf-8")))
        for template in template_files()
    )
    matched = len(static_references()) + len(DYNAMIC_SIGNAL_TAG.findall(
        (TEMPLATES_DIR / "today.html").read_text(encoding="utf-8")
    ))

    assert all_tags >= MIN_EXPECTED_TAGS, (
        f"Znaleziono tylko {all_tags} tagów grafik, oczekiwano co najmniej {MIN_EXPECTED_TAGS}."
    )
    assert matched == all_tags, (
        f"Wzorce rozpoznały {matched} z {all_tags} tagów grafik. "
        "Któryś tag ma inny format atrybutów i wymknąłby się sprawdzeniom."
    )


def test_static_references_are_served_by_manifest() -> None:
    """Każda grafika z szablonu musi być w manifeście, inaczej widok zwróci 404."""
    manifest = build_manifest(ASSETS_DIR)

    missing = [
        f"{template}: {reference}"
        for reference, _, _, template in static_references()
        if reference not in manifest
    ]

    assert not missing, "Grafiki nieobecne w manifeście: " + ", ".join(missing)


def test_signal_references_are_served_by_manifest() -> None:
    """Grafiki sygnałów wstawia Jinja, więc szablon ich nie weryfikuje."""
    manifest = build_manifest(ASSETS_DIR)

    missing = [reference for reference in signal_references() if reference not in manifest]

    assert not missing, "Grafiki sygnałów nieobecne w manifeście: " + ", ".join(missing)


def test_declared_proportions_match_files() -> None:
    """Niezgodne proporcje oznaczają, że przeglądarka rozciąga grafikę."""
    manifest = build_manifest(ASSETS_DIR)
    stretched: list[str] = []

    for reference, width, height, template in static_references():
        path = manifest.get(reference)
        if path is None:
            continue
        file_width, file_height = png_size(path)
        expected_width = height * file_width / file_height
        if abs(expected_width - width) > width * ASPECT_TOLERANCE:
            stretched.append(
                f"{template}: {reference} ma {width}x{height}, "
                f"a plik {file_width}x{file_height} wymaga wysokości "
                f"{round(width * file_height / file_width)}"
            )

    assert not stretched, "Grafiki rozciągnięte przez błędne atrybuty: " + "; ".join(stretched)


def test_files_have_at_least_double_display_resolution() -> None:
    """Zbyt mały plik wygląda rozmyto na ekranie o dużej gęstości pikseli."""
    manifest = build_manifest(ASSETS_DIR)
    too_small: list[str] = []

    for reference, display in sorted(display_sizes().items()):
        path = manifest.get(reference)
        if path is None:
            continue
        longer_edge = max(png_size(path))
        required = display * MIN_PIXEL_RATIO
        if longer_edge < required:
            too_small.append(f"{reference} ma {longer_edge} px, wymagane {required} px")

    assert not too_small, "Grafiki o zbyt małej rozdzielczości: " + "; ".join(too_small)


def test_asset_tags_are_marked_as_decorative() -> None:
    """Grafiki są dekoracyjne, więc czytnik ekranu musi je pomijać."""
    described: list[str] = []

    for template in template_files():
        for tag in ANY_ASSET_TAG.findall(template.read_text(encoding="utf-8")):
            if 'alt=""' not in tag:
                described.append(f"{template.name}: {tag}")

    assert not described, "Tagi grafik bez alt=\"\": " + "; ".join(described)


def test_every_used_asset_keeps_an_original() -> None:
    """Pliki prezentacyjne są nadpisywane, więc oryginał musi zostać w repozytorium."""
    missing: list[str] = []

    for reference in sorted(display_sizes()):
        if not (ORIGINALS_DIR / reference).is_file():
            missing.append(reference)

    assert not missing, (
        "Brak oryginałów dla używanych grafik, nie da się ich już powiększyć: "
        + ", ".join(missing)
    )
