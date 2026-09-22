import json

from joblens.db import connect
from joblens.importers import import_file


def write_jobs(path, description="Python and OCR", company_name="Example Co"):
    path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "source": "test",
                        "external_id": "1",
                        "company_name": company_name,
                        "title": "OCR Engineer",
                        "description": description,
                        "source_url": "https://example.com/1",
                        "security_id": "must-not-be-persisted",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_import_is_idempotent_and_tracks_changes(tmp_path):
    source = tmp_path / "jobs.json"
    database = tmp_path / "jobs.db"
    write_jobs(source)
    first = import_file(database, source)
    second = import_file(database, source)
    assert first == {"imported": 1, "changed": 1, "unchanged": 0}
    assert second == {"imported": 1, "changed": 0, "unchanged": 1}

    write_jobs(source, "Python, OCR and VLM")
    third = import_file(database, source)
    assert third["changed"] == 1
    with connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM job_versions").fetchone()[0] == 2
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        assert "security_id" not in columns


def test_company_relationship_moves_without_leaving_a_stale_link(tmp_path):
    source = tmp_path / "jobs.json"
    database = tmp_path / "jobs.db"
    write_jobs(source)
    import_file(database, source)

    write_jobs(source, company_name="Corrected Company")
    import_file(database, source)

    with connect(database) as connection:
        relationships = connection.execute("SELECT company_id, job_id FROM company_jobs").fetchall()
        current_company = connection.execute("SELECT company_id FROM jobs").fetchone()[0]
        assert len(relationships) == 1
        assert relationships[0][0] == current_company
