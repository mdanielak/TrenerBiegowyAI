"""Rebuild the presentation PNG files from the untouched originals.

The files served from trener_biegowy_ai_assets are cropped and downscaled copies
of the originals kept in trener_biegowy_ai_assets/_originals. Display sizes are
read from the templates, so changing a size there and rerunning this script is
enough to regenerate matching files. Nothing is written without --write.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
ASSETS_DIR = PROJECT_ROOT / "trener_biegowy_ai_assets"
ORIGINALS_DIR = ASSETS_DIR / "_originals"

# Presentation files carry twice the display size so they stay sharp on screens
# with a high pixel density.
PIXEL_RATIO = 2
# Visible artwork fills this share of the frame. The originals shipped with
# 20-37% of empty alpha margin, which made the icons look far too small.
FILL = 0.88
# Small dots keep their margin on purpose, so they are only resized.
NO_CROP_MARKER = "dot_"
# Below this ratio the artwork is enlarged beyond its original resolution and
# loses sharpness.
SHARPNESS_FLOOR = 2.0

STATIC_ASSET_TAG = re.compile(
    r'<img class="asset[^"]*" src="/assets/([0-9a-z_]+/[a-z0-9_]+\.png)"'
    r' width="(\d+)" height="(\d+)"'
)
DYNAMIC_SIGNAL_TAG = re.compile(
    r'<img class="asset[^"]*" src="/assets/\{\{ *card\.asset *\}\}" width="(\d+)"'
)
DYNAMIC_PLAN_ICON_TAG = re.compile(
    r'<img class="asset[^"]*" src="\{\{ *plan_day\.icon *\}\}" width="(\d+)"'
)
ANY_ASSET_TAG = re.compile(r'<img class="asset[^"]*"[^>]*>')


def template_files() -> list[Path]:
    """Return every HTML template of the project."""
    return sorted(TEMPLATES_DIR.glob("*.html"))


def signal_references() -> list[str]:
    """Return the health signal images that Jinja inserts at render time."""
    # The templates only hold a placeholder for these, so the names have to come
    # from the application metadata.
    sys.path.insert(0, str(PROJECT_ROOT))
    from api.main import _SIGNAL_META

    return sorted({meta["asset"] for meta in _SIGNAL_META.values() if meta.get("asset")})


def plan_icon_references() -> list[str]:
    """Return the training kind icons that Jinja inserts in the plan grid."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from api.views.plan import _PLAN_KIND_ICONS

    return sorted({reference.removeprefix("/assets/") for reference in _PLAN_KIND_ICONS.values()})


def collect_targets() -> tuple[dict[str, int], list[str]]:
    """Return the largest display size per image, plus any warnings."""
    targets: dict[str, int] = {}
    warnings: list[str] = []
    recognised = 0
    total = 0

    for template in template_files():
        text = template.read_text(encoding="utf-8")
        total += len(ANY_ASSET_TAG.findall(text))
        for reference, width, height in STATIC_ASSET_TAG.findall(text):
            recognised += 1
            size = max(int(width), int(height))
            targets[reference] = max(targets.get(reference, 0), size)

    today = (TEMPLATES_DIR / "today.html").read_text(encoding="utf-8")
    dynamic_sizes = [int(size) for size in DYNAMIC_SIGNAL_TAG.findall(today)]
    recognised += len(dynamic_sizes)
    if dynamic_sizes:
        for reference in signal_references():
            targets[reference] = max(targets.get(reference, 0), max(dynamic_sizes))
    else:
        warnings.append(
            "no dynamic signal tag found in today.html, health signal images were skipped"
        )

    plan = (TEMPLATES_DIR / "plan.html").read_text(encoding="utf-8")
    plan_sizes = [int(size) for size in DYNAMIC_PLAN_ICON_TAG.findall(plan)]
    recognised += len(plan_sizes)
    if plan_sizes:
        for reference in plan_icon_references():
            targets[reference] = max(targets.get(reference, 0), max(plan_sizes))
    else:
        warnings.append(
            "no dynamic plan icon tag found in plan.html, training kind icons were skipped"
        )

    if recognised != total:
        warnings.append(
            f"only {recognised} of {total} asset tags matched the patterns, "
            "some images may be missing from this run"
        )

    return targets, warnings


def frame_size(original: tuple[int, int], display: int) -> tuple[int, int]:
    """Return the output frame, keeping the aspect ratio of the original."""
    width, height = original
    longer = display * PIXEL_RATIO
    if width >= height:
        return longer, round(height * longer / width)
    return round(width * longer / height), longer


def render(source: Path, display: int, crop: bool):
    """Return the rebuilt image and its frame for one original."""
    from PIL import Image

    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        frame = frame_size(image.size, display)
        box = image.getchannel("A").getbbox()
        full_frame = box is None or box == (0, 0, image.width, image.height)

        if not crop or full_frame:
            # Nothing to trim, so a plain resize keeps the artwork untouched.
            return image.resize(frame, Image.Resampling.LANCZOS), frame, False

        artwork = image.crop(box)
        scale = min(
            FILL * frame[0] / artwork.width,
            FILL * frame[1] / artwork.height,
        )
        scaled = artwork.resize(
            (max(1, round(artwork.width * scale)), max(1, round(artwork.height * scale))),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", frame, (0, 0, 0, 0))
        canvas.paste(
            scaled,
            ((frame[0] - scaled.width) // 2, (frame[1] - scaled.height) // 2),
            scaled,
        )
        return canvas, frame, True


def png_size(path: Path) -> tuple[int, int]:
    """Read PNG dimensions from the IHDR header without decoding the image."""
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG file: {path}")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="overwrite the presentation files, otherwise only report what would change",
    )
    arguments = parser.parse_args()

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print(
            "ERROR: Pillow is required. Install it with: pip install -r requirements-dev.txt",
            file=sys.stderr,
        )
        return 2

    targets, warnings = collect_targets()
    if not targets:
        print("ERROR: no asset references found in the templates", file=sys.stderr)
        return 2

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    print(f"{'image':38} {'display':>7} {'frame':>11} {'original':>11} {'headroom':>9}  mode")
    written = 0
    total_bytes = 0
    blurry: list[str] = []
    missing: list[str] = []

    for reference, display in sorted(targets.items()):
        source = ORIGINALS_DIR / reference
        if not source.is_file():
            missing.append(reference)
            continue

        crop = NO_CROP_MARKER not in Path(reference).name
        image, frame, cropped = render(source, display, crop)
        original = png_size(source)
        headroom = max(original) / display
        if headroom < SHARPNESS_FLOOR:
            blurry.append(f"{reference} ({headroom:.2f}x)")

        destination = ASSETS_DIR / reference
        if arguments.write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, "PNG", optimize=True)
            total_bytes += destination.stat().st_size
            written += 1

        mode = "crop+fill" if cropped else "resize"
        flag = "" if headroom >= SHARPNESS_FLOOR else "  LOW"
        print(
            f"{reference:38} {display:7} {frame[0]:5}x{frame[1]:<5} "
            f"{original[0]:5}x{original[1]:<5} {headroom:8.2f}x  {mode}{flag}"
        )

    if missing:
        print(f"\nERROR: missing originals ({len(missing)}):", file=sys.stderr)
        for reference in missing:
            print(f"- {reference}", file=sys.stderr)

    print(f"\n{len(targets) - len(missing)} images processed")
    if blurry:
        print(
            f"{len(blurry)} enlarged past the original resolution: " + ", ".join(blurry)
        )
    if arguments.write:
        print(f"{written} files written, {total_bytes / 1024 / 1024:.3f} MB total")
    else:
        print("Dry run, nothing was written. Pass --write to apply.")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
