# -*- coding: utf-8 -*-
"""
Reużywalny builder treningów dla Garmin Connect API.

Przykład:
    from trainer.workouts import GarminWorkout

    gw = GarminWorkout()
    gw.login()

    # Bieg łatwy
    gw.easy_run("Regeneracja 35 min", 35, "2026-06-15")

    # Interwały progowe
    gw.threshold_intervals("5x3min progowe", 5, 180, 120, "5:00", "5:10", "2026-06-16")

    # Tempo ciągłe
    gw.tempo_run("Tempo 25 min", 25, "5:00", "5:10", 10, 10, "2026-06-19")

    # Długie wybieganie
    gw.long_run("Długie 15 km", 5100, "2026-06-21")
"""
import logging
import os
import sys
import argparse
from datetime import date
from garminconnect import Garmin
from garminconnect.workout import (
    RunningWorkout, WorkoutSegment, ExecutableStep, StepType, TargetType,
)
from .config import GARMIN_EMAIL, GARMIN_PASSWORD
from services.workout_registry import record_added, record_deleted, find_workout

logger = logging.getLogger(__name__)

# Maps the 'kind' stored in the registry to the builder method that recreates it,
# so a deleted workout can be re-uploaded from its log entry alone.
_BUILDERS = {
    'easy_run': 'easy_run',
    'easy_run_zoned': 'easy_run_zoned',
    'long_run': 'long_run',
    'hr_zone_run': 'hr_zone_run',
    'tempo_run': 'tempo_run',
    'threshold_intervals': 'threshold_intervals',
    'strides': 'strides',
}


class GarminWorkout:
    """Wrapper around Garmin Connect API for creating & scheduling running workouts."""

    def __init__(self, email=None, password=None):
        self.email = email or GARMIN_EMAIL
        self.password = password or GARMIN_PASSWORD
        self.api = None

    def login(self):
        """Log in to Garmin Connect.

        Uses GARMIN_EMAIL/GARMIN_PASSWORD when both are set. Otherwise falls back
        to the cached GarminDB OAuth token store (~/.GarminDb/garmin_tokens.json),
        which the daily sync already keeps fresh — so no password is needed.
        """
        if self.email and self.password:
            logger.info("Logging in to Garmin Connect as %s", self.email)
            self.api = Garmin(self.email, self.password)
            self.api.login()
            logger.info("Garmin Connect login successful")
            return self

        logger.info("No GARMIN_EMAIL/GARMIN_PASSWORD set — using cached GarminDB tokens")
        from garmindb.garmin_connect_auth_adapter import GarminConnectAuthAdapter
        from garmindb.garmin_connect_config_manager import GarminConnectConfigManager

        adapter = GarminConnectAuthAdapter(GarminConnectConfigManager())
        adapter.login()
        self.api = adapter.client
        logger.info("Garmin Connect login successful (cached token)")
        return self

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pace_to_ms(pace_str):
        """'5:00' -> 3.33 m/s"""
        parts = pace_str.strip().split(':')
        total_sec = int(parts[0]) * 60 + int(parts[1])
        return round(1000.0 / total_sec, 4)

    @staticmethod
    def _make_step(step_order, step_type_id, step_type_key, duration_sec,
                   target_type_id=1, target_type_key="no.target",
                   target_value_one=None, target_value_two=None,
                   zone_number=None, distance_m=None):
        """Build an ExecutableStep with an optional pace or HR-zone target.

        Pace targets use targetValueOne/Two (m/s). Heart-rate targets use
        zone_number instead — Garmin resolves it against the zones configured
        on the watch, which is why `hr_zone_run` needs no bpm values.

        Pass `distance_m` to end the step on distance (metres) instead of time.
        """
        if distance_m is not None:
            end_condition = {"conditionTypeId": 3, "conditionTypeKey": "distance",
                             "displayOrder": 3, "displayable": True}
            end_value = float(distance_m)
        else:
            end_condition = {"conditionTypeId": 2, "conditionTypeKey": "time",
                             "displayOrder": 2, "displayable": True}
            end_value = float(duration_sec)

        step = ExecutableStep(
            stepOrder=step_order,
            stepType={"stepTypeId": step_type_id, "stepTypeKey": step_type_key, "displayOrder": step_type_id},
            endCondition=end_condition,
            endConditionValue=end_value,
            targetType={"workoutTargetTypeId": target_type_id, "workoutTargetTypeKey": target_type_key, "displayOrder": target_type_id},
        )
        if zone_number is not None:
            step.zoneNumber = zone_number
            step.targetValueOne = None
            step.targetValueTwo = None
        elif target_value_one is not None:
            step.targetValueOne = target_value_one
            step.targetValueTwo = target_value_two
            step.targetValueUnit = None
            step.zoneNumber = None
        return step

    def _lookup_schedule_id(self, workout_id, date_str):
        """Find the calendar entry id for a freshly scheduled workout."""
        try:
            year, month = int(date_str[:4]), int(date_str[5:7])
            cal = self.api.get_scheduled_workouts(year, month)
        except Exception as e:
            logger.warning("Could not read calendar to resolve schedule id: %s", e)
            return None
        for item in (cal or {}).get('calendarItems') or []:
            if item.get('workoutId') == workout_id and item.get('itemType') == 'workout':
                return item.get('id')
        return None

    def _upload_and_schedule(self, name, total_sec, steps, date_str, spec=None):
        """Upload workout, schedule it, and log both to the workout registry."""
        seg = WorkoutSegment(
            segmentOrder=1,
            sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
            workoutSteps=steps,
        )
        w = RunningWorkout(
            workoutName=name,
            estimatedDurationInSecs=total_sec,
            workoutSegments=[seg],
        )
        try:
            logger.info("Uploading workout '%s' (%ds, %d steps)", name, total_sec, len(steps))
            r = self.api.upload_running_workout(w)
            wid = r["workoutId"]
            logger.info("Workout uploaded: ID=%d, scheduling for %s", wid, date_str)
            sched = self.api.schedule_workout(wid, date_str)
            schedule_id = sched.get('id') if isinstance(sched, dict) else None
            if schedule_id is None:
                # Garmin's schedule response does not always carry the id; without
                # it the workout cannot be removed from the calendar later.
                schedule_id = self._lookup_schedule_id(wid, date_str)
            logger.info("Workout scheduled successfully (schedule id %s)", schedule_id)

            record_added(name=name, date=date_str, workout_id=wid,
                         schedule_id=schedule_id,
                         spec={'name': name, 'date': date_str, **(spec or {})})
            return wid
        except Exception as e:
            logger.error("Failed to upload/schedule workout '%s': %s", name, e)
            print(f"  BLAD: Nie udalo sie wgrac/planowac treningu '{name}': {e}")
            raise

    # ------------------------------------------------------------------
    # Public workout builders
    # ------------------------------------------------------------------

    def easy_run(self, name, duration_min, date_str):
        """Prosty bieg regeneracyjny/bazowy bez targetu."""
        steps = [self._make_step(1, StepType.WARMUP, "warmup", duration_min * 60)]
        wid = self._upload_and_schedule(
            name, duration_min * 60, steps, date_str,
            spec={'kind': 'easy_run', 'duration_min': duration_min},
        )
        print(f"  {date_str} {name}: ID={wid}")
        return wid

    def long_run(self, name, duration_min, date_str):
        """Długie wybieganie, konwersacyjne tempo."""
        return self.easy_run(name, duration_min, date_str)

    def hr_zone_run(self, name, duration_min, zone_number, date_str,
                    warmup_min=6, warmup_pace_faster="7:00",
                    warmup_pace_slower="8:30"):
        """Bieg z alarmem strefy tętna.

        Garmin pilnuje górnej granicy strefy i ostrzega, gdy ją przekroczysz —
        co jest dokładnie tym, czego brakuje przy bieganiu w szarej strefie.

        `duration_min` to CAŁKOWITY czas biegu. Pierwsze `warmup_min` minut leci
        na tempo i BEZ alarmu strefy: na starcie tętno jest fizjologicznie
        niskie, więc alarm wyłby o "za niskim tętnie", zanim organizm wdroży
        pracę. Dopiero po rozgrzewce włącza się pilnowanie strefy.

        Args:
            zone_number: numer strefy w konfiguracji zegarka (1-5)
            warmup_min: rozgrzewka na tempo bez alarmu (0 = bez rozgrzewki)
        """
        main_min = max(0, duration_min - warmup_min)
        o = 1
        steps = []
        if warmup_min > 0:
            steps.append(self._make_step(
                o, StepType.WARMUP, "warmup", warmup_min * 60,
                target_type_id=TargetType.PACE_ZONE, target_type_key="pace.zone",
                target_value_one=self._pace_to_ms(warmup_pace_faster),
                target_value_two=self._pace_to_ms(warmup_pace_slower),
            ))
            o += 1
        steps.append(self._make_step(
            o, StepType.INTERVAL, "interval", main_min * 60,
            target_type_id=TargetType.HEART_RATE_ZONE, target_type_key="heart.rate.zone",
            zone_number=zone_number,
        ))
        wid = self._upload_and_schedule(
            name, duration_min * 60, steps, date_str,
            spec={'kind': 'hr_zone_run', 'duration_min': duration_min,
                  'zone_number': zone_number, 'warmup_min': warmup_min,
                  'warmup_pace_faster': warmup_pace_faster,
                  'warmup_pace_slower': warmup_pace_slower},
        )
        print(f"  {date_str} {name}: ID={wid}")
        return wid

    def easy_run_zoned(self, name, date_str, main_min, zone_number=2,
                       warmup_min=6, warmup_pace_faster="7:00",
                       warmup_pace_slower="8:30", warmup_km=None,
                       strides=0, stride_sec=20, stride_rest_sec=90,
                       stride_pace_faster=None, stride_pace_slower=None,
                       cooldown_min=0):
        """Bieg łatwy: rozgrzewka na tempo, reszta na strefę tętna.

        Rozgrzewka ma cel TEMPA, nie tętna. Na starcie tętno jest zawsze niskie
        (organizm jeszcze nie wdrożył pracy), więc alarm strefy wyłby o "za
        niskim tętnie" przez pierwsze minuty. Bieg na tempo załatwia ten
        problem: tempo podnosi tętno, zanim włączy się pilnowanie strefy.

        Args:
            main_min: czas części na tętno (rozgrzewka jest DODATKOWO, na wierzchu)
            warmup_min: rozgrzewka na tempo bez alarmu strefy (domyślnie 6 min
                w tempie 7:00-8:30/km — tempo, w którym wchodzi się w strefę 2)
            warmup_km: tryb kilometrowy, pozostałość po starszych treningach.
                Gdy podany, wygrywa nad `warmup_min` — dzięki temu stare wpisy
                z rejestru nadal odtwarzają się poprawnie.
            strides: liczba przebieżek na koniec (0 = brak)
            stride_pace_*: cel tempa przebieżek; bez nich przebieżki nie mają
                celu i zegarek nie daje żadnej informacji zwrotnej
            cooldown_min: trucht na koniec po przebieżkach (0 = brak)
        """
        o = 1
        steps = []
        if warmup_km is not None:
            # Tryb z odtwarzania starych wpisów rejestru: kilometr na tempo.
            steps.append(self._make_step(
                o, StepType.WARMUP, "warmup", 0,
                target_type_id=TargetType.PACE_ZONE, target_type_key="pace.zone",
                target_value_one=self._pace_to_ms(warmup_pace_faster),
                target_value_two=self._pace_to_ms(warmup_pace_slower),
                distance_m=warmup_km * 1000,
            ))
            o += 1
        elif warmup_min > 0:
            steps.append(self._make_step(
                o, StepType.WARMUP, "warmup", warmup_min * 60,
                target_type_id=TargetType.PACE_ZONE, target_type_key="pace.zone",
                target_value_one=self._pace_to_ms(warmup_pace_faster),
                target_value_two=self._pace_to_ms(warmup_pace_slower),
            ))
            o += 1

        steps.append(self._make_step(
            o, StepType.INTERVAL, "interval", main_min * 60,
            target_type_id=TargetType.HEART_RATE_ZONE, target_type_key="heart.rate.zone",
            zone_number=zone_number,
        ))
        o += 1

        stride_targets = {}
        if stride_pace_faster and stride_pace_slower:
            stride_targets = {
                'target_type_id': TargetType.PACE_ZONE,
                'target_type_key': 'pace.zone',
                'target_value_one': self._pace_to_ms(stride_pace_faster),
                'target_value_two': self._pace_to_ms(stride_pace_slower),
            }
        for i in range(strides):
            steps.append(self._make_step(o, StepType.INTERVAL, "interval",
                                         stride_sec, **stride_targets))
            o += 1
            if i < strides - 1:
                steps.append(self._make_step(o, StepType.RECOVERY, "recovery", stride_rest_sec))
                o += 1

        if cooldown_min > 0:
            # Celowo bez celu tempa ani strefy: po przebieżkach tętno jest
            # wysoko i alarm strefy wyłby przez pierwszą minutę.
            steps.append(self._make_step(o, StepType.COOLDOWN, "cooldown", cooldown_min * 60))

        # Distance steps carry metres in endConditionValue, so estimate the total
        # duration separately: warmup km at ~7:00/km, plus the timed steps.
        if warmup_km is not None:
            warmup_sec = warmup_km * 420
        else:
            warmup_sec = warmup_min * 60
        stride_sec_total = strides * stride_sec + max(0, strides - 1) * stride_rest_sec
        total = warmup_sec + main_min * 60 + stride_sec_total + cooldown_min * 60

        wid = self._upload_and_schedule(
            name, total, steps, date_str,
            spec={'kind': 'easy_run_zoned', 'main_min': main_min,
                  'zone_number': zone_number, 'warmup_min': warmup_min,
                  'warmup_pace_faster': warmup_pace_faster,
                  'warmup_pace_slower': warmup_pace_slower,
                  'strides': strides, 'stride_sec': stride_sec,
                  'stride_rest_sec': stride_rest_sec,
                  'stride_pace_faster': stride_pace_faster,
                  'stride_pace_slower': stride_pace_slower,
                  'cooldown_min': cooldown_min},
        )
        print(f"  {date_str} {name}: ID={wid}")
        return wid

    def delete(self, workout_id, schedule_id=None, reason=None):
        """Usuń trening z biblioteki Garmina (i z kalendarza).

        schedule_id jest dobierany automatycznie z rejestru, jeśli nie podano.
        Usunięcie trafia do rejestru — trening da się później odtworzyć.
        """
        if schedule_id is None:
            entry = find_workout(workout_id)
            if entry:
                schedule_id = entry.get('schedule_id')
        if schedule_id is not None:
            try:
                self.api.unschedule_workout(schedule_id)
                logger.info("Unscheduled workout %s (schedule %s)", workout_id, schedule_id)
            except Exception as e:
                logger.warning("Could not unschedule %s: %s", schedule_id, e)
        self.api.delete_workout(workout_id)
        record_deleted(workout_id, schedule_id=schedule_id, reason=reason)
        logger.info("Deleted workout %s", workout_id)
        print(f"  Usunieto trening ID={workout_id}")

    def tempo_run(self, name, tempo_min, pace_faster, pace_slower,
                  warmup_min=10, cooldown_min=10, date_str=None):
        """
        Ciągły bieg tempowy na progu.

        Args:
            tempo_min: czas trwania tempa w minutach
            pace_faster: szybsza granica tempa (np. "5:00")
            pace_slower: wolniejsza granica tempa (np. "5:10")
        """
        if not date_str:
            date_str = name.split()[-1]  # fallback
        faster_ms = self._pace_to_ms(pace_faster)
        slower_ms = self._pace_to_ms(pace_slower)

        o = 1
        steps = []
        if warmup_min > 0:
            steps.append(self._make_step(o, StepType.WARMUP, "warmup", warmup_min * 60))
            o += 1
        steps.append(self._make_step(
            o, StepType.INTERVAL, "interval", tempo_min * 60,
            target_type_id=6, target_type_key="pace.zone",
            target_value_one=faster_ms, target_value_two=slower_ms,
        ))
        o += 1
        if cooldown_min > 0:
            steps.append(self._make_step(o, StepType.COOLDOWN, "cooldown", cooldown_min * 60))

        total = sum(s.endConditionValue for s in steps)
        wid = self._upload_and_schedule(
            name, total, steps, date_str,
            spec={'kind': 'tempo_run', 'tempo_min': tempo_min,
                  'pace_faster': pace_faster, 'pace_slower': pace_slower,
                  'warmup_min': warmup_min, 'cooldown_min': cooldown_min},
        )
        print(f"  {date_str} {name}: ID={wid}")
        return wid

    def threshold_intervals(self, name, num_intervals, work_sec, rest_sec,
                            pace_faster, pace_slower, warmup_min=10,
                            cooldown_min=10, date_str=None):
        """
        Interwały progowe z przerwami.

        Args:
            num_intervals: liczba powtórzeń
            work_sec: czas pracy w sekundach
            rest_sec: czas przerwy w sekundach (trucht)
        """
        if not date_str:
            date_str = ""
        faster_ms = self._pace_to_ms(pace_faster)
        slower_ms = self._pace_to_ms(pace_slower)

        o = 1
        steps = []
        if warmup_min > 0:
            steps.append(self._make_step(o, StepType.WARMUP, "warmup", warmup_min * 60))
            o += 1
        for i in range(num_intervals):
            steps.append(self._make_step(
                o, StepType.INTERVAL, "interval", work_sec,
                target_type_id=6, target_type_key="pace.zone",
                target_value_one=faster_ms, target_value_two=slower_ms,
            ))
            o += 1
            if i < num_intervals - 1 and rest_sec > 0:
                steps.append(self._make_step(o, StepType.RECOVERY, "recovery", rest_sec))
                o += 1
        if cooldown_min > 0:
            steps.append(self._make_step(o, StepType.COOLDOWN, "cooldown", cooldown_min * 60))

        total = sum(s.endConditionValue for s in steps)
        wid = self._upload_and_schedule(
            name, total, steps, date_str,
            spec={'kind': 'threshold_intervals', 'num_intervals': num_intervals,
                  'work_sec': work_sec, 'rest_sec': rest_sec,
                  'pace_faster': pace_faster, 'pace_slower': pace_slower,
                  'warmup_min': warmup_min, 'cooldown_min': cooldown_min},
        )
        print(f"  {date_str} {name}: ID={wid}")
        return wid

    def strides(self, name, base_min, num_strides, date_str,
                pace_faster="3:30", pace_slower="4:00",
                stride_sec=20, rest_sec=90):
        """
        Bieg bazowy + przebieżki (krótkie przyspieszenia).

        Args:
            base_min: czas biegu bazowego przed przebieżkami
            num_strides: liczba przebieżek
            stride_sec: czas jednej przebieżki (domyślnie 20s)
            rest_sec: przerwa między przebieżkami (domyślnie 90s)
        """
        faster_ms = self._pace_to_ms(pace_faster)
        slower_ms = self._pace_to_ms(pace_slower)

        o = 1
        steps = []
        steps.append(self._make_step(o, StepType.WARMUP, "warmup", base_min * 60))
        o += 1
        for i in range(num_strides):
            steps.append(self._make_step(
                o, StepType.INTERVAL, "interval", stride_sec,
                target_type_id=6, target_type_key="pace.zone",
                target_value_one=faster_ms, target_value_two=slower_ms,
            ))
            o += 1
            if i < num_strides - 1:
                steps.append(self._make_step(o, StepType.RECOVERY, "recovery", rest_sec))
                o += 1
        steps.append(self._make_step(o, StepType.COOLDOWN, "cooldown", 150.0))

        total = sum(s.endConditionValue for s in steps)
        wid = self._upload_and_schedule(
            name, total, steps, date_str,
            spec={'kind': 'strides', 'base_min': base_min,
                  'num_strides': num_strides, 'stride_sec': stride_sec,
                  'rest_sec': rest_sec, 'pace_faster': pace_faster,
                  'pace_slower': pace_slower},
        )
        print(f"  {date_str} {name}: ID={wid}")
        return wid

    def restore(self, entry, date_str=None):
        """Odtwórz trening z wpisu rejestru.

        Preferuje surową definicję z Garmina (odtwarza trening dokładnie tak,
        jak wyglądał). Gdy jej nie ma, odbudowuje trening z argumentów buildera.

        Args:
            entry: wpis z services.workout_registry (albo samo pole 'spec')
            date_str: nowa data; domyślnie oryginalna z rejestru
        """
        if 'event' not in entry and 'kind' in entry:
            entry = {'spec': entry, 'date': entry.get('date')}

        definition = entry.get('definition')
        date_str = date_str or entry.get('date')
        if definition:
            return self._upload_definition(definition, date_str)

        args = dict(entry.get('spec') or {})
        kind = args.pop('kind', None)
        if kind not in _BUILDERS:
            raise ValueError(f"Nieznany typ treningu w rejestrze: {kind!r}")
        args['date_str'] = date_str
        return getattr(self, _BUILDERS[kind])(**args)

    def _upload_definition(self, definition, date_str):
        """Wgraj trening z surowej definicji Garmina (verbatim)."""
        w = RunningWorkout(**definition)
        r = self.api.upload_running_workout(w)
        wid = r["workoutId"]
        sched = self.api.schedule_workout(wid, date_str)
        schedule_id = sched.get('id') if isinstance(sched, dict) else None
        record_added(name=definition.get('workoutName'), date=date_str, workout_id=wid,
                     schedule_id=schedule_id, definition=definition, source='restore')
        print(f"  {date_str} {definition.get('workoutName')}: ID={wid} (odtworzony)")
        return wid


# ------------------------------------------------------------------
# CLI: szybkie tworzenie treningu z linii komend
# ------------------------------------------------------------------
def _positive_int(value):
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('wymagana dodatnia liczba całkowita') from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError('wymagana dodatnia liczba całkowita')
    return parsed


def _iso_date(value):
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('wymagana data ISO RRRR-MM-DD') from error
    return value


def create_workout(kind, name, **kwargs):
    """Zaloguj się i utwórz trening opisany przez jawne argumenty."""
    gw = GarminWorkout().login()
    builders = {
        'easy': lambda: gw.easy_run(name, kwargs['minutes'], kwargs['date']),
        'tempo': lambda: gw.tempo_run(name, kwargs['minutes'], kwargs['pace_from'],
                                      kwargs['pace_to'], date_str=kwargs['date']),
        'intervals': lambda: gw.threshold_intervals(
            name, kwargs['repeats'], kwargs['work_seconds'], kwargs['rest_seconds'],
            kwargs['pace_from'], kwargs['pace_to'], date_str=kwargs['date']),
        'long': lambda: gw.long_run(name, kwargs['minutes'], kwargs['date']),
        'strides': lambda: gw.strides(name, kwargs['base_minutes'], kwargs['repeats'], kwargs['date']),
    }
    return builders[kind]()


def legacy_main(argv=None):
    """Samodzielny, zgodny wstecz CLI tworzenia treningów."""
    parser = argparse.ArgumentParser(description='Tworzy trening Garmin')
    sub = parser.add_subparsers(dest='kind', required=True)

    def command(kind, fields):
        item = sub.add_parser(kind)
        item.add_argument('name')
        for field, type_ in fields:
            item.add_argument(field, type=type_)

    command('easy', [('minutes', _positive_int), ('date', _iso_date)])
    command('tempo', [('minutes', _positive_int), ('pace_from', str), ('pace_to', str), ('date', _iso_date)])
    command('intervals', [('repeats', _positive_int), ('work_seconds', _positive_int), ('rest_seconds', _positive_int), ('pace_from', str), ('pace_to', str), ('date', _iso_date)])
    command('long', [('minutes', _positive_int), ('date', _iso_date)])
    command('strides', [('base_minutes', _positive_int), ('repeats', _positive_int), ('date', _iso_date)])
    args = vars(parser.parse_args(argv))
    kind, name = args.pop('kind'), args.pop('name')
    create_workout(kind, name, **args)
    return 0


if __name__ == "__main__":
    raise SystemExit(legacy_main())
