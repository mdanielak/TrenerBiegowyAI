import builtins
from trainer.commands import workout_new


class Tty:
    def isatty(self): return True


def test_confirmation_gate_does_not_create(monkeypatch):
    answers = iter(['1', 'Test', '2099-01-01', '30', 'n'])
    monkeypatch.setattr(builtins, 'input', lambda _: next(answers))
    monkeypatch.setattr(workout_new.sys, 'stdin', Tty())
    called = []
    monkeypatch.setattr('trainer.garmin_workouts.create_workout', lambda *a, **k: called.append(a))
    assert workout_new.main() == 0
    assert not called


def test_invalid_date_and_pace_reprompt(monkeypatch):
    answers = iter(['2', 'Test', '2000-01-01', '2099-01-01', '20', 'bad', '5:00', '5:15', 'n'])
    monkeypatch.setattr(builtins, 'input', lambda _: next(answers))
    monkeypatch.setattr(workout_new.sys, 'stdin', Tty())
    assert workout_new.main() == 0


def test_non_tty_returns_error(monkeypatch):
    monkeypatch.setattr(workout_new.sys.stdin, 'isatty', lambda: False)
    assert workout_new.main() == 2
