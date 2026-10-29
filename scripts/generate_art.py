"""Generate the dashboard artwork with the OpenAI Images API.

Images are written to trener_biegowy_ai_assets/_generated/<run>/ using the same
relative paths as _originals/, together with sheet.html for review. Nothing in
the served assets changes until --promote copies a reviewed run into _originals/,
after which scripts/rescale_assets.py --write produces the presentation files.

The API key is read from OPENAI_API_KEY (environment first, then the project .env
through trainer.env_file, exactly like the app reads its own settings). It is never
printed. Prompts describe generic artwork only; no runner data is sent.

    python scripts/generate_art.py --list
    python scripts/generate_art.py                    # all images, new run directory
    python scripts/generate_art.py --only nav_home kind_easy --run <dir>
    python scripts/generate_art.py --promote <dir>
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "trener_biegowy_ai_assets"
GENERATED_DIR = ASSETS_DIR / "_generated"
ORIGINALS_DIR = ASSETS_DIR / "_originals"
MAX_REQUESTS = 40
FALLBACK_MODEL = "gpt-image-1"

STYLE = (
    "Flat vector illustration for a calm, trustworthy running-coach app. "
    "Palette only: bright blue #2563EB, deep blue #1D4ED8, pale blue #DBEAFE, slate #475569, "
    "light slate #CBD5E1, white, and a small soft green accent #16A34A. "
    "Clean geometric shapes, softly rounded corners, gentle two-tone shading, no heavy outlines, "
    "no gradients mesh, no photorealism. Centered subject with generous empty padding around it. "
    "Fully transparent background. Absolutely no text, letters, numbers, logos or watermarks."
)
ICON = ("Single icon from one cohesive app icon set: same stroke weight, same corner radius, same "
        "perspective (straight-on), readable at 32 pixels. Subject: ")
SCENE = "Small friendly spot illustration, simple and uncluttered. Subject: "
NAV = ("Minimal navigation glyph from one cohesive set, at most three simple bold shapes, no small "
       "details, mostly #2563EB with one pale blue #DBEAFE fill, readable at 24 pixels. Subject: ")

# key: (relative path inside _originals, size, quality, prompt)
ITEMS = {
    "app_mark": ("07_ui_icons/app_mark.png", "1024x1024", "high",
                 "App icon mark: a stylised runner in motion formed by two or three bold blue strokes, "
                 "with a small green upward chevron suggesting progress, inside a rounded-square tile "
                 "filled with #2563EB, the runner in white. Simple, memorable, works at 16 pixels."),
    "nav_home": ("01_navigation/home.png", "1024x1024", "medium", NAV + "a house, today's dashboard."),
    "nav_plan": ("01_navigation/plan.png", "1024x1024", "medium", NAV + "a clipboard with a checklist and a small running shoe."),
    "nav_calendar": ("01_navigation/calendar.png", "1024x1024", "medium", NAV + "a calendar page with one highlighted day."),
    "nav_statistics": ("01_navigation/statistics.png", "1024x1024", "medium", NAV + "a bar chart with rising bars."),
    "nav_analysis": ("01_navigation/analysis.png", "1024x1024", "medium", NAV + "a magnifying glass over a heart-rate line."),
    "nav_journal": ("01_navigation/journal.png", "1024x1024", "medium", NAV + "an open notebook with a pen and a small heart."),
    "nav_goal": ("01_navigation/goal.png", "1024x1024", "medium", NAV + "a finish-line flag on a winding road."),
    "nav_settings": ("01_navigation/settings.png", "1024x1024", "medium", NAV + "a gear wheel with a slider."),
    "kind_easy": ("03_activity/kind_easy.png", "1024x1024", "medium", ICON + "a runner jogging relaxed, easy pace, light motion lines."),
    "kind_recovery": ("03_activity/kind_recovery.png", "1024x1024", "medium", ICON + "a runner walking slowly with a small leaf, recovery."),
    "kind_long": ("03_activity/kind_long.png", "1024x1024", "medium", ICON + "a runner on a long path stretching to distant hills."),
    "kind_tempo": ("03_activity/kind_tempo.png", "1024x1024", "medium", ICON + "a runner leaning forward with a steady speedometer needle."),
    "kind_threshold": ("03_activity/kind_threshold.png", "1024x1024", "medium", ICON + "a runner next to a heart with a horizontal threshold line."),
    "kind_intervals": ("03_activity/kind_intervals.png", "1024x1024", "medium", ICON + "a runner with alternating fast and slow dashed segments and a stopwatch."),
    "kind_rest": ("03_activity/kind_rest.png", "1024x1024", "medium", ICON + "a crescent moon above a pillow, rest day."),
    "rest_day": ("03_activity/rest_day.png", "1024x1024", "medium", SCENE + "a cosy bed with a pillow and a small moon, a planned rest day."),
    "no_training": ("03_activity/no_training.png", "1024x1024", "medium", SCENE + "a calendar day card with a pair of running shoes resting beside it, nothing scheduled."),
    "training_plan": ("09_illustrations/training_plan.png", "1536x1024", "medium", SCENE + "a clipboard training plan with a pair of running shoes and a small plant."),
    "running": ("09_illustrations/running.png", "1536x1024", "medium", SCENE + "a runner on a park path with soft trees, morning run."),
    "sleep": ("09_illustrations/sleep.png", "1536x1024", "medium", SCENE + "a sleeping figure under a blanket with a moon and stars, night recovery."),
    "journal_empty": ("09_illustrations/journal_empty.png", "1536x1024", "medium", SCENE + "an open journal with a pen and a cup of tea, ready for the first note."),
    "goal_finish": ("09_illustrations/goal_finish.png", "1536x1024", "medium", SCENE + "a road leading to a finish arch on the horizon, a long-term goal, sunrise."),
    # Small icons for number tiles and settings rows, same glyph style as the menu.
    **{f"tile_{name}": (f"07_ui_icons/tile_{name}.png", "1024x1024", "medium", NAV + subject) for name, subject in (
        ("distance", "a winding route line between a start dot and a map pin."),
        ("time", "a stopwatch."),
        ("pace", "a speedometer gauge with the needle in the middle."),
        ("sessions", "a running shoe with a small check mark."),
        ("quality", "a lightning bolt."),
        ("average", "three bars with a horizontal average line across them."),
        ("heart", "a heart with a pulse line."),
        ("heart_max", "a heart with an upward arrow."),
        ("heart_rest", "a heart with a small crescent moon."),
        ("threshold", "a heart with a horizontal threshold line through it."),
        ("vo2max", "a pair of lungs."),
        ("readiness", "a round gauge ring, partly filled, with a check mark in the centre."),
        ("signals", "a wristwatch with small radiating signal arcs."),
        ("confidence", "a shield with a check mark."),
        ("points", "a stack of three rounded coins."),
        ("trophy", "a trophy cup."),
        ("phase", "a calendar page with a small flag on it."),
        ("load", "a dumbbell next to a small rising arrow."),
        ("person", "a person bust in a circle."),
        ("age", "a birthday cake with one candle."),
        ("weight", "a bathroom scale."),
        ("height", "a vertical ruler with a small person silhouette beside it."),
        ("watch", "a GPS sports watch face."),
        ("race", "a race bib number card with safety pins, no digits."),
        ("date", "a calendar with one circled day."),
        ("frequency", "a calendar week row with four filled dots."),
        ("finish", "a checkered finish flag."),
        ("idea", "a light bulb with two short light rays."),
        ("message", "a speech bubble with three dots."),
        ("alert", "a rounded warning triangle with an exclamation mark, in amber #D97706 instead of blue."),
    )},
}


def api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.path.insert(0, str(PROJECT_ROOT))
        from trainer.env_file import read_env_file

        key = read_env_file(PROJECT_ROOT / ".env").get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set in the environment or in .env")
    return key


def candidate_models(client) -> list[str]:
    """gpt-image models the key can use, newest first; mini variants last."""
    try:
        ids = [model.id for model in client.models.list()]
    except Exception as error:  # noqa: BLE001 - any listing failure falls back
        print(f"Could not list models ({type(error).__name__}), using {FALLBACK_MODEL}")
        return [FALLBACK_MODEL]

    def rank(model_id):
        match = re.fullmatch(r"gpt-image-(\d+(?:\.\d+)?)(-mini)?", model_id)
        return (match.group(2) is None, float(match.group(1))) if match else None

    ranked = sorted(((rank(i), i) for i in ids if rank(i) is not None), reverse=True)
    return [model_id for _, model_id in ranked] or [FALLBACK_MODEL]


def _no_transparency(error) -> bool:
    return "Transparent background is not supported" in str(error)


def generate(client, model, key, run_dir) -> Path:
    relative, size, quality, prompt = ITEMS[key]
    result = client.images.generate(model=model, prompt=f"{STYLE}\n\n{prompt}", size=size, quality=quality,
                                    background="transparent", output_format="png", n=1)
    target = run_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(result.data[0].b64_json))
    return target


def write_sheet(run_dir: Path) -> Path:
    cells = []
    for key, (relative, *_rest) in ITEMS.items():
        path = run_dir / relative
        if path.is_file():
            cells.append(f'<figure><img src="{html.escape(relative)}" alt=""><figcaption>{html.escape(key)}'
                         f'<br><small>{html.escape(relative)}</small></figcaption></figure>')
    sheet = run_dir / "sheet.html"
    sheet.write_text(
        "<!doctype html><meta charset=utf-8><title>Grafiki</title><style>"
        "body{font:13px system-ui;margin:16px;background:#F8FAFC}"
        "main{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}"
        "figure{margin:0;background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:10px;text-align:center}"
        "img{width:100%;aspect-ratio:1/1;object-fit:contain;background:"
        "repeating-conic-gradient(#F1F5F9 0 25%,#fff 0 50%) 0 0/16px 16px;border-radius:8px}"
        "small{color:#475569}</style><main>" + "".join(cells) + "</main>",
        encoding="utf-8",
    )
    return sheet


def promote(run_dir: Path, keys) -> None:
    for key in keys:
        relative = ITEMS[key][0]
        source = run_dir / relative
        if not source.is_file():
            print(f"skip {key}: not generated in {run_dir}")
            continue
        target = ORIGINALS_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        # A presentation file must exist for the manifest; rescale_assets.py overwrites it.
        presentation = ASSETS_DIR / relative
        if not presentation.exists():
            presentation.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, presentation)
        print(f"promoted {key} -> _originals/{relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list", action="store_true", help="print the planned images and exit")
    parser.add_argument("--only", nargs="+", choices=sorted(ITEMS), help="generate only these keys")
    parser.add_argument("--run", type=Path, help="existing run directory to add images to")
    parser.add_argument("--promote", type=Path, metavar="RUN", help="copy a reviewed run into _originals/")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    keys = args.only or list(ITEMS)

    if args.list:
        for key in keys:
            relative, size, quality, _ = ITEMS[key]
            print(f"{key:16} {size:10} {quality:7} {relative}")
        return 0
    if args.promote:
        promote(args.promote.resolve(), keys)
        return 0
    if len(keys) > MAX_REQUESTS:
        raise SystemExit(f"refusing to send more than {MAX_REQUESTS} requests in one run")

    from openai import OpenAI

    client = OpenAI(api_key=api_key(), max_retries=2, timeout=180)
    run_dir = (args.run or GENERATED_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"run: {run_dir}\nimages: {len(keys)}")

    # The first image probes models newest-first: some families reject transparent
    # backgrounds, which every image here needs, so they are skipped instead of retried.
    model = None
    for candidate in candidate_models(client):
        try:
            generate(client, candidate, keys[0], run_dir)
        except Exception as error:  # noqa: BLE001
            if _no_transparency(error):
                print(f"skip model {candidate}: no transparent background")
                continue
            raise
        model = candidate
        break
    if model is None:
        raise SystemExit("no available model supports transparent backgrounds")
    print(f"model: {model}\nok   {keys[0]}")

    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(generate, client, model, key, run_dir): key for key in keys[1:]}
        for future in as_completed(futures):
            key = futures[future]
            try:
                future.result()
                print(f"ok   {key}")
            except Exception as error:  # noqa: BLE001 - report and continue with the rest
                failures.append(key)
                print(f"FAIL {key}: {type(error).__name__}: {str(error)[:200]}")
    print(f"sheet: {write_sheet(run_dir)}")
    if failures:
        print("retry with: --run", run_dir, "--only", " ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
