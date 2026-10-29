# -*- coding: utf-8 -*-
"""
Append-only registry of workouts pushed to Garmin Connect.

Every deletion and update appends an event, while an upload may append multiple
events, to
``local/workout-registry.jsonl``::

    {"ts": "2026-09-16T17:20:00", "event": "added", "workout_id": 1700241385,
     "schedule_id": 1779674902, "date": "2026-09-17",
     "name": "Regeneracja 35 min - strefa 2", "spec": {"kind": "hr_zone_run", ...}}
    {"ts": "2026-09-18T08:05:00", "event": "deleted", "workout_id": 1700241385,
     "schedule_id": 1779674902, "reason": "wykonany"}

The file is never rewritten or truncated, so the full history survives: what was
sent to Garmin, when, when it was removed, and why. Current state is *derived* by
replaying the log, and because each ``added`` entry keeps the builder arguments in
``spec``, a deleted workout can be re-uploaded later.

Append-only was chosen over a mutable JSON/SQLite store on purpose: a crash or a
partial write can at worst lose the last line, never corrupt earlier history.

``schedule_status`` describes whether a requested schedule is pending,
confirmed, or unknown.

Importable from CLI, tests, and future API.
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from trainer.config import SETTINGS

logger = logging.getLogger(__name__)

REGISTRY_PATH = SETTINGS.workout_registry


@dataclass
class RegistryWriteResult:
    """Outcome of an attempted registry write.

    ``persisted=False`` means the write was not confirmed; it does not mean
    that no bytes reached the file.
    """
    entry: dict
    persisted: bool
    error_code: str | None = None


def _now():
    return datetime.now().replace(microsecond=0).isoformat()


def _write_entry(entry) -> RegistryWriteResult:
    """Write one entry and report whether the write was confirmed."""
    try:
        entry.setdefault('ts', _now())
    except Exception as e:
        logger.warning("Could not write workout registry: %s", e)
        return RegistryWriteResult(entry, persisted=False,
                                   error_code='timestamp_error')

    try:
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str)
    except Exception as e:
        logger.warning("Could not write workout registry: %s", e)
        return RegistryWriteResult(entry, persisted=False,
                                   error_code='serialization_error')

    try:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        logger.warning("Could not write workout registry: %s", e)
        return RegistryWriteResult(entry, persisted=False, error_code='io_error')

    result = RegistryWriteResult(entry, persisted=True)
    try:
        logger.info("Registry: %s %s", entry.get('event'), entry.get('workout_id'))
    except Exception:
        pass
    return result


def _append(entry, *, return_status=False):
    """Append one event to the log. Never rewrites existing lines.

    Swallows every error on purpose: bookkeeping must never break an upload that
    has already reached Garmin, so a failure here is logged, not raised.
    """
    result = _write_entry(entry)
    return result if return_status else entry


def record_added(name, date, workout_id, schedule_id=None, spec=None,
                 definition=None, source='live', *, intended_date=None,
                 schedule_status=None, return_status=False):
    """Log a workout that was uploaded (and optionally scheduled) to Garmin.

    Args:
        spec: builder arguments, enough to recreate the workout from scratch.
        definition: raw Garmin workout payload, enough to re-upload it verbatim.
            Either one makes the entry restorable; `definition` wins on restore.
        source: 'live' for uploads made through this project, 'backfill' for
            pre-existing library entries discovered later.
        intended_date: requested schedule date when it differs from ``date``.
        schedule_status: one of 'pending', 'confirmed', or 'unknown'.
    """
    entry = {
        'event': 'added',
        'workout_id': workout_id,
        'schedule_id': schedule_id,
        'date': date,
        'name': name,
        'source': source,
        'spec': spec or {},
        'definition': definition,
    }
    if intended_date is not None:
        entry['intended_date'] = intended_date
    if schedule_status is not None:
        entry['schedule_status'] = schedule_status
    return _append(entry, return_status=return_status)


def record_deleted(workout_id, schedule_id=None, reason=None, source='live', *,
                   return_status=False):
    """Log the removal of a workout from the Garmin library and calendar."""
    return _append({
        'event': 'deleted',
        'workout_id': workout_id,
        'schedule_id': schedule_id,
        'reason': reason,
        'source': source,
    }, return_status=return_status)


def record_usage(workout_id, last_used, source='sync', activity_id=None, match_method=None,
                 *, return_status=False):
    """Log the most recent date this workout's session was actually run.

    Refreshed periodically from the activity history, so cleanup decisions are
    based on real use rather than on how old the template is.
    """
    return _append({
        'event': 'usage',
        'workout_id': workout_id,
        'last_used': last_used,
        'source': source,
        'activity_id': activity_id,
        'match_method': match_method,
    }, return_status=return_status)


def record_updated(workout_id, name=None, definition=None, schedule_id=None,
                   date=None, note=None, source='update', *, schedule_status=None,
                   return_status=False):
    """Log that a registered workout was edited in Garmin Connect.

    Workouts get reshaped on the watch or in the app, and the entry on file
    drifts out of date in two ways that both bite later: the name stops matching
    the activity names Garmin writes (so the workout looks unused and becomes a
    cleanup candidate), and the stored definition no longer re-creates what was
    actually run. Recording the new state keeps both honest.

    Only the fields passed in are changed; the builder ``spec`` stays as it was,
    since that describes the original upload rather than the current shape.
    """
    entry = {
        'event': 'updated',
        'workout_id': workout_id,
        'name': name,
        'definition': definition,
        'schedule_id': schedule_id,
        'date': date,
        'note': note,
        'source': source,
    }
    if schedule_status is not None:
        entry['schedule_status'] = schedule_status
    return _append(entry, return_status=return_status)


# Garmin truncates activity names at about this many BYTES (UTF-8), not
# characters. With Polish diacritics (Ł, ż, ę are two bytes each) a truncated
# name can be as short as 43 characters — a character-based check misses it.
ACTIVITY_NAME_LIMIT = 44


def matches_activity(workout_name, activity_name):
    """True when an activity looks like it ran the given workout template.

    Garmin names activities "<location> - <workout name>" (or just the workout
    name), so we require an exact match or a " - <name>" suffix. A plain
    substring test is unusable here — template names like "Bieg" would match
    almost every activity.

    When the activity name hits Garmin's byte limit it is cut off mid-word, so
    an exact test silently fails. A truncated tail that is still a prefix of
    the workout name also counts, provided it is genuinely shorter than the
    workout name and at least 10 characters — that floor keeps short templates
    from turning into wildcards.

    Erring towards matching is deliberate: a false match leaves an unused
    workout in the library, while a miss would mark a used workout as stale and
    get it deleted.
    """
    if not workout_name or not activity_name:
        return False
    if activity_name == workout_name or activity_name.endswith(' - ' + workout_name):
        return True

    if len(activity_name.encode('utf-8')) >= ACTIVITY_NAME_LIMIT:
        tail = activity_name.split(' - ', 1)[-1]
        if len(tail) >= 10 and len(tail) < len(workout_name):
            return workout_name.startswith(tail)
    return False


def load_events():
    """Return every event in the log, oldest first. Unreadable lines are skipped."""
    if not REGISTRY_PATH.is_file():
        return []
    events = []
    with open(REGISTRY_PATH, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed registry line: %s", line[:80])
    return events


def list_workouts(status='all'):
    """Current state of every registered workout, newest upload first.

    Args:
        status: 'active', 'deleted', or 'all'.
    """
    state = {}
    for e in load_events():
        wid = e.get('workout_id')
        if wid is None:
            continue
        # Only 'added' brings a workout into existence. Every other event is
        # about a workout that is already known, so one for an unregistered id
        # is ignored rather than allowed to conjure an empty entry.
        if e.get('event') == 'added':
            entry = state.setdefault(wid, {'workout_id': wid})
            entry.update({
                'name': e.get('name'),
                'date': e.get('date'),
                'schedule_id': e.get('schedule_id'),
                'spec': e.get('spec') or {},
                'definition': e.get('definition'),
                'source': e.get('source', 'live'),
                'atp_plan_id': e.get('atp_plan_id'),
                'added_at': e.get('ts'),
                'status': 'active',
            })
            if e.get('intended_date') is not None:
                entry['intended_date'] = e['intended_date']
            if e.get('schedule_status') is not None:
                entry['schedule_status'] = e['schedule_status']
            entry.pop('deleted_at', None)
            entry.pop('reason', None)
            continue

        entry = state.get(wid)
        if entry is None:
            logger.warning("Registry: %s for unregistered workout %s",
                           e.get('event'), wid)
            continue

        if e.get('event') == 'deleted':
            entry.update({
                'status': 'deleted',
                'deleted_at': e.get('ts'),
                'reason': e.get('reason'),
                'schedule_id': entry.get('schedule_id') or e.get('schedule_id'),
            })
        elif e.get('event') == 'updated':
            # Only the fields actually passed in change; the builder spec
            # describes the original upload and survives an in-Garmin edit.
            for key in ('name', 'definition', 'schedule_id', 'date', 'schedule_status'):
                if e.get(key) is not None:
                    entry[key] = e[key]
        elif e.get('event') == 'usage':
            # Latest observation wins, not the maximum: each entry is a fresh
            # scan of the whole activity history, so the newest one is the most
            # correct — including when it corrects an earlier bad match.
            # A partial/empty scan must never erase a date established by an
            # earlier complete scan.
            if e.get('last_used') is not None:
                entry['last_used'] = e['last_used']
            if e.get('activity_id') is not None:
                entry['activity_id'] = e['activity_id']
            if e.get('match_method') is not None:
                entry['match_method'] = e['match_method']

    items = sorted(state.values(), key=lambda x: x.get('added_at') or '', reverse=True)
    if status != 'all':
        items = [x for x in items if x.get('status') == status]
    return items


def find_workout(workout_id):
    """Return the registry entry for one workout id, or None."""
    for w in list_workouts('all'):
        if w['workout_id'] == workout_id:
            return w
    return None


def library(status='active'):
    """Workouts that show up in the Garmin Connect workout library.

    Excludes anything belonging to an adaptive training plan: Garmin does not
    list those, so they are archive rather than library.
    """
    return [w for w in list_workouts(status) if not w.get('atp_plan_id')]


def cleanup_candidates(days=90, today=None, status='active'):
    """Library workouts that are both old and unused.

    A workout qualifies only when it was added to the library more than `days`
    ago AND has not been run since the cutoff (or never). The age check matters:
    a workout created this week has no usage history yet, and without it a
    freshly scheduled session would look like dead weight and get deleted the
    moment it was created.

    Plan workouts are never candidates — they are the record of past plans.
    """
    if today is None:
        today = datetime.now()
    cutoff = (today - timedelta(days=days)).strftime('%Y-%m-%d')
    out = []
    for w in library(status):
        added = (w.get('added_at') or '')[:10]
        if added and added >= cutoff:
            continue
        last = w.get('last_used')
        if last is None or last < cutoff:
            out.append(w)
    return sorted(out, key=lambda w: w.get('last_used') or '')


def _entry_date(entry):
    """When the workout entered the library — scheduled date if known, else added_at."""
    return (entry.get('date') or (entry.get('added_at') or '')[:10]) or None


def restore_entry(workout_id):
    """Return the full registry entry needed to re-upload a deleted workout.

    Raises KeyError if the workout was never registered.
    """
    w = find_workout(workout_id)
    if w is None:
        raise KeyError(f"Workout {workout_id} is not in the registry")
    return w


def summary(workout_id):
    """One-line human description of a registry entry."""
    w = find_workout(workout_id)
    if w is None:
        return f"{workout_id}: nieznany (brak w rejestrze)"
    line = f"{workout_id} | {w.get('name')} | {w.get('status')}"
    if w.get('status') == 'active':
        if w.get('schedule_status') in ('pending', 'unknown'):
            line += (f" | dodany {w.get('added_at')} | planowanie "
                     f"niepotwierdzone, żądany termin {w.get('intended_date')}")
        else:
            line += f" | dodany {w.get('added_at')} | zaplanowany {w.get('date')}"
    else:
        line += f" | usunięty {w.get('deleted_at')}"
        if w.get('reason'):
            line += f" ({w['reason']})"
    return line
