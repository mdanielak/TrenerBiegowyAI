import json
import sys
import types

from trainer import cli


def test_no_arguments_prints_setup_hint(capsys):
    assert cli.main([]) == 2
    assert 'trainer setup' in capsys.readouterr().out


def test_new_command_wiring(monkeypatch):
    module = types.ModuleType('trainer.commands.workout_new')
    module.main = lambda: 0
    monkeypatch.setitem(sys.modules, 'trainer.commands.workout_new', module)
    assert cli.main(['workouts', 'new']) == 0


def test_error_mapping_has_no_traceback(monkeypatch, capsys):
    module = types.ModuleType('trainer.commands.sync')
    module.main = lambda fresh=False: (_ for _ in ()).throw(ModuleNotFoundError('x'))
    monkeypatch.setitem(sys.modules, 'trainer.commands.sync', module)
    assert cli.main(['sync']) == 3
    assert 'Traceback' not in capsys.readouterr().err


def test_debug_prints_traceback(monkeypatch, capsys):
    module = types.ModuleType('trainer.commands.sync')
    module.main = lambda fresh=False: (_ for _ in ()).throw(FileNotFoundError('profile.json'))
    monkeypatch.setitem(sys.modules, 'trainer.commands.sync', module)
    assert cli.main(['--debug', 'sync']) == 5
    assert 'Traceback' in capsys.readouterr().err
