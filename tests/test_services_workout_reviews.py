import json

import pytest

from services.workout_reviews import load_review, save_review


def test_save_and_load_review_with_polish_comment(tmp_path):
    path = tmp_path / "reviews.jsonl"
    save_review(review_key="2026-10-02:7", score={"overall": 5}, comment="Świetny bieg, żółw!", path=path)
    review = load_review(review_key="2026-10-02:7", path=path)
    assert review["score"] == {"overall": 5}
    assert review["comment"] == "Świetny bieg, żółw!"
    assert "+00:00" in review["created_at"]


def test_load_review_returns_latest_entry_for_key(tmp_path):
    path = tmp_path / "reviews.jsonl"
    save_review(review_key="key", score={"overall": 2}, comment="stara", path=path)
    save_review(review_key="key", score={"overall": 5}, comment="nowa", path=path)
    assert load_review(review_key="key", path=path)["comment"] == "nowa"


def test_load_review_returns_none_for_missing_file_or_unknown_key(tmp_path):
    path = tmp_path / "reviews.jsonl"
    assert load_review(review_key="key", path=path) is None
    save_review(review_key="known", score={}, comment="ok", path=path)
    assert load_review(review_key="unknown", path=path) is None


def test_load_review_skips_malformed_line(tmp_path, caplog):
    path = tmp_path / "reviews.jsonl"
    path.write_text(
        json.dumps({"review_key": "key", "score": {"overall": 1}, "comment": "stara"})
        + "\n{nie json}\n"
        + json.dumps({"review_key": "key", "score": {"overall": 4}, "comment": "nowa"}) + "\n",
        encoding="utf-8",
    )
    assert load_review(review_key="key", path=path)["comment"] == "nowa"
    assert "uszkodzonej linii" in caplog.text


def test_save_review_does_not_silence_write_errors(tmp_path):
    directory_path = tmp_path / "directory"
    directory_path.mkdir()
    with pytest.raises(OSError):
        save_review(review_key="key", score={}, comment="nie zapisze", path=directory_path)
