from joblens.dashboard_app import selected_job_id_from_rows


def test_selected_job_id_from_rows():
    rows = [{"job_id": "job-a"}, {"job_id": "job-b"}]

    assert selected_job_id_from_rows(rows, [1]) == "job-b"
    assert selected_job_id_from_rows(rows, []) is None
    assert selected_job_id_from_rows(rows, [9]) is None
