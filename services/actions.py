"""Wykonawcy mutujących operacji uruchamianych jako zadania w tle."""
from __future__ import annotations

from services.jobs import JobStore
from services.locking import LockBusyError, acquire_lock


SYNC_BUSY_MESSAGE = "Operacja już trwa. Spróbuj ponownie za chwilę."


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
