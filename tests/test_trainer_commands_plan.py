# -*- coding: utf-8 -*-
"""Testy komendy `trainer plan`."""
import json

from trainer import cli
from trainer.commands import plan as plan_command


def _write_plan(base):
    directory = base / "2026-10"
    directory.mkdir(parents=True, exist_ok=True)
    days = [
        ("mon", "2026-10-26", "easy", "Bieg łatwy"),
        ("tue", "2026-10-27", "easy", "Bieg łatwy"),
        ("wed", "2026-10-28", "rest", "Odpoczynek"),
        ("thu", "2026-10-29", "tempo", "Tempo progowe"),
        ("fri", "2026-10-30", "rest", "Odpoczynek"),
        ("sat", "2026-10-31", "rest", "Odpoczynek"),
        ("sun", "2026-11-01", "long", "Długi bieg"),
    ]
    plan = {
        "start_date": "2026-10-26", "end_date": "2026-11-01", "priority": "normal",
        "focus": "Baza tygodnia", "summary": "Jeden akcent i dwa biegi regeneracyjne.",
        "generated_at": "2026-10-26T06:00:00+00:00",
        "workouts": [{
            "day": day, "date": date, "type": kind, "name": name, "description": "",
            "distance_km": 8.0 if kind != "rest" else None,
            "duration_min": 45 if kind != "rest" else None,
            "pace_target": "5:00-5:10" if kind == "tempo" else None,
            "hr_target": "122-136 bpm" if kind != "rest" else None,
            "hr_zone": "Z2" if kind != "rest" else None,
            "garmin_upload": False, "garmin_workout_id": None, "notes": "",
        } for day, date, kind, name in days],
    }
    (directory / "26-1.json").write_text(json.dumps(plan), encoding="utf-8")
    return plan


def test_show_without_a_plan_reports_a_missing_plan(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path)

    code = plan_command.main(show=True, week="2026-10-26")

    captured = capsys.readouterr()
    assert code == 1
    assert "Brak planu" in captured.err
    assert "python -m trainer plan" in captured.err


def test_show_prints_every_day_of_the_saved_plan(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path)
    _write_plan(tmp_path)

    code = plan_command.main(show=True, week="2026-10-26")

    captured = capsys.readouterr()
    assert code == 0
    for date in ("2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29",
                 "2026-10-30", "2026-10-31", "2026-11-01"):
        assert date in captured.out
    assert "Tempo progowe" in captured.out
    assert "Razem:" in captured.out


def test_cli_show_option_reaches_the_plan_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path)
    _write_plan(tmp_path)

    code = cli.main(["plan", "--show", "--week", "2026-10-26"])

    captured = capsys.readouterr()
    assert code == 0
    assert "2026-11-01" in captured.out


def test_cli_show_without_a_plan_fails_with_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path)

    code = cli.main(["plan", "--show"])

    captured = capsys.readouterr()
    assert code == 1
    assert "Brak planu" in captured.err


def test_push_without_a_plan_does_not_call_garmin(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("services.plan_files.TRAINING_PLANS_DIR", tmp_path)

    code = plan_command.main(push=True, week="2026-10-26")

    captured = capsys.readouterr()
    assert code == 1
    assert "Najpierw ułóż plan na ten tydzień." in captured.err
