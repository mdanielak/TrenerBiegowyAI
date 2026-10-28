import os
import re
from pathlib import Path
import builtins
import types
from unittest import mock
import pytest

from trainer.env_file import load_env_file
from trainer.setup_wizard import _write_env
from trainer import setup_wizard, profile_store, preferences


def test_write_env_updates_without_duplicates_and_preserves_lines(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# zachowaj\nONE=old\nOTHER=value\nONE=older\n', encoding='utf8')
    _write_env(path, {'ONE': 'new value', 'NEW': 'pa ss#wo"rd\\'})
    text = path.read_text(encoding='utf8')
    assert '# zachowaj' in text and 'OTHER=value' in text
    assert text.count('ONE=') == 1 and "ONE='new value'" in text
    assert "NEW='pa ss#wo\"rd\\'" in text


def test_write_env_round_trips_special_values(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    values = {'PASSWORD': 'pa ss#wo"rd\\', 'HEALTH_DATA_DIR': r'C:\Moje dane\Health Data'}
    _write_env(path, values)
    monkeypatch.delenv('PASSWORD', raising=False)
    monkeypatch.delenv('HEALTH_DATA_DIR', raising=False)
    assert load_env_file(path, override=True) == values


def test_write_env_removes_all_legacy_garmin_passwords(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# comment\nGARMIN_PASSWORD=old\nexport GARMIN_PASSWORD = older\nAI_API_KEY=keep\n')
    _write_env(path, {'GARMIN_PASSWORD': 'never-save', 'GARMIN_EMAIL': 'runner@example.com'})
    text = path.read_text()
    assert 'GARMIN_PASSWORD' not in text
    assert 'never-save' not in text
    assert '# comment\nAI_API_KEY=keep\n' in text
    assert 'GARMIN_EMAIL=runner@example.com' in text
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600


def test_load_env_excludes_legacy_password(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('GARMIN_PASSWORD=unused\nGARMIN_EMAIL=runner@example.com\n')
    monkeypatch.delenv('GARMIN_PASSWORD', raising=False)
    monkeypatch.delenv('GARMIN_EMAIL', raising=False)
    assert load_env_file(path, exclude={'GARMIN_PASSWORD'}) == {'GARMIN_EMAIL': 'runner@example.com'}
    assert 'GARMIN_PASSWORD' not in os.environ


def test_write_env_skips_empty_values(tmp_path):
    path = tmp_path / '.env'
    path.write_text('KEEP=old\n', encoding='utf8')
    _write_env(path, {'EMPTY': '', 'KEEP': ''})
    assert path.read_text(encoding='utf8') == 'KEEP=old\n'


def test_write_env_quoting_matrix_round_trips(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    values = {
        'BARE': 'simple_value-1', 'SPACES': 'two words',
        'WINDOWS': r'C:\Moje dane\Health Data', 'HASH': 'a#b',
        'DOUBLE': 'a"b', 'SINGLE': "a'b", 'BOTH': "a'\"b\\",
        'SLASH': '\\',
    }
    _write_env(path, values)
    for key in values: monkeypatch.delenv(key, raising=False)
    assert load_env_file(path, override=True) == values
    text = path.read_text(encoding='utf8')
    assert "SPACES='two words'" in text
    assert 'BOTH="a\'\\"b\\\\"' in text


def test_write_env_rejects_newline(tmp_path):
    with pytest.raises(ValueError, match='NOWA'):
        _write_env(tmp_path / '.env', {'NOWA': 'a\nb'})


class _Tty:
    def isatty(self): return True


class _OfflineGarmin:
    """Atrapa klienta: logowanie zawodzi, więc kreator idzie ścieżką ręczną."""
    def __init__(self, **kwargs): pass
    def login(self): raise RuntimeError('brak sieci w testach')


def _answers(mapping, default=''):
    """Odpowiadaj na podstawie treści pytania, nie jego pozycji.

    Pozycyjne listy odpowiedzi rozjeżdżały się przy każdej zmianie
    kolejności pytań w kreatorze; dopasowanie po treści jest odporne.
    """
    compiled = [(re.compile(pattern, re.IGNORECASE), value) for pattern, value in mapping]
    def answer(prompt):
        for pattern, value in compiled:
            if pattern.search(prompt):
                return value
        return default
    return answer


@pytest.fixture(autouse=True)
def _disable_terminal_getpass(monkeypatch):
    """Testy bez sekretu nie mogą próbować czytać prawdziwego terminala."""
    monkeypatch.setattr(setup_wizard.getpass, 'getpass', lambda prompt: '')


def _redirect_stores(monkeypatch, tmp_path):
    settings = types.SimpleNamespace(runner_profile_local=tmp_path / 'profile.json', local_dir=tmp_path)
    monkeypatch.setattr(profile_store, 'SETTINGS', settings)
    monkeypatch.setattr(preferences, 'SETTINGS', settings)
    monkeypatch.setattr(setup_wizard, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(setup_wizard, 'has_token', lambda: False)
    monkeypatch.setattr(setup_wizard, 'ensure_token', lambda email, password, **kwargs: object())
    monkeypatch.setattr(setup_wizard, 'ensure_garmindb_config', lambda email: False)


@pytest.mark.parametrize('token_state', ['missing', 'valid', 'expired'])
def test_wizard_happy_path_writes_files_without_echoing_secrets(monkeypatch, tmp_path, capsys, token_state):
    _redirect_stores(monkeypatch, tmp_path)
    monkeypatch.setattr(setup_wizard, 'has_token', lambda: token_state != 'missing')
    attempts = []
    def login(email, password, **kwargs):
        attempts.append(password)
        if token_state == 'expired' and password is None:
            raise setup_wizard.GarminAuthError('Zaloguj ponownie', retry_credentials=True)
        return object()
    monkeypatch.setattr(setup_wizard, 'ensure_token', login)
    (tmp_path / '.env').write_text('GARMIN_PASSWORD=legacy-secret\nKEEP=value\n')
    monkeypatch.setattr('trainer.garmin_workouts.GarminWorkout', _OfflineGarmin)
    answers = _answers([
        (r'E-mail', 'runner@example.com'),
        (r'Hasło Garmin', 'sekret#haslo'),
        (r'Katalog danych', str(tmp_path / 'health')),
        (r'Użyć tych danych', 'n'),
        (r'Wiek', '35'),
        (r'Waga', '70'),
        (r'Wzrost', '180'),
        (r'Tętno maksymalne', '190'),
        (r'Tętno spoczynkowe', '50'),
        (r'mleczanowy', '170'),
        (r'Wybierz numer', '3'),
        (r'Zakładany czas', '1:49:00'),
        (r'Data celu', '2027-05-01'),
        (r'Aktualny rekord', '1:45:00'),
        (r'trenujesz', 'n'),
        (r'Zatwierdzasz ten plan', 'n'),
        (r'minuty \(', '0'),
        (r'intensywnych sesji', '2'),
        (r'AI_BASE_URL', 'https://api.example/v1'),
        (r'AI_MODEL', 'model'),
        (r'AI_API_KEY', 'tajny-klucz'),
        (r'Włączyć opcjonalne', 't'),
        (r'zgodę na eksport', 't'),
        (r'Zapisać ustawienia', 't'),
    ])
    monkeypatch.setattr(builtins, 'input', answers)
    monkeypatch.setattr(setup_wizard.getpass, 'getpass', answers)
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    profile = profile_store.load_profile()
    assert profile['age'] == 35 and profile['target_hm'] == 'półmaraton 1:49:00'
    assert profile['hr_max'] == 190 and profile['lactate_threshold_hr'] == 170
    assert preferences.load_preferences()['max_quality_sessions_per_week'] == 2
    env = (tmp_path / '.env').read_text(encoding='utf8')
    assert 'sekret#haslo' not in env and 'GARMIN_PASSWORD' not in env
    assert 'tajny-klucz' in env and 'KEEP=value' in env
    assert 'legacy-secret' not in env
    assert attempts == {'missing': ['sekret#haslo'], 'valid': [None],
                        'expired': [None, 'sekret#haslo']}[token_state]
    output = capsys.readouterr().out
    assert 'sekret#haslo' not in output and 'tajny-klucz' not in output


def test_wizard_zone_sync_survives_final_profile_write(monkeypatch, tmp_path):
    _redirect_stores(monkeypatch, tmp_path)
    profile_store.save_profile({'age': 30, 'weight_kg': 60, 'height_cm': 170, 'hr_max': 180, 'hr_rest': 50, 'lactate_threshold_hr': 160})
    class Workout:
        api = object()
        def __init__(self, **kwargs): pass
        def login(self): return self
    monkeypatch.setattr('trainer.garmin_workouts.GarminWorkout', Workout)
    monkeypatch.setattr(setup_wizard, 'fetch_snapshot', lambda api: {
        'age': 31, 'weight': 61, 'height': 171, 'hr_max': 190, 'hr_rest': 51,
        'lactate_threshold_hr': 170, 'hr_zone_floors': {'z1': 100, 'z2': 120, 'z3': 140, 'z4': 160, 'z5': 175}})
    answers = _answers([
        (r'Katalog', str(tmp_path / 'health')), (r'Użyć tych danych', 't'),
        (r'Wybierz numer', '3'), (r'Zakładany czas', ''), (r'Data celu', ''), (r'Aktualny rekord', ''),
        (r'Zatwierdzasz', 't'), (r'intensywnych', '0'), (r'Włączyć', 'n'), (r'Zapisać', 'n'),
    ])
    monkeypatch.setattr(builtins, 'input', answers)
    monkeypatch.setattr(setup_wizard.getpass, 'getpass', answers)
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    result = profile_store.load_profile()
    assert result['age'] == 31 and result['hr_zone_floors'] == {'z1': 100, 'z2': 120, 'z3': 140, 'z4': 160, 'z5': 175}
    assert 'Garmin Connect' in result['hr_zones_source']
    assert result['hr_zones'] == 'Z1 100-119, Z2 120-139, Z3 140-159, Z4 160-174, Z5 175-190'


def test_weekly_proposal_approval_avoids_daily_questions(monkeypatch, tmp_path):
    _redirect_stores(monkeypatch, tmp_path)
    existing = preferences.load_preferences()
    existing['days']['tue'] = {'available': True, 'min_minutes': 40, 'max_minutes': 50}
    preferences.save_preferences(existing)
    prompts = []
    monkeypatch.setattr('trainer.garmin_workouts.GarminWorkout', _OfflineGarmin)
    answers = _answers([(r'E-mail', 'x@example.com'), (r'Hasło', ''), (r'Katalog', str(tmp_path)),
                        (r'Wiek', '35'), (r'Waga', '70'), (r'Wzrost', '180'), (r'maksymalne', '190'),
                         (r'spoczynkowe', '50'), (r'mleczanowy', '170'), (r'Wybierz numer', '3'), (r'Zakładany czas', ''),
                        (r'Data celu', '2027-01-01'), (r'Aktualny rekord', 'x'),
                        (r'Zatwierdzasz', 't'), (r'intensywnych', '2'), (r'Włączyć', 'n'), (r'Zapisać', 'n')])
    monkeypatch.setattr(builtins, 'input', lambda prompt: prompts.append(prompt) or answers(prompt))
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    assert not any('trenujesz' in prompt or 'minimum minut' in prompt for prompt in prompts)
    assert preferences.get_weekly_availability('tue') == {'available': True, 'min_minutes': 40, 'max_minutes': 50}


def test_weekly_proposal_rejection_asks_daily_questions(monkeypatch, tmp_path):
    _redirect_stores(monkeypatch, tmp_path)
    prefs = preferences.load_preferences(); prefs['days']['mon']['available'] = True; preferences.save_preferences(prefs)
    prompts = []
    monkeypatch.setattr('trainer.garmin_workouts.GarminWorkout', _OfflineGarmin)
    answers = _answers([(r'E-mail', 'x'), (r'Katalog', str(tmp_path)), (r'Wiek', '35'), (r'Waga', '70'),
                        (r'Wzrost', '180'), (r'maksymalne', '190'), (r'spoczynkowe', '50'), (r'mleczanowy', '170'),
                        (r'Wybierz numer', '3'), (r'Zakładany czas', ''), (r'Data celu', '2027-01-01'), (r'Aktualny rekord', 'x'),
                        (r'Zatwierdzasz', 'n'), (r'trenujesz', 'n'), (r'intensywnych', '0'), (r'Włączyć', 'n'), (r'Zapisać', 'n')])
    monkeypatch.setattr(builtins, 'input', lambda prompt: prompts.append(prompt) or answers(prompt))
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    assert any('trenujesz' in prompt for prompt in prompts)


def test_weekly_proposal_uses_garmin_days_and_long_range():
    proposal = setup_wizard._weekly_proposal({}, {'available_training_days': ['tue'], 'long_training_days': ['sun']})
    assert proposal['tue'] == {'available': True, 'min_minutes': 35, 'max_minutes': 45}
    assert proposal['sun'] == {'available': True, 'min_minutes': 60, 'max_minutes': 90}


def test_target_goal_half_marathon_time(monkeypatch):
    monkeypatch.setattr(builtins, 'input', _answers([(r'Wybierz numer', '3'), (r'Zakładany czas', '1:49:00')]))
    assert setup_wizard._target_goal({}) == {'target_race': 'półmaraton', 'target_time': '1:49:00', 'target_hm': 'półmaraton 1:49:00'}


def test_target_goal_no_race_skips_time(monkeypatch):
    prompts = []
    answers = _answers([(r'Wybierz numer', '6')])
    monkeypatch.setattr(builtins, 'input', lambda prompt: prompts.append(prompt) or answers(prompt))
    assert setup_wizard._target_goal({}) == {'target_race': 'brak', 'target_time': '', 'target_hm': 'brak'}
    assert not any('Zakładany czas' in prompt for prompt in prompts)


def test_target_goal_other_and_invalid_choice_reprompts(monkeypatch):
    answers = iter(['9', '5', 'Bieg górski', '2:00:00'])
    monkeypatch.setattr(builtins, 'input', lambda prompt: next(answers))
    assert setup_wizard._target_goal({})['target_race'] == 'Bieg górski'


@pytest.mark.parametrize(('answers', 'expected'), [(['30-45'], (30, 45)), (['30'], (30, 30)), ([''], (20, 40)), (['45-30', '30-45'], (30, 45)), (['abc', '30'], (30, 30))])
def test_minutes_range(monkeypatch, answers, expected):
    inputs = iter(answers)
    monkeypatch.setattr(builtins, 'input', lambda prompt: next(inputs))
    assert setup_wizard._minutes_range('Minuty', 20, 40) == expected


def test_weekly_rejection_asks_minutes_once_per_available_day(monkeypatch, tmp_path):
    _redirect_stores(monkeypatch, tmp_path)
    prefs = preferences.load_preferences(); prefs['days']['mon'] = {'available': True, 'min_minutes': 30, 'max_minutes': 45}; preferences.save_preferences(prefs)
    prompts = []
    monkeypatch.setattr('trainer.garmin_workouts.GarminWorkout', _OfflineGarmin)
    answers = _answers([(r'E-mail', 'x'), (r'Katalog', str(tmp_path)), (r'Wiek', '35'), (r'Waga', '70'), (r'Wzrost', '180'),
                        (r'maksymalne', '190'), (r'spoczynkowe', '50'), (r'mleczanowy', '170'), (r'Wybierz numer', '6'),
                        (r'Data celu', ''), (r'Aktualny rekord', ''), (r'Zatwierdzasz', 'n'), (r'Pon: trenujesz', 't'), (r'trenujesz', 'n'),
                        (r'minuty \(', '30-45'), (r'intensywnych', '0'), (r'Włączyć', 'n'), (r'Zapisać', 'n')])
    monkeypatch.setattr(builtins, 'input', lambda prompt: prompts.append(prompt) or answers(prompt))
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    assert sum('minuty (np.' in prompt for prompt in prompts) == 1


def test_wizard_retries_password_then_allows_manual_mode(monkeypatch, tmp_path):
    _redirect_stores(monkeypatch, tmp_path)
    attempts = []
    def rejected(email, password, **kwargs):
        attempts.append(password)
        raise setup_wizard.GarminAuthError('błędne hasło', retry_credentials=True)
    monkeypatch.setattr(setup_wizard, 'ensure_token', rejected)
    answers = _answers([
        (r'E-mail', 'runner@example.com'),
        # Treść promptu zależy od tego, czy token już istnieje, więc
        # dopasowujemy wspólny fragment zamiast pełnej etykiety. Lookahead
        # chroni przed złapaniem promptu ponowienia, który też się tak zaczyna.
        (r'^Hasło Garmin(?!.*ponownie)', 'pierwsze'),
        (r'spróbuj ponownie', 'drugie'), (r'Kontynuować z ręcznym', 't'),
        (r'Katalog', str(tmp_path)), (r'Wiek', '35'), (r'Waga', '70'), (r'Wzrost', '180'),
        (r'maksymalne', '190'), (r'spoczynkowe', '50'), (r'mleczanowy', '170'),
        (r'Wybierz numer', '6'), (r'Data celu', ''), (r'Aktualny rekord', ''),
        (r'trenujesz', 'n'), (r'intensywnych', '0'), (r'Włączyć', 'n'), (r'Zapisać', 'n'),
    ])
    monkeypatch.setattr(builtins, 'input', answers)
    monkeypatch.setattr(setup_wizard.getpass, 'getpass', answers)
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    assert setup_wizard.main() == 0
    assert attempts == ['pierwsze', 'drugie', 'drugie']


@pytest.mark.parametrize('message', ['HTTP 429', 'Błąd połączenia SSO'])
def test_wizard_stops_on_noncredential_error(monkeypatch, tmp_path, capsys, message):
    _redirect_stores(monkeypatch, tmp_path)
    monkeypatch.setattr(setup_wizard, 'has_token', lambda: False)
    monkeypatch.setattr(setup_wizard.sys, 'stdin', _Tty())
    attempts = []
    def rejected(email, password, *, prompt_mfa):
        assert callable(prompt_mfa)
        attempts.append(password)
        raise setup_wizard.GarminAuthError(message)
    monkeypatch.setattr(setup_wizard, 'ensure_token', rejected)
    monkeypatch.setattr(builtins, 'input', _answers([
        (r'E-mail', 'runner@example.com'), (r'Katalog', str(tmp_path)),
        (r'Kontynuować z ręcznym', 'n'),
    ]))
    secrets = []
    def getpass(prompt):
        secrets.append(prompt)
        return ' secret '
    monkeypatch.setattr(setup_wizard.getpass, 'getpass', getpass)
    assert setup_wizard.main() == 1
    assert attempts == [' secret ']
    assert len(secrets) == 1
    output = capsys.readouterr().out
    assert 'Logowanie Garmin zakończone niepowodzeniem:' in output
    assert message in output
    assert ' secret ' not in output


def test_ask_secret_preserves_whitespace(monkeypatch):
    monkeypatch.setattr(setup_wizard.getpass, 'getpass', lambda prompt: ' secret ')
    assert setup_wizard._ask('Hasło Garmin', secret=True) == ' secret '


def test_ask_secret_uses_getpass_not_input(monkeypatch):
    def forbidden_input(prompt):
        if 'Hasło' in prompt:
            raise AssertionError('sekretny prompt nie może używać input')
        return ''
    monkeypatch.setattr(builtins, 'input', forbidden_input)
    monkeypatch.setattr(setup_wizard.getpass, 'getpass', lambda prompt: 'tajne-hasło')
    assert setup_wizard._ask('Hasło Garmin', secret=True) == 'tajne-hasło'
