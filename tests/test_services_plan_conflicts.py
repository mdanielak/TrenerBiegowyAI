# -*- coding: utf-8 -*-
"""Konflikty przy układaniu i wysyłce planu: wykrywanie, decyzje, archiwum i wersje."""
import json
import re
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ai.plan_generation import WeekPlanResponse
from api.main import create_app
from services import plan_conflicts, plan_files
from services.actions import generate_week_plan, push_plan_to_garmin
from services.data_extract import SnapshotReadResult, SnapshotStatus
from services.jobs import JobStore
from services.plan import save_plan
from services.plan_conflicts import PlanConflictError
from trainer import config

pytestmark = pytest.mark.usefixtures("testclient_sockets")

MONDAY = datetime(2026, 10, 26)
KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _dates():
    return [(MONDAY + timedelta(days=i)).date().isoformat() for i in range(7)]


def _plan(name="Łatwy 40 min – Z2", uploaded=(), start=0):
    workouts = []
    for index, day in enumerate(_dates()):
        if index < start:
            continue
        kind = "easy" if index in (0, 1, 3) else "rest"
        workouts.append({
            "date": day, "day": KEYS[index], "type": kind, "name": name if kind == "easy" else "Odpoczynek",
            "duration_min": 40 if kind == "easy" else None, "hr_zone": "Z2" if kind == "easy" else None,
            "garmin_upload": index in uploaded, "garmin_workout_id": 900 + index if index in uploaded else None,
        })
    dates = _dates()
    return {"start_date": dates[start], "end_date": dates[-1], "focus": "Spokojnie", "summary": "",
            "workouts": workouts}


def _registry(*days, workout_id=1):
    return [{"workout_id": workout_id + i, "date": _dates()[day], "name": "Bieg z zegarka", "schedule_id": 50 + i}
            for i, day in enumerate(days)]


# --- wykrywanie -------------------------------------------------------------------------

def test_plan_conflict_days_list_trainings_and_watch_state():
    days = plan_conflicts.plan_conflict_days(_plan(uploaded=(0,)))

    assert [d["label"] for d in days] == ["poniedziałek 26.10", "wtorek 27.10", "czwartek 29.10"]
    assert days[0]["on_watch"] is True and days[1]["on_watch"] is False
    assert days[0]["minutes"] == 40


def test_garmin_conflicts_ignore_own_uploads_and_already_sent_days():
    plan = _plan(uploaded=(0,))
    entries = _registry(0, 1) + [{"workout_id": 900, "date": _dates()[0], "name": "własny"}]

    conflicts = plan_conflicts.garmin_conflict_days(plan, entries)

    assert [c["date"] for c in conflicts] == [_dates()[1]]
    assert conflicts[0]["existing"][0]["workout_id"] == 2


# --- archiwum i wersje ------------------------------------------------------------------

def test_archive_week_moves_every_file_of_the_week_including_revisions():
    save_plan(_plan())
    revision = _plan(name="Rewizja", start=2)
    revision_path = plan_files.plan_path(MONDAY, None).parent / "28-1.json"
    revision_path.write_text(json.dumps(revision), encoding="utf-8")

    moved = plan_conflicts.archive_week(MONDAY, now=datetime(2026, 10, 28, 12))

    assert {p.parent.name for p in moved} == {"archive"}
    assert len(moved) == 2
    assert plan_files.find_plan_file(MONDAY) is None
    assert (moved[0].with_suffix(".csv")).is_file() or (moved[1].with_suffix(".csv")).is_file()


def test_variants_are_invisible_to_the_active_plan_until_activated():
    save_plan(_plan(name="Obecny"))
    plan_conflicts.save_variant(_plan(name="Nowy"), now=datetime(2026, 10, 28, 12, 0, 0))

    assert plan_files.load_plan(MONDAY)["workouts"][0]["name"] == "Obecny"
    [(name, variant)] = plan_conflicts.list_variants(MONDAY)
    assert name == "26-1.20261028-120000.json" and variant["workouts"][0]["name"] == "Nowy"

    plan_conflicts.activate_variant(MONDAY, name, now=datetime(2026, 10, 28, 12, 5))

    assert plan_files.load_plan(MONDAY)["workouts"][0]["name"] == "Nowy"
    assert plan_conflicts.list_variants(MONDAY) == []
    archive = plan_files.plan_path(MONDAY, None).parent / "archive"
    assert len(list(archive.glob("*.json"))) == 2


@pytest.mark.parametrize("name", ["../26-1.json", "26-1.json", "2-8.20261028-120000.json", "x"])
def test_variant_names_from_the_form_are_validated(name):
    with pytest.raises(ValueError):
        plan_conflicts.activate_variant(MONDAY, name)


# --- decyzje w serwisach ----------------------------------------------------------------

@pytest.fixture
def ai_calls(monkeypatch):
    """Generowanie planu bez sieci: stały kontekst i odpowiedź modelu."""
    calls = []
    monkeypatch.setattr(config, "AI_DATA_EXPORT_ENABLED", True)
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    monkeypatch.setattr("services.data_extract.read_snapshot_status",
                        lambda: SnapshotReadResult(status=SnapshotStatus.FRESH, data={}))
    monkeypatch.setattr("trainer.profile_store.load_profile", lambda: {})
    monkeypatch.setattr("trainer.preferences.load_preferences", lambda: {})
    week_days = [{"date": d, "day": KEYS[i], "weekday": "x", "available": True, "min_minutes": 30,
                  "max_minutes": 60, "pause_reason": None} for i, d in enumerate(_dates())]
    monkeypatch.setattr("services.plan.build_plan_context",
                        lambda **kwargs: {"week_start": _dates()[0], "week_end": _dates()[-1], "week_days": week_days})

    def respond(provider, context):
        calls.append(context)
        return WeekPlanResponse(start_date=_dates()[0], end_date=_dates()[-1], focus="Nowy plan",
                                workouts=[{"date": _dates()[0], "kind": "easy", "name": "Nowy", "duration_min": 40}])

    monkeypatch.setattr("ai.plan_generation.generate_week_plan", respond)
    return calls


def _generate(**kwargs):
    return generate_week_plan(week_start=MONDAY, provider_factory=lambda: object(), **kwargs)


def test_generate_without_a_decision_stops_before_calling_ai(ai_calls):
    save_plan(_plan(name="Obecny"))

    with pytest.raises(PlanConflictError):
        _generate()
    assert ai_calls == []
    assert _generate(on_conflict="cancel") is None
    assert ai_calls == []


def test_generate_overwrite_archives_and_add_keeps_the_current_plan(ai_calls):
    save_plan(_plan(name="Obecny"))

    _generate(on_conflict="add")
    assert plan_files.load_plan(MONDAY)["workouts"][0]["name"] == "Obecny"
    assert len(plan_conflicts.list_variants(MONDAY)) == 1

    _generate(on_conflict="overwrite")
    assert plan_files.load_plan(MONDAY)["focus"] == "Nowy plan"
    assert list((plan_files.plan_path(MONDAY, None).parent / "archive").glob("26-1.*.json"))


def test_generate_without_an_existing_plan_needs_no_decision(ai_calls):
    assert _generate()["focus"] == "Nowy plan"


def test_push_policies(monkeypatch):
    save_plan(_plan(uploaded=(0,)))
    created, deleted = [], []

    def factory(kind, name, **kwargs):
        created.append(kwargs.get("date") or name)
        return 1000 + len(created)

    def deleter(workout_id, schedule_id=None, reason=None):
        deleted.append((workout_id, schedule_id, reason))

    entries = _registry(1)
    with pytest.raises(PlanConflictError):
        push_plan_to_garmin(week_start=MONDAY, workout_factory=factory, registry_entries=entries)
    assert push_plan_to_garmin(week_start=MONDAY, workout_factory=factory, registry_entries=entries,
                               on_conflict="cancel")["created"] == []
    assert created == []

    result = push_plan_to_garmin(week_start=MONDAY, workout_factory=factory, workout_deleter=deleter,
                                 registry_entries=entries, on_conflict="overwrite")

    assert deleted == [(1, 50, "zastąpiony planem")]
    assert result["replaced"] == [1] and len(result["created"]) == 2


def test_push_add_keeps_existing_watch_workouts():
    save_plan(_plan())
    deleted = []
    result = push_plan_to_garmin(week_start=MONDAY, workout_factory=lambda kind, name, **kw: 7,
                                 workout_deleter=lambda *a, **k: deleted.append(a),
                                 registry_entries=_registry(0), on_conflict="add")

    assert deleted == [] and len(result["created"]) == 3


# --- web ---------------------------------------------------------------------------------

def _client(tmp_path, *, plan, registry=(), jobs=None, plan_calls=None):
    app = create_app(
        plan_provider=lambda monday: plan,
        registry_provider=lambda: list(registry),
        ai_settings_provider=lambda: {"key_present": True, "export_enabled": True},
        profile_provider=lambda: {"name": "Test"},
        availability_provider=lambda: {},
        job_store=jobs or JobStore(tmp_path / "jobs"),
        lock_directory=tmp_path / "locks",
        plan_operation=lambda **kwargs: (plan_calls if plan_calls is not None else []).append(kwargs),
        plan_push_operation=lambda **kwargs: None,
        now_provider=lambda: datetime(2026, 10, 28, 12),
        snapshot_provider=lambda: SnapshotReadResult(status=SnapshotStatus.FRESH, data={}),
    )
    return TestClient(app)


def _csrf(client, url="/plan?week=2026-10-26"):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(url).text).group(1)


def _post(client, url, **data):
    data.setdefault("csrf_token", _csrf(client))
    data.setdefault("week_start", "2026-10-26")
    return client.post(url, data=data, headers={"Origin": "http://testserver"}, follow_redirects=False)


def test_plan_button_asks_before_overwriting(tmp_path):
    store = JobStore(tmp_path / "jobs")
    client = _client(tmp_path, plan=_plan(uploaded=(0,)), jobs=store)

    response = _post(client, "/actions/plan")

    assert response.status_code == 303
    assert response.headers["location"] == "/plan?week=2026-10-26&confirm=plan"
    assert store.list_jobs().jobs == []
    page = client.get(response.headers["location"]).text
    assert "Na ten tydzień jest już plan" in page
    assert "Poniedziałek 26.10" in page and "na zegarku" in page
    for value in ("overwrite", "add", "cancel"):
        assert f'name="on_conflict" value="{value}"' in page


def test_plan_decisions_queue_a_job_or_cancel(tmp_path):
    store = JobStore(tmp_path / "jobs")
    calls = []
    with _client(tmp_path, plan=_plan(), jobs=store, plan_calls=calls) as client:
        cancelled = _post(client, "/actions/plan", on_conflict="cancel")
        assert cancelled.headers["location"] == "/plan?week=2026-10-26" and store.list_jobs().jobs == []

        queued = _post(client, "/actions/plan", on_conflict="add")
        assert queued.status_code == 303
    [job] = store.list_jobs().jobs
    assert job.operation == "plan"
    assert calls == [{"week_start": "2026-10-26", "on_conflict": "add"}]


def test_push_button_asks_only_when_the_watch_has_workouts(tmp_path):
    store = JobStore(tmp_path / "jobs")
    client = _client(tmp_path, plan=_plan(), registry=_registry(1), jobs=store)

    response = _post(client, "/actions/plan/push")

    assert response.headers["location"] == "/plan?week=2026-10-26&confirm=push"
    page = client.get(response.headers["location"]).text
    assert "Na te dni są już treningi na zegarku" in page and "Zastąp na zegarku" in page

    with _client(tmp_path, plan=_plan(), registry=(), jobs=JobStore(tmp_path / "jobs2")) as free:
        assert _post(free, "/actions/plan/push").headers["location"] == "/plan"


def test_confirm_form_requires_csrf(tmp_path):
    client = _client(tmp_path, plan=_plan())

    response = _post(client, "/actions/plan", csrf_token="zly", on_conflict="overwrite")

    assert response.status_code == 403


def test_variant_card_and_activation(tmp_path):
    save_plan(_plan(name="Obecny"))
    plan_conflicts.save_variant(_plan(name="Nowy"), now=datetime(2026, 10, 28, 12))
    client = _client(tmp_path, plan=plan_files.load_plan(MONDAY))

    page = client.get("/plan?week=2026-10-26").text
    assert "Druga wersja planu" in page and "teraz: Obecny · 40 min" in page

    response = _post(client, "/actions/plan/variant", variant="26-1.20261028-120000.json", decision="activate")

    assert response.status_code == 303
    assert plan_files.load_plan(MONDAY)["workouts"][0]["name"] == "Nowy"


def test_overwrite_deletes_old_workouts_only_after_new_ones_are_on_the_watch():
    save_plan(_plan())
    calls = []

    def factory(kind, name, **kwargs):
        calls.append("create")
        if calls.count("create") == 2:
            raise ConnectionError("zerwane połączenie")
        return 7

    with pytest.raises(ConnectionError):
        push_plan_to_garmin(week_start=MONDAY, workout_factory=factory,
                            workout_deleter=lambda *a, **k: calls.append("delete"),
                            registry_entries=_registry(1), on_conflict="overwrite")
    assert "delete" not in calls  # przerwana wysyłka nie zostawia pustego dnia na zegarku
