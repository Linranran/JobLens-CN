import json

from joblens.db import connect
from joblens.importers import import_bundle, load_bundle


def write_bundle(list_path, details_path):
    list_path.write_text(
        json.dumps(
            {
                "keyword": "OCR",
                "city": "北京",
                "filters": {"experience": "3-5年"},
                "scraped_at": "2026-09-22T12:00:00+08:00",
                "jobs": [
                    {
                        "job_id": "source-job-1",
                        "title": "OCR算法工程师",
                        "salary": "30-50K",
                        "location": "北京·海淀区",
                        "tags": "3-5年 | 本科",
                        "boss_name": "示例科技",
                        "boss_title": "招聘经理",
                        "boss_active_status": "在线",
                        "company_scale": "100-499人",
                        "company_stage": "B轮",
                        "company_industry": "人工智能",
                        "skills": "Python | OCR",
                        "job_link": (
                            "https://example.com/jobs/1?securityId=secret&from=search&lid=private"
                        ),
                        "company_link": "https://example.com/company/1?lid=private",
                        "security_id": "secret",
                        "lid": "private",
                        "encrypt_boss_id": "person-id",
                    },
                    {
                        "job_id": "source-job-2",
                        "title": "视觉算法工程师",
                        "boss_name": "第二家公司",
                        "job_link": "https://example.com/jobs/2",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    details_path.write_text(
        json.dumps(
            [
                {
                    "job_id": "source-job-1",
                    "title": "OCR算法工程师",
                    "company": "示例科技",
                    "job_link": "https://example.com/jobs/1",
                    "skill_tags": ["PyTorch", "DBNet"],
                    "jd": "负责OCR检测识别与模型部署。",
                    "boss_active_status": "刚刚活跃",
                },
                {
                    "job_id": "source-job-3",
                    "title": "多模态算法工程师",
                    "company": "第三家公司",
                    "job_link": "https://example.com/jobs/3",
                    "tags_list": "1-3年 | 硕士",
                    "jd": "负责VLM训练与评测。",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_load_bundle_merges_and_sanitizes(tmp_path):
    list_path = tmp_path / "jobs.json"
    details_path = tmp_path / "details.json"
    write_bundle(list_path, details_path)

    records, diagnostics = load_bundle(list_path, details_path, source_name="offline-source")

    assert diagnostics["list_count"] == 2
    assert diagnostics["detail_count"] == 2
    assert diagnostics["matched_details"] == 1
    assert diagnostics["missing_details"] == 1
    assert diagnostics["details_only"] == 1
    assert diagnostics["canonical_count"] == 3
    assert diagnostics["discarded_sensitive_fields"]["security_id"] == 1

    merged = next(record for record in records if record["external_id"] == "source-job-1")
    assert merged["job_id"] == ""
    assert merged["description"] == "负责OCR检测识别与模型部署。"
    assert merged["experience"] == "3-5年"
    assert merged["education"] == "本科"
    assert merged["skills"] == ["Python", "OCR", "PyTorch", "DBNet"]
    assert merged["source_url"] == "https://example.com/jobs/1?from=search"
    assert merged["company"]["source_url"] == "https://example.com/company/1"
    assert merged["company"]["size"] == "100-499人"


def test_bundle_dry_run_and_idempotent_import(tmp_path):
    list_path = tmp_path / "jobs.json"
    details_path = tmp_path / "details.json"
    database = tmp_path / "jobs.db"
    write_bundle(list_path, details_path)

    preview = import_bundle(
        database,
        list_path,
        details_path,
        source_name="offline-source",
        dry_run=True,
    )
    assert preview["dry_run"] is True
    assert not database.exists()

    first = import_bundle(database, list_path, details_path, source_name="offline-source")
    second = import_bundle(database, list_path, details_path, source_name="offline-source")
    assert first["new"] == 3
    assert first["updated"] == 0
    assert second["new"] == 0
    assert second["unchanged"] == 3

    with connect(database) as connection:
        job = connection.execute("SELECT * FROM jobs WHERE external_id = 'source-job-1'").fetchone()
        assert job["job_id"].startswith("job_")
        assert job["job_id"] != "source-job-1"
        assert job["source"] == "offline-source"
        assert job["description"] == "负责OCR检测识别与模型部署。"
        assert job["last_seen"] == "2026-09-22T12:00:00+08:00"
        assert connection.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM job_versions").fetchone()[0] == 3
