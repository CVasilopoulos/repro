import time

from app.store import Store


def test_lab_runs_and_issue_runs_are_rate_limited_separately(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    for _ in range(3):
        store.create_job("lab:wipe", "1.2.3.4")
    store.create_job("https://github.com/o/r/issues/1", "1.2.3.4")
    since = time.time() - 60
    assert store.jobs_from_client_since("1.2.3.4", since) == 1
    assert store.jobs_from_client_since("1.2.3.4", since, lab=True) == 3
    assert store.jobs_from_client_since("5.6.7.8", since) == 0


def test_events_are_numbered_in_order_and_filtered_by_sequence(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    job = store.create_job("https://github.com/o/r/issues/1", "x")
    store.emit(job, "status", message="a")
    store.emit(job, "status", message="b")
    store.emit(job, "done", seconds=1)
    assert [e["seq"] for e in store.events(job)] == [1, 2, 3]
    assert [e["data"].get("message") for e in store.events(job, after=1)] == ["b", None]


def test_daily_token_usage_accumulates(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    store.add_tokens(100)
    assert store.add_tokens(50) == 150
    assert store.tokens_today() == 150
