# -*- coding: utf-8 -*-
"""Odtwarzanie treningów usuniętych z Garmina."""
from services.workout_registry import record_added, record_deleted
from trainer.commands.workout_restore import main


class _Session:
    def __init__(self):
        self.restored = []

    def restore(self, entry, date_str=None):
        self.restored.append((entry["workout_id"], date_str))


def test_lists_deleted_workouts_and_restores_one(capsys):
    record_added("Łatwy 40 min – Z2", "2026-10-29", 11, spec={"kind": "easy_run", "duration_min": 40})
    record_added("Tempo 30 min", "2026-10-30", 12, spec={"kind": "easy_run", "duration_min": 30})
    record_deleted(11, reason="zastąpiony planem")

    assert main() == 0
    listing = capsys.readouterr().out
    assert "11  2026-10-29  Łatwy 40 min – Z2  (zastąpiony planem)" in listing and "Tempo" not in listing

    session = _Session()
    assert main(11, "2026-11-02", session_factory=lambda: session) == 0
    assert session.restored == [(11, "2026-11-02")]
    assert main(12, session_factory=lambda: session) == 1  # aktywnego nie ma czego odtwarzać
    assert main(99, session_factory=lambda: session) == 1
