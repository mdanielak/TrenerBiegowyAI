import unittest

from scripts.check_privacy import find_private_paths, privacy_reason


class PrivacyPathMatchingTests(unittest.TestCase):
    def test_detects_private_paths_and_artifacts(self):
        cases = {
            "local/profile.json": "private local/ runtime data",
            "local/memory/note.md": "private local/ runtime data",
            ".env.production": "environment file",
            "HealthData/metrics.json": "Garmin private data",
            "archive/activity.fit": "database or activity export",
            "secrets/deploy.pem": "private key or certificate",
            "auth/session_cookie.json": "token or cookie artifact",
            "training-plans/_garmin_workouts.jsonl": "Garmin workout registry",
            "data_latest.json": "legacy private runtime data",
            "memory/history.json": "agent memory",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(privacy_reason(path), expected)

    def test_allows_public_examples_plans_and_source_names(self):
        for path in (
            ".env.example",
            "runner_profile.example.json",
            "training-plans/long-term/half-marathon-2027.md",
            "services/tokenizer.py",
            "src/key_mapping.py",
            "docs/cookie-policy.md",
        ):
            with self.subTest(path=path):
                self.assertIsNone(privacy_reason(path))

    def test_finds_and_sorts_only_private_paths(self):
        findings = find_private_paths(["src/key_mapping.py", "b/activity.gpx", "local/profile.json"])
        self.assertEqual([path for path, _ in findings], ["b/activity.gpx", "local/profile.json"])


if __name__ == "__main__":
    unittest.main()
