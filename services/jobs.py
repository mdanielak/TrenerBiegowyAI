"""Trwały, lokalny rejestr zadań wykonywanych w tle.

Moduł celowo nie wykonuje operacji zewnętrznych.  Najpierw tworzy rekord
zadania na dysku, a wywołujący może dopiero potem oznaczyć je jako uruchomione
i wykonać efekt, na przykład wysłanie treningu do Garmina.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trainer.files import write_atomic


_STATUSES = frozenset({"accepted", "running", "succeeded", "failed", "unknown"})
_ACTIVE_STATUSES = frozenset({"accepted", "running"})
_SAFE_OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_GENERIC_FAILURE = "Operacja nie powiodła się."
# Zakończone zadania są potrzebne tylko do pasków stanu z ostatnich minut i strony szczegółów.
JOB_RETENTION = timedelta(days=30)
PLAN_AI_DISABLED_MESSAGE = "Generowanie planu wymaga włączenia wysyłania danych do AI."
PLAN_NO_PLAN_MESSAGE = "Najpierw ułóż plan na ten tydzień."
GARMIN_LOGIN_REQUIRED_MESSAGE = "Wysyłka planu do Garmina wymaga działającego logowania."
AI_PAYMENT_MESSAGE = "Brak środków na koncie u dostawcy AI. Doładuj konto albo zmień dostawcę w Ustawienia → API AI."
AI_REJECTED_MESSAGE = "Dostawca AI odrzucił zapytanie. Sprawdź klucz w Ustawienia → API AI → Sprawdź połączenie."
_ALLOWED_FAILURE_MESSAGES = frozenset({
    _GENERIC_FAILURE,
    "Operacja już trwa. Spróbuj ponownie za chwilę.",
    PLAN_AI_DISABLED_MESSAGE,
    PLAN_NO_PLAN_MESSAGE,
    GARMIN_LOGIN_REQUIRED_MESSAGE,
    AI_PAYMENT_MESSAGE,
    AI_REJECTED_MESSAGE,
})


class JobError(RuntimeError):
    """Bazowy błąd publicznego API magazynu zadań."""


class JobNotFoundError(JobError):
    """Nie znaleziono zadania o podanym identyfikatorze."""


class JobConflictError(JobError):
    """Trwa już inne zadanie tego samego typu."""


class JobCooldownError(JobError):
    """Od ostatniego sukcesu nie minął jeszcze wymagany czas."""


@dataclass(frozen=True)
class JobRecord:
    """Bezpieczny do zapisania stan pojedynczego zadania."""

    id: str
    operation: str
    arguments_hash: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class JobListResult:
    """Wynik listowania wraz z plikami pominiętymi jako uszkodzone."""

    jobs: list[JobRecord]
    corrupted_files: list[Path]


def _utc_iso(now: datetime | None = None) -> str:
    """Zwróć czas UTC w jednoznacznym formacie ISO bez mikrosekund."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_timestamp(value: str) -> datetime:
    """Odczytaj zapisany czas ISO jako czas strefowy."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _arguments_hash(arguments) -> str:
    """Zwróć stabilny skrót argumentów bez zapisywania ich zawartości."""
    try:
        payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Argumenty zadania muszą dać się zapisać jako JSON.") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JobStore:
    """Magazyn plików JSON, domyślnie w ``local/jobs``."""

    def __init__(self, directory: Path | str = Path("local/jobs")) -> None:
        self.directory = Path(directory)

    def submit(self, operation: str, arguments, *, cooldown: timedelta | None = None,
               now: datetime | None = None) -> JobRecord:
        """Utwórz zadanie lub zwróć identyczne aktywne zadanie.

        Zapis kończy się przed zwróceniem rekordu, więc wywołujący może bezpiecznie
        rozpocząć efekt zewnętrzny dopiero po powrocie z tej metody.
        """
        self._validate_operation(operation)
        if cooldown is not None and cooldown.total_seconds() < 0:
            raise ValueError("Czas cooldown nie może być ujemny.")
        arguments_hash = _arguments_hash(arguments)
        listing = self.list_jobs()
        active = [job for job in listing.jobs if job.operation == operation and job.status in _ACTIVE_STATUSES]
        for job in active:
            if job.arguments_hash == arguments_hash:
                return job
        if active:
            raise JobConflictError("Trwa już zadanie tego samego typu z innymi argumentami.")

        if cooldown is not None:
            current = _parse_timestamp(_utc_iso(now))
            successful = [job for job in listing.jobs if job.operation == operation and job.status == "succeeded"]
            if successful:
                latest = max(_parse_timestamp(job.finished_at or job.created_at) for job in successful)
                if current < latest + cooldown:
                    raise JobCooldownError("Należy poczekać przed ponownym uruchomieniem tej operacji.")

        record = JobRecord(
            id=secrets.token_urlsafe(24), operation=operation, arguments_hash=arguments_hash,
            status="accepted", created_at=_utc_iso(now),
        )
        self._write(record)
        return record

    def get(self, job_id: str) -> JobRecord:
        """Odczytaj zadanie lub zgłoś czytelny błąd jego braku."""
        path = self._path_for_id(job_id)
        try:
            return self._read(path)
        except FileNotFoundError as exc:
            raise JobNotFoundError("Nie znaleziono zadania o podanym identyfikatorze.") from exc

    def list_jobs(self) -> JobListResult:
        """Zwróć poprawne zadania i osobno wskaż uszkodzone pliki JSON."""
        if not self.directory.exists():
            return JobListResult(jobs=[], corrupted_files=[])
        jobs: list[JobRecord] = []
        corrupted: list[Path] = []
        for path in self.directory.glob("*.json"):
            try:
                jobs.append(self._read(path))
            except (OSError, ValueError, json.JSONDecodeError, TypeError):
                corrupted.append(path)
        jobs.sort(key=lambda job: (job.created_at, job.id), reverse=True)
        return JobListResult(jobs=jobs, corrupted_files=corrupted)

    def mark_running(self, job_id: str, *, now: datetime | None = None) -> JobRecord:
        """Oznacz zapisane wcześniej zaakceptowane zadanie jako wykonywane."""
        return self._change_status(job_id, "running", now=now)

    def mark_succeeded(self, job_id: str, *, now: datetime | None = None) -> JobRecord:
        """Zakończ zadanie sukcesem."""
        return self._change_status(job_id, "succeeded", now=now)

    def mark_failed(self, job_id: str, *, message: str | None = None,
                    now: datetime | None = None) -> JobRecord:
        """Zakończ zadanie błędem bez ujawniania tekstu wyjątku z integracji."""
        safe_message = message if message in _ALLOWED_FAILURE_MESSAGES else _GENERIC_FAILURE
        return self._change_status(job_id, "failed", error_message=safe_message, now=now)

    def mark_abandoned_running_as_unknown(self, *, now: datetime | None = None) -> list[JobRecord]:
        """Oznacz zadania przerwane przez restart jako nieznane, bez ponawiania.

        Dotyczy też zadań czekających w kolejce: po restarcie nic ich już nie uruchomi,
        a jako „przyjęte” blokowałyby przycisk tej operacji na zawsze.
        """
        changed = []
        for job in self.list_jobs().jobs:
            if job.status in _ACTIVE_STATUSES:
                changed.append(self._change_status(job.id, "unknown", now=now))
        return changed

    def prune_finished(self, *, older_than: timedelta = JOB_RETENTION, now: datetime | None = None) -> int:
        """Usuń zakończone zadania starsze niż ``older_than``; strony czytają przy każdym wejściu wszystkie."""
        cutoff = _parse_timestamp(_utc_iso(now)) - older_than
        removed = 0
        for job in self.list_jobs().jobs:
            if job.status in _ACTIVE_STATUSES:
                continue
            if _parse_timestamp(job.finished_at or job.created_at) < cutoff:
                for path in (self._path_for_id(job.id), self.directory / "progress" / f"{job.id}.json"):
                    path.unlink(missing_ok=True)
                removed += 1
        return removed

    def _change_status(self, job_id: str, status: str, *, error_message=None,
                       now: datetime | None) -> JobRecord:
        job = self.get(job_id)
        if status == "running" and job.status != "accepted":
            raise JobError("Można uruchomić tylko zaakceptowane zadanie.")
        if status in {"succeeded", "failed"} and job.status != "running":
            raise JobError("Można zakończyć tylko wykonywane zadanie.")
        if status == "unknown" and job.status not in _ACTIVE_STATUSES:
            raise JobError("Jako nieznane można oznaczyć tylko przyjęte albo wykonywane zadanie.")
        timestamp = _utc_iso(now)
        updated = JobRecord(
            id=job.id, operation=job.operation, arguments_hash=job.arguments_hash, status=status,
            created_at=job.created_at, started_at=timestamp if status == "running" else job.started_at,
            finished_at=timestamp if status in {"succeeded", "failed", "unknown"} else job.finished_at,
            error_message=error_message if status == "failed" else None,
        )
        self._write(updated)
        return updated

    def _write(self, record: JobRecord) -> None:
        """Atomowo zapisz rekord; awaria zapisu zawsze trafia do wywołującego."""
        write_atomic(self._path_for_id(record.id), json.dumps(asdict(record), ensure_ascii=False, indent=2) + "\n")

    def _read(self, path: Path) -> JobRecord:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != set(JobRecord.__dataclass_fields__):
            raise ValueError("Nieprawidłowy rekord zadania.")
        record = JobRecord(**data)
        if (not _SAFE_JOB_ID.fullmatch(record.id) or not _SAFE_OPERATION.fullmatch(record.operation)
                or record.operation in {".", ".."} or record.status not in _STATUSES
                or not re.fullmatch(r"[0-9a-f]{64}", record.arguments_hash)):
            raise ValueError("Nieprawidłowy rekord zadania.")
        return record

    @staticmethod
    def _validate_operation(operation: str) -> None:
        if (not isinstance(operation, str) or not _SAFE_OPERATION.fullmatch(operation)
                or operation in {".", ".."}):
            raise ValueError("Klucz operacji zawiera niedozwolone znaki.")

    def _path_for_id(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _SAFE_JOB_ID.fullmatch(job_id):
            raise JobNotFoundError("Nieprawidłowy identyfikator zadania.")
        return self.directory / f"{job_id}.json"
