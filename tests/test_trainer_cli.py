"""Tests for the thin shared trainer CLI; all external operations are mocked."""
import sys
import types
import unittest
from unittest.mock import patch

from trainer import cli


class TrainerCliTests(unittest.TestCase):
    def test_help_and_version(self):
        with self.assertRaises(SystemExit) as help_exit:
            cli.main(['--help'])
        self.assertEqual(help_exit.exception.code, 0)
        with self.assertRaises(SystemExit) as version_exit:
            cli.main(['--version'])
        self.assertEqual(version_exit.exception.code, 0)

    def test_sync_dispatches_fresh_flag(self):
        module = types.ModuleType('trainer.commands.sync')
        calls = []
        setattr(module, 'main', lambda fresh=False: calls.append(fresh))
        with patch.dict(sys.modules, {'trainer.commands.sync': module}):
            self.assertEqual(cli.main(['sync', '--fresh']), 0)
        self.assertEqual(calls, [True])

    def test_create_dispatches_to_shared_builder(self):
        module = types.ModuleType('trainer.workouts')
        calls = []
        setattr(module, 'create_workout', lambda kind, name, **kwargs: calls.append((kind, name, kwargs)))
        with patch.dict(sys.modules, {'trainer.workouts': module}):
            self.assertEqual(cli.main(['workouts', 'create', 'easy', 'Lekki', '30', '2026-10-01']), 0)
        self.assertEqual(calls, [('easy', 'Lekki', {'minutes': 30, 'date': '2026-10-01'})])

    def test_invalid_number_and_date_do_not_import_garmin(self):
        with patch.dict(sys.modules, {'trainer.workouts': None}):
            with self.assertRaises(SystemExit) as number_exit:
                cli.main(['workouts', 'create', 'easy', 'Lekki', '0', '2026-10-01'])
            self.assertEqual(number_exit.exception.code, 2)
            with self.assertRaises(SystemExit) as date_exit:
                cli.main(['workouts', 'create', 'easy', 'Lekki', '30', '01-10-2026'])
            self.assertEqual(date_exit.exception.code, 2)

    def test_privacy_code_is_passed_through(self):
        package = types.ModuleType('scripts')
        module = types.ModuleType('scripts.check_privacy')
        setattr(module, 'main', lambda: 2)
        with patch.dict(sys.modules, {'scripts': package, 'scripts.check_privacy': module}):
            self.assertEqual(cli.main(['privacy-check']), 2)

    def test_ai_configuration_error_is_preserved(self):
        module = types.ModuleType('trainer.commands.analyze')
        seen = []
        def analyze(**kwargs):
            seen.append(kwargs)
            return 3
        setattr(module, 'main', analyze)
        with patch.dict(sys.modules, {'trainer.commands.analyze': module}):
            self.assertEqual(cli.main(['analyze', '--ai']), 3)
        self.assertEqual(seen, [{'use_ai': True, 'strict_ai': True}])

    def test_doctor_is_lazily_dispatched(self):
        module = types.ModuleType('trainer.doctor')
        setattr(module, 'main', lambda: 3)
        with patch.dict(sys.modules, {'trainer.doctor': module}):
            self.assertEqual(cli.main(['doctor']), 3)

    def test_unexpected_runtime_error_is_reported_without_traceback(self):
        module = types.ModuleType('trainer.commands.sync')
        setattr(module, 'main', lambda fresh=False: (_ for _ in ()).throw(Exception('awaria')))
        with patch.dict(sys.modules, {'trainer.commands.sync': module}):
            with patch('sys.stderr') as stderr:
                self.assertEqual(cli.main(['sync']), 1)
        self.assertIn('BŁĄD wykonania: awaria', ''.join(call.args[0] for call in stderr.write.call_args_list))


if __name__ == '__main__':
    unittest.main()
