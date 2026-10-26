# Graph Report - TrenerBiegowyAI  (2026-10-19)

## Corpus Check
- Large corpus: 281 files · ~658,552 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder.

## Summary
- 1706 nodes · 3837 edges · 98 communities (61 shown, 37 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 267 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Wydane zadania synchronizacji
- Audyt bezpieczeństwa i prywatności
- Testy rdzenia CLI trainer
- Obsługa błędów i importów
- Silnik oceny gotowości
- Zależności dev i narzędzia
- Logowanie do Garmina i testy
- Test połączenia z AI
- Komentarz trenera AI do treningu
- Raport tygodnia
- Ekstrakcja danych GarminDB
- Punktacja wykonania treningu
- Testy endpointów API
- System wizualny i granice UI
- Testy spójności grafik
- Endpointy health i readiness
- Testy raportu tygodniowego
- Zapis ustawień AI
- Testy akcji i CSRF
- Budowniki treningów Garmin
- Abstrakcja dostawcy AI
- Testy widoku dziś
- Trasy FastAPI i CSRF
- Logowanie i konfiguracja analizy
- Kontekst treningowy dla AI
- Podział odpowiedzialności projektu
- Dopasowanie aktywności do planu
- Rejestr operacji na Garminie
- Bezpieczne serwowanie assetów
- Kreator treningu i pytania
- Preferencje dostępności
- Cele i cel tygodniowy
- Raport dzisiejszy i testy
- Czas snapshotu i zadania sync
- Kreator konfiguracji profilu
- Rekomendacja dzienna AI
- Dostawca OpenAI-compatible
- Zmienne środowiskowe i .env
- Serwis widoku dziś
- Testy komendy profile
- Widoki analizy i tygodnia w API
- Magazyn profilu biegacza
- Blokady międzyprocesowe
- Testy ustawień AI
- Magazyn ocen treningów
- Blokada plikowa i testy
- Uruchamianie oceny treningu
- Plan treningowy CSV
- Akcje HTTP serwisu
- Odczyt planu na dziś
- Testy rejestru treningów
- Testy zapisu rejestru
- Izolowany rejestr w testach
- Zasada strefy 2 w treningach
- Spójność rejestru i harmonogramu
- Wgrywanie definicji treningu
- Wykonawcy operacji mutujących
- Snapshot danych data_latest
- Testy aktualizacji użycia
- Nazwa pliku planu tygodnia
- Ścieżki runtime projektu
- Dopasowywanie po przebudowie
- Logowanie przez tokeny
- Testy stref tętna
- Pobranie profilu z Garmina
- Wyszukiwanie pliku planu
- Testy widoku tygodnia
- Zmienne AI i eksport danych
- Dopasowanie po nazwie i lokalizacji
- Klasyfikacja aktualności snapshotu
- Sekcja treningu na dashboardzie
- Testy pobierania profilu
- Walidacja profilu dla AI
- Testy blokady plikowej
- Konwersja tempa i kompatybilność
- Ostatnie aktywności biegowe
- Wczytywanie planu JSON
- Rozwiązywanie katalogu bazy
- Kandydaci do usunięcia
- Nieaktualne treningi
- Rejestr append-only
- Odświeżanie liczników użycia
- Liczenie użycia po nazwie
- Obciążenie tygodniowe
- Inicjalizacja klienta Garmin
- Podsumowanie ekstrakcji
- Wczytywanie pliku .env
- Eksport planu do CSV
- Normalizacja danych z Garmina
- Wiek biegacza
- Walidacja zakresów pomiarów
- Kafelki sygnałów i trendy
- Testowy klient HTTP
- Limity czasu synchronizacji
- Atrapa klienta Garmin

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 75 edges
2. `JobStore` - 54 edges
3. `GarminWorkout` - 44 edges
4. `_report()` - 41 edges
5. `SnapshotStatus` - 34 edges
6. `main()` - 33 edges
7. `acquire_lock()` - 30 edges
8. `build_today_report()` - 23 edges
9. `compute_readiness_breakdown()` - 22 edges
10. `ensure_token()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Zasady długoterminowego trenera AI` --semantically_similar_to--> `Zasady bezpieczeństwa i danych (TRAINING_RULES)`  [INFERRED] [semantically similar]
  IMPORTANT_PROMPT.txt → docs/TRAINING_RULES.md
- `Reguły modyfikacji (czerwone flagi: HRV, RHR, sen, ból)` --semantically_similar_to--> `Intensywność i struktura treningu`  [INFERRED] [semantically similar]
  training-plans/long-term/half-marathon-2027.md → docs/TRAINING_RULES.md
- `create_app()` --uses--> `AIConnectionTestError`  [INFERRED]
  api/main.py → ai/connection_test.py
- `fail()` --calls--> `AIConnectionTestError`  [EXTRACTED]
  tests/test_api.py → ai/connection_test.py
- `TestOpenAICompatibleProvider` --uses--> `AIProviderError`  [INFERRED]
  tests/test_ai_provider.py → ai/openai_compatible.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Ochrona prywatności danych biegacza** — readme_prywatnosc, docs_security_audit_ochrona_danych, docs_prompt_technical_local_runtime_state, scripts_check_privacy [INFERRED 0.85]
- **Baza zasad trenera AI i strategii treningowej** — important_prompt_zasady_trenerskie, docs_training_rules_intensywnosc_struktura, training_plans_long_term_half_marathon_2027_reguly_modyfikacji, docs_prompt_training_json_schema [INFERRED 0.85]
- **Instrukcje uruchomienia na platformach** — docs_linux_setup_instalacja, docs_windows_description_platforma, readme_dashboard_lokalny [INFERRED 0.75]
- **Widoki lokalnego dashboardu (Jinja2, bez JS)** — templates_today, templates_week, templates_analysis, templates_settings, templates_job [INFERRED 0.85]
- **Prezentacja gotowości w UI (pierścień, wykres, analiza)** — templates_today_pierscien_gotowosci, templates_analysis_dlaczego_taka_ocena, templates_week_wykres_gotowosci, services_readiness [INFERRED 0.85]
- **Serwowanie lokalnego pakietu grafik przez /assets/** — templates__base_assety_lokalne, trener_biegowy_ai_assets_readme_pakiet_grafik, services_assets [INFERRED 0.85]

## Communities (98 total, 37 thin omitted)

### Community 0 - "Wydane zadania synchronizacji"
Cohesion: 0.07
Nodes (31): run_sync_job(), _arguments_hash(), JobConflictError, JobCooldownError, JobError, JobListResult, JobNotFoundError, JobRecord (+23 more)

### Community 1 - "Audyt bezpieczeństwa i prywatności"
Cohesion: 0.05
Nodes (28): SECURITY_AUDIT.md — audyt bezpieczeństwa, find_private_paths(), git_paths(), main(), normalize_path(), privacy_reason(), PrivacyPathMatchingTests, test_debug_prints_traceback() (+20 more)

### Community 2 - "Testy rdzenia CLI trainer"
Cohesion: 0.07
Nodes (12): extract(), TestFindPlan, TestHrvAlert, TestPaceStr, TestParseTimedelta, TestReadinessScore, TestExtract, check_hrv_alert() (+4 more)

### Community 3 - "Obsługa błędów i importów"
Cohesion: 0.08
Nodes (28): test_env_hint_matches_current_platform(), test_garmin_auth_error_is_not_reported_as_unexpected(), test_json_error_and_secret_are_safe(), test_missing_dependency_has_stable_advice(), test_missing_dependency_includes_venv_hint_when_outside_venv(), test_profile_and_database_errors_are_classified(), _ready_environment(), Status (+20 more)

### Community 4 - "Silnik oceny gotowości"
Cohesion: 0.08
Nodes (11): compare_plan_vs_actual(), compute_readiness_breakdown(), get_today_workout(), readiness_for_day(), signal_trends(), _make_data(), TestComparePlanVsActual, TestGetTodayWorkout (+3 more)

### Community 5 - "Zależności dev i narzędzia"
Cohesion: 0.06
Nodes (22): lifespan(), requirements-dev.txt — zależności developerskie, Zależności dev (pytest, httpx, Pillow), collect_targets(), frame_size(), main(), png_size(), render() (+14 more)

### Community 6 - "Logowanie do Garmina i testy"
Cohesion: 0.07
Nodes (17): test_ensure_garmindb_config_creates_neutral_credentials(), test_ensure_garmindb_config_never_overwrites(), test_ensure_token_falls_back_from_invalid_token(), test_ensure_token_requires_password(), test_ensure_token_uses_existing_token(), test_expired_token_without_password_requests_interactive_login(), test_login_failure_does_not_repeat_strategy_chain(), test_mfa_passed_to_constructor_not_login() (+9 more)

### Community 7 - "Test połączenia z AI"
Cohesion: 0.07
Nodes (27): AIConnectionTestError, check_connection(), linux_setup.md — instrukcja Linux, Automatyzacja codziennego sync (cron / systemd timer), Instalacja i konfiguracja na Linuxie (venv, requirements, local/profile.json), Migracja HealthData z nośnika (export_healthdata.ps1 → migrate_healthdata.sh), MOBILE_APP_PROPOSAL.md — propozycja aplikacji mobilnej, Opcja B: Flutter + FastAPI backend (rekomendacja) (+19 more)

### Community 8 - "Komentarz trenera AI do treningu"
Cohesion: 0.08
Nodes (21): build_comment_message(), get_workout_comment(), _value(), _with_unit(), WorkoutComment, _block_network(), blocked(), _isolate_garmin_tokens() (+13 more)

### Community 9 - "Raport tygodnia"
Cohesion: 0.08
Nodes (22): week_bounds(), _availability(), build_week_report(), DayAvailability, get_week_report(), _sport(), _valid_date(), WeekActivity (+14 more)

### Community 10 - "Ekstrakcja danych GarminDB"
Cohesion: 0.09
Nodes (12): download_today(), _find_garmindb_cli(), _find_python(), _garmindb_log_dir(), GarminDBSyncError, SnapshotStatus, sync(), sync_full() (+4 more)

### Community 11 - "Punktacja wykonania treningu"
Cohesion: 0.11
Nodes (26): _workout_section(), _workout_status(), _execution_zone(), planned_duration_min(), score_execution(), zone_band(), score(), test_below_warmup_tolerance_loses_one_point() (+18 more)

### Community 12 - "Testy endpointów API"
Cohesion: 0.16
Nodes (30): _analysis_client(), _analysis_readiness(), _client(), _readiness(), _report(), test_analysis_escapes_metric_message(), test_analysis_maps_unknown_status_to_neutral_pill(), test_analysis_marks_navigation_entry_as_current() (+22 more)

### Community 13 - "System wizualny i granice UI"
Cohesion: 0.10
Nodes (27): UI_STYLE.md — system wizualny, System wizualny: jasny motyw slate + akcent #2563EB, _base.html — szkielet aplikacji (sidebar + nawigacja), Obrazy z lokalnego pakietu serwowane z /assets/ (zawsze dekoracyjne), Nawigacja sidebar (Dziś, Kalendarz, Analiza, Ustawienia; Plan/Statystyki/Sprzęt wyłączone), _icons.html — makra Jinja ikon SVG (home, runner, check, refresh…), _styles.html — jedyne źródło stylu (tokeny CSS w :root), Tokeny CSS w :root z policzonymi kontrastami w komentarzach (+19 more)

### Community 14 - "Testy spójności grafik"
Cohesion: 0.11
Nodes (13): display_sizes(), png_size(), signal_asset_size(), signal_references(), static_references(), template_files(), test_asset_tags_are_marked_as_decorative(), test_declared_proportions_match_files() (+5 more)

### Community 15 - "Endpointy health i readiness"
Cohesion: 0.09
Nodes (12): health(), readiness(), HealthResponse, _hr_zone_rows(), _job_timestamp(), _profile_rows(), _raise_report_error(), ReadinessDetail (+4 more)

### Community 16 - "Testy raportu tygodniowego"
Cohesion: 0.25
Nodes (20): _activity(), _day(), _entry(), _report(), test_activity_without_plan_is_activity_only(), test_bad_or_stale_snapshot_keeps_plan_visible(), test_confirmed_schedule_remains_a_planned_week_workout(), test_duplicate_workout_id_does_not_break_report_and_default_availability_is_unconfigured() (+12 more)

### Community 17 - "Zapis ustawień AI"
Cohesion: 0.18
Nodes (13): save(), test_atomic_failure_preserves_old_file_and_cleans_temporary(), test_different_provider_never_receives_saved_key(), test_invalid_settings_never_modify_file(), test_key_roundtrip_clear_and_restart_loading(), test_preserves_other_entries_comments_and_blank_key(), test_provider_change_requires_explicit_key_decision(), test_same_provider_reuses_and_preserves_key_after_path_change() (+5 more)

### Community 18 - "Testy akcji i CSRF"
Cohesion: 0.14
Nodes (20): _action_app(), _csrf(), _review_app(), test_ai_connection_failure_preserves_nonsecret_form(), fail(), test_dashboard_quiet_state_has_no_banner_or_refresh(), test_double_submission_reuses_one_job_and_one_execution(), test_executor_is_shutdown_with_application() (+12 more)

### Community 20 - "Abstrakcja dostawcy AI"
Cohesion: 0.14
Nodes (6): AIProvider, AIProviderError, AIResponseError, requirements.txt — zależności runtime, Zależności runtime (garmindb, garminconnect, pydantic, openai, fastapi, uvicorn, jinja2, python-multipart), TestAIProviderABC

### Community 21 - "Testy widoku dziś"
Cohesion: 0.15
Nodes (13): SnapshotReadResult, _ClockAt20261002, _run_today(), test_deleted_registry_workout_is_not_shown(), test_missing_snapshot_is_friendly(), test_newest_active_registry_workout_is_shown_for_same_date(), test_single_activity_stays_on_one_line(), test_stale_snapshot_warns() (+5 more)

### Community 22 - "Trasy FastAPI i CSRF"
Cohesion: 0.16
Nodes (18): create_app(), ai_settings(), ai_settings_page(), asset(), attach_csrf(), csrf_token(), csrf_valid(), dashboard() (+10 more)

### Community 23 - "Logowanie i konfiguracja analizy"
Cohesion: 0.12
Nodes (6): main(), print_health_data(), print_hrv_alert(), print_plan_comparison(), print_readiness(), print_weekly_activities()

### Community 24 - "Kontekst treningowy dla AI"
Cohesion: 0.16
Nodes (8): build_training_context(), format_context_for_user(), _get_health_snapshot(), _goal_from_profile(), _load_important_prompt(), _make_sample_data(), TestFormatContextForUser, TestGetHealthSnapshot

### Community 25 - "Podział odpowiedzialności projektu"
Cohesion: 0.13
Nodes (15): PROMPT_TECHNICAL.md — prompt techniczny, GarminDB — backend danych lokalnych, Prywatny stan runtime local/ (profile.json, data_latest.json, workout-registry.jsonl, memory/), PROMPT_TRAINING.md — prompt trenera AI, Schemat JSON rekomendacji dziennej, TRAINING_RULES.md — zasady tworzenia treningów, Strategia i pliki planów treningowych, IMPORTANT_PROMPT.txt — zasady trenera (+7 more)

### Community 26 - "Dopasowanie aktywności do planu"
Cohesion: 0.23
Nodes (14): assign_activities(), find_activity_for_workout(), match_activity_for_workout(), _activity(), test_assignments_do_not_reuse_one_activity_for_two_workouts(), test_ignores_activity_from_another_date(), test_ignores_non_running_activity(), test_matches_explicit_activity_id() (+6 more)

### Community 27 - "Rejestr operacji na Garminie"
Cohesion: 0.12
Nodes (7): _append(), record_added(), record_deleted(), record_updated(), _iso_date(), legacy_main(), _positive_int()

### Community 28 - "Bezpieczne serwowanie assetów"
Cohesion: 0.25
Nodes (11): build_manifest(), resolve_asset(), create_file(), test_manifest_collects_only_allowed_categories(), test_manifest_returns_empty_for_missing_root(), test_manifest_skips_non_png_files(), test_resolve_asset_rejects_file_outside_manifest(), test_resolve_asset_rejects_invalid_references() (+3 more)

### Community 29 - "Kreator treningu i pytania"
Cohesion: 0.16
Nodes (11): _answers(), _redirect_stores(), test_minutes_range(), test_weekly_proposal_approval_avoids_daily_questions(), test_weekly_proposal_rejection_asks_daily_questions(), test_wizard_happy_path_writes_files_without_echoing_secrets(), test_wizard_retries_password_then_allows_manual_mode(), rejected() (+3 more)

### Community 30 - "Preferencje dostępności"
Cohesion: 0.19
Nodes (10): test_legacy_days_and_unknown_fields_are_preserved(), test_missing_preferences_return_safe_defaults(), test_set_weekly_availability_writes_one_day(), test_weekly_rejection_asks_minutes_once_per_available_day(), _default_preferences(), load_preferences(), _normalize(), _preferences_path() (+2 more)

### Community 31 - "Cele i cel tygodniowy"
Cohesion: 0.18
Nodes (13): test_target_goal_half_marathon_time(), test_target_goal_no_race_skips_time(), test_target_goal_other_and_invalid_choice_reprompts(), test_weekly_proposal_uses_garmin_days_and_long_range(), _ask(), _choice(), _integer(), main() (+5 more)

### Community 32 - "Raport dzisiejszy i testy"
Cohesion: 0.26
Nodes (16): build_today_report(), _snapshot(), test_build_today_report_has_expected_status(), test_build_today_report_includes_trends_for_report_date(), test_build_today_report_keeps_snapshot_timestamp(), test_build_today_report_sorts_yesterday_and_uses_requested_weekday(), test_build_today_report_suggestion_rule(), test_build_today_report_uses_none_for_missing_signals_and_keeps_stale_data() (+8 more)

### Community 33 - "Czas snapshotu i zadania sync"
Cohesion: 0.12
Nodes (13): _format_sync_time(), _sync_job(), test_ai_connection_rejects_unsafe_requests_without_calling_provider(), test_ai_connection_uses_form_and_never_saves(), test_ai_settings_rejects_csrf(), test_dashboard_hides_old_failed_sync_banner(), test_dashboard_respects_utc_job_age_with_naive_local_clock(), test_dashboard_shows_cooldown_from_recent_success() (+5 more)

### Community 34 - "Kreator konfiguracji profilu"
Cohesion: 0.15
Nodes (11): _disable_terminal_getpass(), test_ask_secret_preserves_whitespace(), test_ask_secret_uses_getpass_not_input(), test_load_env_excludes_legacy_password(), test_write_env_quoting_matrix_round_trips(), test_write_env_rejects_newline(), test_write_env_removes_all_legacy_garmin_passwords(), test_write_env_round_trips_special_values() (+3 more)

### Community 35 - "Rekomendacja dzienna AI"
Cohesion: 0.18
Nodes (5): DailyRecommendation, get_daily_recommendation(), TestBuildContext, TestDailyRecommendation, TestGetDailyRecommendation

### Community 37 - "Zmienne środowiskowe i .env"
Cohesion: 0.20
Nodes (4): Konfiguracja .env (HEALTH_DATA_DIR, AI_*, GARMIN_EMAIL, SNAPSHOT_TTL_SECONDS), Formularz API AI (AI_BASE_URL, AI_MODEL, AI_API_KEY, zgoda na eksport), AppSettings, _positive_int_env()

### Community 38 - "Serwis widoku dziś"
Cohesion: 0.15
Nodes (8): _execution(), get_today_report(), _today_registry_entries(), TodayReport, test_confirmed_schedule_remains_a_planned_today_workout(), _activity_line(), main(), get_weekly_availability()

### Community 39 - "Testy komendy profile"
Cohesion: 0.18
Nodes (11): test_missing_profile_points_to_setup(), test_render_flags_range_values_and_suggests_sync(), test_render_is_human_readable_not_a_dict_dump(), test_render_keeps_legacy_goal_field_when_structured_missing(), test_render_lists_unknown_fields(), test_render_shows_structured_goal_and_hides_composed_field(), test_sync_maps_garmin_keys_and_skips_preference_fields(), test_sync_reports_error_on_empty_snapshot() (+3 more)

### Community 40 - "Widoki analizy i tygodnia w API"
Cohesion: 0.12
Nodes (9): _analysis_measurements(), _analysis_rows(), analysis(), week(), _format_date(), _format_minutes(), _format_score(), _readiness_chart() (+1 more)

### Community 41 - "Magazyn profilu biegacza"
Cohesion: 0.16
Nodes (6): test_load_profile_missing_has_polish_message(), test_set_hr_zones_preserves_unknown_and_required_fields(), test_update_profile_merges_fields(), save_profile(), set_hr_zones(), update_profile()

### Community 42 - "Blokady międzyprocesowe"
Cohesion: 0.13
Nodes (5): _acquire(), _lock_path(), LockBusyError, _release(), busy()

### Community 43 - "Testy ustawień AI"
Cohesion: 0.14
Nodes (13): _profile(), _settings_client(), test_ai_settings_available_without_profile_and_invalid_input_is_safe(), missing(), test_dashboard_workout_section_skips_score_without_profile(), test_settings_escapes_profile_values(), test_settings_falls_back_to_zone_floors_when_summary_missing(), test_settings_marks_navigation_entry_as_current() (+5 more)

### Community 44 - "Magazyn ocen treningów"
Cohesion: 0.31
Nodes (7): load_review(), save_review(), test_load_review_returns_latest_entry_for_key(), test_load_review_returns_none_for_missing_file_or_unknown_key(), test_load_review_skips_malformed_line(), test_save_and_load_review_with_polish_comment(), test_save_review_does_not_silence_write_errors()

### Community 45 - "Blokada plikowa i testy"
Cohesion: 0.29
Nodes (7): acquire_lock(), _lock_in(), lock(), test_busy_lock_returns_clean_message_and_nonzero_code(), test_operation_exception_releases_lock(), test_success_runs_operation_once_and_releases_lock(), main()

### Community 46 - "Uruchamianie oceny treningu"
Cohesion: 0.19
Nodes (8): run_review(), execute(), run_review_job(), _Store, test_run_review_job_hides_technical_error(), test_run_review_job_marks_success(), test_run_review_job_records_busy_message(), test_run_review_job_records_value_error()

### Community 47 - "Plan treningowy CSV"
Cohesion: 0.22
Nodes (4): plan_csv_rows(), plan_path(), write_plan_csv(), TestPlanPath

### Community 48 - "Akcje HTTP serwisu"
Cohesion: 0.37
Nodes (10): review_workout(), _enable_ai(), _profile(), _report(), test_review_workout_rejects_disabled_ai_export(), test_review_workout_rejects_missing_ai_key(), test_review_workout_rejects_missing_execution(), test_review_workout_rejects_stale_review_key() (+2 more)

### Community 49 - "Odczyt planu na dziś"
Cohesion: 0.22
Nodes (4): find_current_plan(), get_today_workout_from_plan(), TestFindCurrentPlan, TestGetTodayWorkoutFromPlan

### Community 50 - "Testy rejestru treningów"
Cohesion: 0.15
Nodes (3): isolated_registry(), TestRestore, TestState

### Community 56 - "Wykonawcy operacji mutujących"
Cohesion: 0.20
Nodes (4): synchronize_data(), synchronize_and_save(), test_synchronize_data_delegates_to_shared_operation(), load_profile()

### Community 57 - "Snapshot danych data_latest"
Cohesion: 0.25
Nodes (3): load_data_latest(), save_json(), TestSaveLoadJson

### Community 59 - "Nazwa pliku planu tygodnia"
Cohesion: 0.22
Nodes (4): plan_filename(), TestWeekBounds, plan_filename(), week_bounds()

### Community 63 - "Testy stref tętna"
Cohesion: 0.25
Nodes (5): test_local_zones_warn_when_source_missing(), test_sync_empty_response_is_error(), test_sync_uses_mocked_garmin_and_saves_zones(), main(), _print_zones()

### Community 64 - "Pobranie profilu z Garmina"
Cohesion: 0.24
Nodes (4): _render(), _bounded(), _call(), fetch_snapshot()

### Community 65 - "Wyszukiwanie pliku planu"
Cohesion: 0.31
Nodes (4): _candidate_dirs(), find_plan_file(), TestFindPlanFile, write_plan()

### Community 66 - "Testy widoku tygodnia"
Cohesion: 0.38
Nodes (10): WeekWorkout, test_week_hides_registry_problem_warning_when_registry_is_ok(), test_week_renders_all_day_status_labels(), test_week_renders_seven_days_and_no_store(), test_week_shows_all_workouts_and_activities_and_escapes_names(), test_week_shows_registry_problem_warning(), test_week_shows_unconfigured_availability_ambiguous_message_and_links(), test_week_snapshot_states_are_not_errors() (+2 more)

### Community 70 - "Sekcja treningu na dashboardzie"
Cohesion: 0.36
Nodes (9): _execution(), test_dashboard_workout_section_escapes_saved_comment(), test_dashboard_workout_section_offers_review_when_comment_is_missing(), test_dashboard_workout_section_reports_execution_and_local_score(), test_dashboard_workout_section_reports_missing_execution(), test_dashboard_workout_section_shows_saved_comment_without_button(), test_dashboard_workout_section_warns_about_heuristic_match(), test_dashboard_workout_section_without_plan_is_empty() (+1 more)

### Community 71 - "Testy pobierania profilu"
Cohesion: 0.25
Nodes (4): test_fetch_snapshot_falls_back_to_resting_when_average_missing(), test_parse_hr_zones_list_and_dict(), test_parse_hr_zones_prefers_running_and_rejects_bad_data(), parse_hr_zones()

### Community 72 - "Walidacja profilu dla AI"
Cohesion: 0.36
Nodes (3): _load_runner_profile(), _validate_runner_profile(), TestRunnerProfileLoading

### Community 73 - "Testy blokady plikowej"
Cohesion: 0.43
Nodes (6): test_different_lock_names_do_not_collide(), test_exception_inside_context_releases_lock(), test_killing_holder_releases_system_lock(), test_other_process_acquires_after_lock_is_released(), test_other_process_cannot_acquire_held_lock(), _try_lock()

### Community 86 - "Wczytywanie pliku .env"
Cohesion: 0.53
Nodes (4): test_existing_environment_wins_unless_overridden(), test_load_env_file_parses_supported_syntax(), test_missing_file_is_silent(), load_env_file()

## Ambiguous Edges - Review These
- `Granice nienaruszalne UI (zero JS, zero zasobów z sieci, brak StaticFiles, nigdy |safe)` → `settings_ai.html — formularz API AI`  [AMBIGUOUS]
  templates/settings_ai.html · relation: conceptually_related_to

## Knowledge Gaps
- **8 isolated node(s):** `IMPORTANT_PROMPT.txt — zasady trenera`, `requirements.txt — zależności runtime`, `requirements-dev.txt — zależności developerskie`, `MVP w 5 fazach (backend API → dashboard → AI → chat/push → polish)`, `Assety v2 (readiness/, branding/, arkusze źródłowe)` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 569 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GarminWorkout` connect `Budowniki treningów Garmin` to `Pobranie profilu z Garmina`, `Audyt bezpieczeństwa i prywatności`, `Zależności dev i narzędzia`, `Testy komendy profile`, `Ekstrakcja danych GarminDB`, `Konwersja tempa i kompatybilność`, `Inicjalizacja klienta Garmin`, `Izolowany rejestr w testach`, `Spójność rejestru i harmonogramu`, `Zasada strefy 2 w treningach`, `Wgrywanie definicji treningu`, `Rejestr operacji na Garminie`, `Logowanie przez tokeny`, `Testy stref tętna`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `create_app()` (e.g. with `AIConnectionTestError` and `lifespan()`) actually correct?**
  _`create_app()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `IMPORTANT_PROMPT.txt — zasady trenera`, `requirements.txt — zależności runtime`, `requirements-dev.txt — zależności developerskie` to the rest of the system?**
  _8 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Wydane zadania synchronizacji` be split into smaller, more focused modules?**
  _Cohesion score 0.07330618289522399 - nodes in this community are weakly interconnected._
- **Why does `create_app()` connect `Trasy FastAPI i CSRF` to `Wydane zadania synchronizacji`, `Zależności dev i narzędzia`, `Test połączenia z AI`, `Raport tygodnia`, `Ekstrakcja danych GarminDB`, `Testy endpointów API`, `Endpointy health i readiness`, `Zapis ustawień AI`, `Testy akcji i CSRF`, `Bezpieczne serwowanie assetów`, `Czas snapshotu i zadania sync`, `Serwis widoku dziś`, `Widoki analizy i tygodnia w API`, `Blokady międzyprocesowe`, `Testy ustawień AI`, `Blokada plikowa i testy`, `Uruchamianie oceny treningu`, `Akcje HTTP serwisu`, `Testy widoku tygodnia`, `Sekcja treningu na dashboardzie`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `JobStore` (e.g. with `_sync_banner()` and `run_sync_job()`) actually correct?**
  _`JobStore` has 6 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Granice nienaruszalne UI (zero JS, zero zasobów z sieci, brak StaticFiles, nigdy |safe)` and `settings_ai.html — formularz API AI`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._