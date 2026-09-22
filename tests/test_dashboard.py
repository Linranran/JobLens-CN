from joblens.dashboard_app import selected_job_id_from_cells


def test_selected_job_id_from_cells():
    rows = [{"job_id": "job-a"}, {"job_id": "job-b"}]

    assert selected_job_id_from_cells(rows, [(1, "company")]) == "job-b"
    assert selected_job_id_from_cells(rows, [(1, "title")]) == "job-b"
    assert selected_job_id_from_cells(rows, []) is None
    assert selected_job_id_from_cells(rows, [(9, "salary")]) is None
