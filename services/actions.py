"""Wykonawcy mutujących operacji uruchamianych jako zadania w tle."""
from __future__ import annotations

from datetime import datetime

from services.jobs import (
    GARMIN_LOGIN_REQUIRED_MESSAGE,
    JobStore,
    PLAN_AI_DISABLED_MESSAGE,
    PLAN_NO_PLAN_MESSAGE,
)
from services.locking import LockBusyError, acquire_lock
from services.plan import as_datetime


SYNC_BUSY_MESSAGE = "Operacja już trwa. Spróbuj ponownie za chwilę."
SNAPSHOT_MISSING_MESSAGE = "Brakuje lokalnego snapshotu danych. Uruchom: python -m trainer sync"
PLAN_BUSY_MESSAGE = "Operacja już trwa. Spróbuj ponownie za chwilę."
PLAN_CONFLICT_MESSAGE = ("Na ten tydzień jest już plan. Wybierz, czy go nadpisać, "
                         "zapisać nowy jako drugą wersję, czy anulować.")
GARMIN_CONFLICT_MESSAGE = ("Na niektóre dni są już treningi na zegarku. Wybierz, czy je zastąpić, "
                           "dodać nowe obok, czy anulować.")


def synchronize_data(*, fresh=False):
    """Wykonaj synchronizację i zapisz nowy lokalny snapshot.

    Argument ``fresh`` rozróżnia pełną synchronizację od zwykłej bez
    wywoływania komendy CLI, która ma własną blokadę.
    """
    from services.data_extract import synchronize_and_save

    return synchronize_and_save(fresh=fresh)


def run_sync_job(*, store: JobStore, job_id: str, operation=synchronize_data,
                 fresh=False, lock_directory=None):
    """Oznacz zadanie, wykonaj synchronizację pod blokadą i zapisz rezultat."""
    store.mark_running(job_id)
    try:
        with acquire_lock(name="sync", directory=lock_directory):
            if operation is synchronize_data:
                operation(fresh=fresh)
            else:
                operation()
    except LockBusyError:
        return store.mark_failed(job_id, message=SYNC_BUSY_MESSAGE)
    except Exception:
        return store.mark_failed(job_id)
    return store.mark_succeeded(job_id)


REVIEW_BUSY_MESSAGE = "Ocena już trwa. Spróbuj ponownie za chwilę."
REVIEW_DISABLED_MESSAGE = "Ocena treningu wymaga włączenia wysyłania danych do AI."


def review_workout(*, review_key, report_provider, profile_loader=None, provider_factory=None,
                   save=None) -> dict:
    """Policz lokalną ocenę treningu, pobierz komentarz AI i zapisz recenzję."""
    from services.workout_scoring import score_execution

    report = report_provider()
    execution = report.execution
    if execution is None:
        raise ValueError("Brak zaplanowanego treningu na dziś.")
    if execution.get("review_key") != review_key:
        raise ValueError("Ocena dotyczy innego treningu. Odśwież stronę.")

    if profile_loader is None:
        from trainer.profile_store import load_profile
        profile_loader = load_profile
    if save is None:
        from services.workout_reviews import save_review
        save = save_review

    profile = profile_loader()
    score = score_execution(
        planned=report.planned,
        execution=execution,
        readiness_score=(report.readiness or {}).get("score"),
        hr_zone_floors=profile.get("hr_zone_floors") or {},
        hr_max=profile.get("hr_max"),
    )

    from trainer import config
    if not config.AI_DATA_EXPORT_ENABLED or not config.AI_API_KEY:
        raise ValueError(REVIEW_DISABLED_MESSAGE)

    from ai.workout_review import get_workout_comment
    if provider_factory is None:
        from ai.openai_compatible import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(config.AI_BASE_URL, config.AI_API_KEY, config.AI_MODEL)
    else:
        provider = provider_factory()

    comment = get_workout_comment(
        provider,
        planned=report.planned,
        execution=execution,
        score=score,
        readiness=report.readiness or {},
        hr_zones_text=profile.get("hr_zones"),
    )
    save(review_key=review_key, score=score, comment=comment.komentarz)
    return {"score": score, "comment": comment.komentarz}


def run_review_job(*, store, job_id, review_key, operation, lock_directory=None):
    """Wykonaj ocenę treningu pod blokadą i zapisz stan zadania."""
    store.mark_running(job_id)
    try:
        with acquire_lock(name="review", directory=lock_directory):
            operation(review_key=review_key)
    except LockBusyError:
        return store.mark_failed(job_id, message=REVIEW_BUSY_MESSAGE)
    except ValueError as exc:
        return store.mark_failed(job_id, message=str(exc))
    except Exception:
        return store.mark_failed(job_id)
    return store.mark_succeeded(job_id)


# --- Plan tygodniowy ---------------------------------------------------------


def _require_ai_consent():
    """Sprawdź bramkę zgody na wysyłanie danych do AI."""
    from trainer import config

    if not config.AI_DATA_EXPORT_ENABLED or not config.AI_API_KEY:
        raise ValueError(PLAN_AI_DISABLED_MESSAGE)


def _check_policy(on_conflict):
    from services.plan_conflicts import ON_CONFLICT

    if on_conflict is not None and on_conflict not in ON_CONFLICT:
        raise ValueError("Nieznana decyzja w sprawie konfliktu.")


def generate_week_plan(*, week_start=None, provider_factory=None, save=None, today=None,
                       on_conflict=None) -> dict | None:
    """Ułóż tydzień treningowy przez AI, popraw go regułami i zapisz.

    Gdy na tydzień jest już plan, `on_conflict` decyduje: 'overwrite' odkłada obecne pliki
    do archiwum, 'add' zapisuje nowy plan jako drugą wersję, 'cancel' nic nie robi.
    Bez decyzji konflikt kończy się PlanConflictError, zanim dane trafią do AI.
    Jawne `save` (np. podgląd) pomija sprawdzanie konfliktu.
    """
    from services import plan as plan_service
    from services import plan_conflicts
    from services.data_extract import SnapshotStatus, read_snapshot_status
    from trainer.preferences import load_preferences
    from trainer.profile_store import load_profile

    snapshot = read_snapshot_status()
    if snapshot.status is SnapshotStatus.MISSING:
        raise ValueError(SNAPSHOT_MISSING_MESSAGE)

    _require_ai_consent()

    current = as_datetime(today) or datetime.now()
    anchor = as_datetime(week_start) or current
    _check_policy(on_conflict)
    existing = plan_service.load_week_plan(anchor) if save is None else None
    if existing is not None:
        if on_conflict is None:
            raise plan_conflicts.PlanConflictError(PLAN_CONFLICT_MESSAGE)
        if on_conflict == "cancel":
            return None
    profile = load_profile()
    preferences = load_preferences()
    context = plan_service.build_plan_context(
        snapshot_data=snapshot.data,
        profile=profile,
        preferences=preferences,
        today=current,
        week_start=anchor,
        snapshot_status=snapshot.status.value,
        snapshot_timestamp=(snapshot.data or {}).get("timestamp"),
    )

    if provider_factory is None:
        from ai.openai_compatible import OpenAICompatibleProvider
        from trainer import config
        provider = OpenAICompatibleProvider(config.AI_BASE_URL, config.AI_API_KEY, config.AI_MODEL)
    else:
        provider = provider_factory()

    from ai.plan_generation import generate_week_plan as generate_response
    response = generate_response(provider, context)

    normalized = plan_service.normalize_plan(response, context=context)
    if save is not None:
        save(normalized)
    elif existing is not None and on_conflict == "add":
        plan_conflicts.save_variant(normalized)
    else:
        if existing is not None:
            plan_conflicts.archive_week(datetime.strptime(normalized["start_date"], "%Y-%m-%d"))
        plan_service.save_plan(normalized)
    return normalized


def run_plan_job(*, store, job_id, operation=generate_week_plan, week_start=None, lock_directory=None,
                 on_conflict=None):
    """Wykonaj układanie planu pod blokadą i zapisz stan zadania."""
    store.mark_running(job_id)
    try:
        with acquire_lock(name="plan", directory=lock_directory):
            if on_conflict is None:
                operation(week_start=week_start)
            else:
                operation(week_start=week_start, on_conflict=on_conflict)
    except LockBusyError:
        return store.mark_failed(job_id, message=PLAN_BUSY_MESSAGE)
    except ValueError as exc:
        return store.mark_failed(job_id, message=str(exc))
    except Exception:
        return store.mark_failed(job_id)
    return store.mark_succeeded(job_id)


def _garmin_session():
    """Zwróć (utwórz, usuń) działające na jednej, leniwie otwieranej sesji Garmina."""
    from trainer.garmin_workouts import GarminWorkout, build_workout

    state = {"session": None}

    def session():
        if state["session"] is None:
            state["session"] = GarminWorkout().login()
        return state["session"]

    def create(kind, name, **kwargs):
        return build_workout(session(), kind, name, **kwargs)

    def delete(workout_id, schedule_id=None, reason=None):
        return session().delete(workout_id, schedule_id=schedule_id, reason=reason)

    return create, delete


def push_plan_to_garmin(*, week_start=None, workout_factory=None, workout_deleter=None,
                        on_conflict=None, registry_entries=None) -> dict:
    """Wyślij zapisany plan na zegarek; każdy udany trening zapisujesz od razu.

    Dni, na które rejestr ma już aktywny trening spoza tego planu, wymagają decyzji:
    'overwrite' usuwa tamte treningi z Garmina (rejestr pozwala je odtworzyć),
    'add' wysyła obok, 'cancel' nic nie robi.
    """
    from services import plan as plan_service
    from services.plan_conflicts import PlanConflictError, garmin_conflict_days
    from services.workout_registry import library

    _check_policy(on_conflict)
    anchor = as_datetime(week_start) or datetime.now()
    plan = plan_service.load_week_plan(anchor)
    if plan is None:
        raise ValueError(PLAN_NO_PLAN_MESSAGE)

    entries = library("active") if registry_entries is None else registry_entries
    conflicts = garmin_conflict_days(plan, entries)
    if conflicts and on_conflict is None:
        raise PlanConflictError(GARMIN_CONFLICT_MESSAGE)
    if conflicts and on_conflict == "cancel":
        return {"created": [], "skipped": 0, "replaced": []}

    replace = bool(conflicts) and on_conflict == "overwrite"
    if workout_factory is None or (replace and workout_deleter is None):
        session_create, session_delete = _garmin_session()
        workout_factory = workout_factory or session_create
        workout_deleter = workout_deleter or session_delete
    create = workout_factory

    replaced = []
    if replace:
        for conflict in conflicts:
            for existing in conflict["existing"]:
                workout_deleter(existing["workout_id"], schedule_id=existing["schedule_id"],
                                reason="zastąpiony planem")
                replaced.append(existing["workout_id"])

    created = []
    skipped = 0
    for workout in plan.get("workouts", []):
        if workout.get("garmin_upload"):
            skipped += 1
            continue
        mapped = plan_service.plan_workout_to_garmin(workout)
        if mapped is None:
            skipped += 1
            continue
        kind, kwargs = mapped
        workout_id = create(kind, workout.get("name") or "Trening", **kwargs)
        workout["garmin_upload"] = True
        workout["garmin_workout_id"] = workout_id
        created.append(workout_id)
        plan_service.save_plan(plan)
    return {"created": created, "skipped": skipped, "replaced": replaced}


def run_plan_push_job(*, store, job_id, operation=push_plan_to_garmin, week_start=None,
                      lock_directory=None, on_conflict=None):
    """Wykonaj wysyłkę planu do Garmina pod blokadą i zapisz stan zadania."""
    store.mark_running(job_id)
    try:
        with acquire_lock(name="plan-push", directory=lock_directory):
            if on_conflict is None:
                operation(week_start=week_start)
            else:
                operation(week_start=week_start, on_conflict=on_conflict)
    except LockBusyError:
        return store.mark_failed(job_id, message=PLAN_BUSY_MESSAGE)
    except ValueError as exc:
        return store.mark_failed(job_id, message=str(exc))
    except Exception as exc:
        if type(exc).__name__ == "GarminAuthError":
            return store.mark_failed(job_id, message=GARMIN_LOGIN_REQUIRED_MESSAGE)
        return store.mark_failed(job_id)
    return store.mark_succeeded(job_id)


def generate_daily_recommendation(*, provider_factory=None, save=None, today=None) -> dict:
    """Policz rekomendację AI na dziś i zapisz ją lokalnie."""
    from ai.context import build_training_context
    from services import plan as plan_service
    from services.data_extract import SnapshotStatus, read_snapshot_status
    from services.recommendations import save_recommendation

    snapshot = read_snapshot_status()
    if snapshot.status is SnapshotStatus.MISSING:
        raise ValueError(SNAPSHOT_MISSING_MESSAGE)

    _require_ai_consent()

    current = as_datetime(today) or datetime.now()
    plan = plan_service.load_week_plan(current)
    context = build_training_context(snapshot.data, plan=plan, today=current)

    if provider_factory is None:
        from ai.openai_compatible import OpenAICompatibleProvider
        from trainer import config
        provider = OpenAICompatibleProvider(config.AI_BASE_URL, config.AI_API_KEY, config.AI_MODEL)
    else:
        provider = provider_factory()

    from ai.recommendation import get_daily_recommendation
    recommendation = get_daily_recommendation(provider, context)

    result = {
        "readiness": recommendation.readiness,
        "recommendation": recommendation.recommendation,
        "planned_workout": recommendation.planned_workout,
        "adjustment_needed": recommendation.adjustment_needed,
        "reasoning_summary": recommendation.reasoning_summary,
        "warnings": list(recommendation.warnings or []),
    }
    if save is None:
        save = save_recommendation
    save(date=current.date().isoformat(), recommendation=result)
    return result


def run_recommendation_job(*, store, job_id, operation=generate_daily_recommendation,
                           lock_directory=None):
    """Wykonaj rekomendację dzienną pod blokadą i zapisz stan zadania."""
    store.mark_running(job_id)
    try:
        with acquire_lock(name="recommendation", directory=lock_directory):
            operation()
    except LockBusyError:
        return store.mark_failed(job_id, message=PLAN_BUSY_MESSAGE)
    except ValueError as exc:
        return store.mark_failed(job_id, message=str(exc))
    except Exception:
        return store.mark_failed(job_id)
    return store.mark_succeeded(job_id)
