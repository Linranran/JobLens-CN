from joblens.importers import import_records
from joblens.matching import score_database
from joblens.reports import build_report


def test_report_groups_company_and_job(tmp_path):
    database = tmp_path / "jobs.db"
    records = [
        {
            "source": "test",
            "external_id": "1",
            "title": "AI Engineer",
            "description": "Python",
            "skills": ["Python"],
            "directions": [],
            "source_url": "https://example.com/1",
            "status": "active",
            "first_seen": "",
            "last_seen": "",
            "company": {"name": "Example Co", "introduction": "Synthetic company."},
        }
    ]
    import_records(database, records)
    score_database(
        database,
        {
            "skills": ["Python"],
            "target_titles": ["AI Engineer"],
            "target_directions": [],
            "preferred_locations": [],
            "excluded_terms": [],
        },
    )
    output = build_report(database, tmp_path / "report.md")
    text = output.read_text(encoding="utf-8")
    assert "Example Co" in text
    assert "AI Engineer" in text
    assert "Synthetic company." in text
