from datetime import datetime, timezone

from joblens.dashboard_app import freshness_status, selected_job_id_from_cells


def test_selected_job_id_from_cells():
    rows = [{"job_id": "job-a"}, {"job_id": "job-b"}]

    assert selected_job_id_from_cells(rows, [(1, "company")]) == "job-b"
    assert selected_job_id_from_cells(rows, [(1, "title")]) == "job-b"
    assert selected_job_id_from_cells(rows, []) is None
    assert selected_job_id_from_cells(rows, [(9, "salary")]) is None


def test_freshness_status_does_not_mark_missing_results_as_closed():
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)

    assert freshness_status("2026-09-20T12:00:00+00:00", now) == "recent"
    assert freshness_status("2026-09-10T12:00:00+00:00", now) == "possibly_stale"
    assert freshness_status("2026-07-01T12:00:00+00:00", now) == "stale"
    assert freshness_status("", now) == "unknown"
