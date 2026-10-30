# -*- coding: utf-8 -*-
"""Aplikacja do ręcznego testowania UI na zmyślonym tygodniu, bez Garmina i bez prawdziwego AI.

Uruchamiaj przez testowanie.bat: kopiuje kod do katalogu tymczasowego i startuje go stamtąd,
więc każda ścieżka aplikacji (local/, training-plans/, .env, ~/.GarminDb) wskazuje na piaskownicę.

Scenariusz: dziś jest środa (wolne). Poniedziałek przebiegnięty, czwartek i piątek są już na
zegarku, sobota wolna, niedziela jeszcze nie wysłana. Garmin i AI odpowiadają po kilku
sekundach zmyślonymi danymi, więc widać paski postępu i banery.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[1]
PORT = 8002

# Zanim cokolwiek z aplikacji się zaimportuje: dom, dane Garmina i klucze tylko z piaskownicy.
HOME = SANDBOX / "home"
HOME.mkdir(exist_ok=True)
os.environ.update({"USERPROFILE": str(HOME), "HOME": str(HOME), "HEALTH_DATA_DIR": str(HOME / "HealthData"),
                   "AI_BASE_URL": "https://ai.testowanie.invalid/v1", "AI_API_KEY": "testowy-klucz",
                   "AI_MODEL": "model-testowy", "AI_DATA_EXPORT_ENABLED": "1", "GARMIN_EMAIL": "test@example.com"})
(SANDBOX / ".env").write_text(
    "AI_BASE_URL=https://ai.testowanie.invalid/v1\nAI_API_KEY=testowy-klucz\nAI_MODEL=model-testowy\n"
    "AI_DATA_EXPORT_ENABLED=1\nGARMIN_EMAIL=test@example.com\n", encoding="utf-8")
sys.path.insert(0, str(SANDBOX))
os.chdir(SANDBOX)

import importlib  # noqa: E402
import json  # noqa: E402
import pkgutil  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import datetime as _dt  # noqa: E402

from trainer import config  # noqa: E402

if Path(config.PROJECT_ROOT).resolve() != SANDBOX or Path.home().resolve() != HOME.resolve():
    sys.exit(f"Przerwano: aplikacja wskazuje na {config.PROJECT_ROOT}, a nie na piaskownicę {SANDBOX}.")

# --- Zegar: dziś jest środa bieżącego tygodnia; godziny i sekundy płyną normalnie. ---------------
REAL_DT, REAL_DATE = _dt.datetime, _dt.date
_real_today = REAL_DATE.today()
OFFSET = _dt.timedelta(days=2 - _real_today.weekday())
TODAY = _real_today + OFFSET
MONDAY = TODAY - _dt.timedelta(days=2)


class _Clock(type):
    """isinstance/issubclass działają jak dla prawdziwych typów, więc reszta kodu nic nie zauważa."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls.real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls.real)


class FakeDatetime(REAL_DT, metaclass=_Clock):
    real = REAL_DT

    @classmethod
    def now(cls, tz=None):
        return REAL_DT.now(tz) + OFFSET

    @classmethod
    def today(cls):
        return REAL_DT.now() + OFFSET

    @classmethod
    def utcnow(cls):
        return REAL_DT.utcnow() + OFFSET


class FakeDate(REAL_DATE, metaclass=_Clock):
    real = REAL_DATE

    @classmethod
    def today(cls):
        return REAL_DATE.today() + OFFSET


for package in ("trainer", "services", "ai", "api"):
    root = importlib.import_module(package)
    for info in pkgutil.walk_packages(root.__path__, package + "."):
        if info.name.endswith("__main__"):
            continue  # uruchomiłby CLI
        try:
            importlib.import_module(info.name)
        except (Exception, SystemExit):  # noqa: BLE001 - moduł, który się nie importuje, nie bierze udziału w teście
            pass


def _app_modules():
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None) or ""
        if module is sys.modules[__name__]:
            continue  # ten skrypt potrzebuje prawdziwego zegara
        if path and Path(path).resolve().is_relative_to(SANDBOX):
            yield module


def _replace(original, fake):
    """Podmień obiekt wszędzie, gdzie aplikacja go zaimportowała (także `from x import y`)."""
    for module in _app_modules():
        for name, value in list(vars(module).items()):
            if value is original:
                setattr(module, name, fake)


_replace(REAL_DT, FakeDatetime)
_replace(REAL_DATE, FakeDate)
datetime, date, timedelta, timezone = FakeDatetime, FakeDate, _dt.timedelta, _dt.timezone

from services import actions, garmin_setup, plan as plan_service, workout_registry  # noqa: E402
from services.workout_steps import spec_from_plan  # noqa: E402
from ai import connection_test, openai_compatible  # noqa: E402
from ai.plan_generation import WeekPlanResponse  # noqa: E402
from ai.recommendation import DailyRecommendation  # noqa: E402
from ai.workout_review import WorkoutComment  # noqa: E402
from trainer import garmin_auth  # noqa: E402


def _iso(day):
    return day.isoformat()


# --- Udawany Garmin --------------------------------------------------------------------------
_next_id = iter(range(9001, 99999))


def _spec(kind, kwargs):
    """Ten sam zapis w rejestrze, który zostawia prawdziwa wysyłka (format z spec_from_plan)."""
    if kind == "hr_zone_run":
        return {"kind": kind, "duration_min": kwargs["minutes"], "zone_number": kwargs["zone_number"],
                "warmup_min": kwargs.get("warmup_min", 6), "warmup_pace_faster": kwargs.get("warmup_pace_faster"),
                "warmup_pace_slower": kwargs.get("warmup_pace_slower")}
    if kind == "tempo":
        return {"kind": "tempo_run", "tempo_min": kwargs["minutes"], "pace_faster": kwargs["pace_from"],
                "pace_slower": kwargs["pace_to"], "warmup_min": 10, "cooldown_min": 10}
    return {"kind": "threshold_intervals", "num_intervals": kwargs.get("repeats"), "work_sec": kwargs.get("work_seconds"),
            "rest_sec": kwargs.get("rest_seconds"), "pace_faster": kwargs.get("pace_from"),
            "pace_slower": kwargs.get("pace_to"), "warmup_min": 10, "cooldown_min": 10}


def fake_garmin_session():
    def create(kind, name, **kwargs):
        time.sleep(1.5)
        workout_id = next(_next_id)
        workout_registry.record_added(name, kwargs.get("date"), workout_id, schedule_id=workout_id + 1,
                                      spec=_spec(kind, kwargs), schedule_status="confirmed")
        return workout_id

    def delete(workout_id, schedule_id=None, reason=None):
        time.sleep(1.5)
        workout_registry.record_deleted(workout_id, schedule_id=schedule_id, reason=reason)

    return create, delete


def fake_sync(*, fresh=False, progress=None):
    for stage, seconds in (("garmin", 2), ("today", 4), ("history", 12 if fresh else 8), ("extract", 3)):
        if progress:
            progress(stage)
        time.sleep(seconds)
    _write_snapshot()


def fake_start_login(email, password, **kwargs):
    time.sleep(1)
    garmin_auth.token_path().parent.mkdir(parents=True, exist_ok=True)
    garmin_auth.token_path().write_text("{}", encoding="utf-8")
    return "done", None


# --- Udawane AI ------------------------------------------------------------------------------
class FakeProvider:
    def __init__(self, *args, **kwargs):
        pass

    def chat(self, system_prompt, user_message, response_model=None, **kwargs):
        time.sleep(4)
        if response_model is WeekPlanResponse:
            return _fake_plan(user_message)
        if response_model is DailyRecommendation:
            return DailyRecommendation(
                readiness="ready", adjustment_needed=False,
                recommendation="Dziś wolne zgodnie z planem. Krótki spacer i rozciąganie wystarczą.",
                reasoning_summary="HRV w normie, sen dobry, jutro interwały — warto przyjść wypoczętym.",
                warnings=[])
        if response_model is WorkoutComment:
            return WorkoutComment(komentarz="Równe tempo i tętno w drugiej strefie — dokładnie o to chodziło.")
        return "OK"


def _fake_plan(message):
    """Treningi tylko w dni opisane jako dostępne; minione dni AI dostaje jako 'już minął'."""
    dates = re.findall(r"(\d{4}-\d{2}-\d{2}): dostępny", message)
    workouts = []
    for index, day in enumerate(dates):
        if index == len(dates) - 1:
            workouts.append({"date": day, "kind": "long", "name": "Długi bieg 80 min", "duration_min": 80,
                             "distance_km": 13.0, "hr_zone": 2, "description": "Spokojnie, równe tempo."})
        elif index == 1:
            workouts.append({"date": day, "kind": "intervals", "name": "Interwały 5×3 min", "duration_min": 50,
                             "distance_km": 8.5, "hr_zone": 4, "pace_target": "4:55-5:05", "repetitions": 5,
                             "work_seconds": 180, "rest_seconds": 120, "description": "Mocno, ale równo."})
        else:
            workouts.append({"date": day, "kind": "easy", "name": "Bieg łatwy 40 min", "duration_min": 40,
                             "distance_km": 6.5, "hr_zone": 2, "description": "Rozmowa bez zadyszki."})
    return WeekPlanResponse(focus="Testowy tydzień", summary="Plan z udawanego AI do sprawdzania UI.",
                            workouts=workouts)


_replace(actions._garmin_session, fake_garmin_session)
_replace(garmin_setup.start_login, fake_start_login)
_replace(garmin_setup.import_profile, lambda **kwargs: {})
_replace(connection_test.check_connection, lambda **kwargs: time.sleep(1))
openai_compatible.OpenAICompatibleProvider = FakeProvider


# --- Dane startowe ---------------------------------------------------------------------------
FLOORS = {"z1": 98, "z2": 120, "z3": 138, "z4": 156, "z5": 172}


def _write_snapshot():
    rnd = random.Random(7)
    activities, health, sleep, hrv, weight = [], [], [], [], []
    for back in range(70, -1, -1):
        day = TODAY - timedelta(days=back)
        health.append({"date": _iso(day), "rhr": 48 + rnd.randint(0, 3), "hr_min": 44, "hr_max": 150,
                       "steps": rnd.randint(6000, 12000), "stress_avg": rnd.randint(20, 32), "rr": 14,
                       "spo2": 96, "cal_active": 600, "cal_total": 2400})
        sleep.append({"date": _iso(day), "total_h": round(7 + rnd.random() * 0.8, 1), "deep_h": 1.4,
                      "light_h": 3.9, "rem_h": 1.6, "score": rnd.randint(78, 88), "qualifier": "GOOD"})
        hrv.append({"date": _iso(day), "weekly_avg": 60, "last_night": rnd.randint(56, 66),
                    "baseline_low": 52, "baseline_high": 68, "status": "BALANCED"})
        if back % 7 == 0:
            weight.append({"date": _iso(day), "weight_kg": 68.5})
        runs = {1: ("Bieg łatwy", 45, 7.4, 134), 3: ("Interwały", 52, 8.8, 152), 6: ("Długi bieg", 85, 13.8, 139)}
        run = runs.get(day.weekday()) if day < MONDAY else (("Bieg łatwy", 41, 6.8, 133) if day == MONDAY else None)
        if run:
            name, minutes, km, avg_hr = run
            pace = minutes / km
            activities.append({"activity_id": 7000 + back, "date": f"{_iso(day)} 18:10", "name": name,
                               "type": "running/generic", "distance_km": km, "duration_min": float(minutes),
                               "pace": f"{int(pace)}:{round(pace % 1 * 60):02d}", "avg_hr": avg_hr,
                               "max_hr": avg_hr + 18, "avg_speed_kmh": round(km / minutes * 60, 1),
                               "ascent_m": 40.0, "te": 3.1, "ate": 0.8})
    snapshot = {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat(),
                "activities": activities, "daily_health": health, "sleep": sleep, "hrv": hrv, "weight": weight,
                "window": {"activity_days": 70, "health_days": 70}}
    config.DATA_LATEST.parent.mkdir(parents=True, exist_ok=True)
    config.DATA_LATEST.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")


def _workout(day_index, kind, name, **fields):
    day = MONDAY + timedelta(days=day_index)
    entry = {"day": ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day_index], "date": _iso(day), "type": kind,
             "name": name, "description": fields.pop("description", ""), "distance_km": None, "duration_min": None,
             "pace_target": None, "hr_target": None, "hr_zone": None, "repetitions": None, "work_seconds": None,
             "rest_seconds": None, "garmin_upload": False, "garmin_workout_id": None, "notes": ""}
    entry.update(fields)
    return entry


def _seed():
    local = config.LOCAL_DIR
    local.mkdir(exist_ok=True)
    (local / "profile.json").write_text(json.dumps({
        "name": "Testowy Biegacz", "age": 34, "weight_kg": 68.5, "height_cm": 176, "hr_max": 188, "hr_rest": 48,
        "lactate_threshold_hr": 168, "hr_zone_floors": FLOORS,
        "hr_zones": "Z1 98-119, Z2 120-137, Z3 138-155, Z4 156-171, Z5 172-188",
        "current_hm_record": "2:02:00", "target_hm": "1:55:00", "target_race": "Półmaraton",
        "target_date": _iso(TODAY + timedelta(days=150)), "training_frequency": "4 treningi w tygodniu",
    }, ensure_ascii=False), encoding="utf-8")
    slot = lambda free, low=30, high=60: {"available": free, "min_minutes": low if free else 0,  # noqa: E731
                                          "max_minutes": high if free else 0}
    (local / "training_preferences.json").write_text(json.dumps({
        "version": 1, "max_quality_sessions_per_week": 1, "notes": "", "planned_pauses": [],
        "days": {"mon": slot(True), "tue": slot(True), "wed": slot(False), "thu": slot(True, 40, 60),
                 "fri": slot(True), "sat": slot(False), "sun": slot(True, 60, 100)},
    }), encoding="utf-8")
    garmin_auth.token_path().parent.mkdir(parents=True, exist_ok=True)
    garmin_auth.token_path().write_text("{}", encoding="utf-8")
    from services.ai_status import record_test
    record_test(ok=True, base_url=os.environ["AI_BASE_URL"], model=os.environ["AI_MODEL"],
                path=local / "ai_status.json")
    _write_snapshot()

    workouts = [
        _workout(0, "easy", "Bieg łatwy 40 min", duration_min=40, distance_km=6.5, hr_zone="Z2",
                 hr_target="120-137 bpm", description="Rozmowa bez zadyszki."),
        _workout(1, "rest", "Odpoczynek"),
        _workout(2, "rest", "Odpoczynek", description="Dzień bez zadeklarowanej dostępności."),
        _workout(3, "intervals", "Interwały 5×3 min", duration_min=50, distance_km=8.5, hr_zone="Z4",
                 hr_target="156-171 bpm", pace_target="4:55-5:05", repetitions=5, work_seconds=180,
                 rest_seconds=120, description="Mocno, ale równo."),
        _workout(4, "easy", "Bieg łatwy 35 min", duration_min=35, distance_km=5.8, hr_zone="Z2",
                 hr_target="120-137 bpm", description="Rozluźnienie po interwałach."),
        _workout(5, "rest", "Odpoczynek", description="Dzień bez zadeklarowanej dostępności."),
        _workout(6, "long", "Długi bieg 80 min", duration_min=80, distance_km=13.0, hr_zone="Z2",
                 hr_target="120-137 bpm", description="Spokojnie, równe tempo."),
    ]
    create, _ = fake_garmin_session()
    for index in (0, 3, 4):  # poniedziałek (już przebiegnięty), czwartek i piątek są na zegarku
        workout = workouts[index]
        kind, kwargs = plan_service.plan_workout_to_garmin(workout)
        workout["garmin_upload"] = True
        workout["garmin_workout_id"] = create(kind, workout["name"], **kwargs)
    plan_service.save_plan({
        "start_date": _iso(MONDAY), "end_date": _iso(MONDAY + timedelta(days=6)), "priority": "normal",
        "focus": "Akcent w czwartek, długi bieg w niedzielę",
        "summary": "Środa i sobota wolne. Czwartek i piątek są już na zegarku, niedziela czeka na wysyłkę.",
        "generated_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "workouts": workouts,
    })
    assert spec_from_plan(workouts[6]) is not None


if __name__ == "__main__":
    import uvicorn
    from api.main import create_app

    _seed()
    actions.synchronize_data = fake_sync  # run_sync_job podaje postęp tylko „swojej” synchronizacji
    app = create_app(sync_operation=fake_sync)
    print(f"\n  Testowa aplikacja: http://127.0.0.1:{PORT}  (dziś = środa {TODAY:%d.%m.%Y})")
    print(f"  Piaskownica: {SANDBOX}\n  Garmin i AI są udawane. Zamknij okno albo Ctrl+C, żeby zakończyć.\n")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
