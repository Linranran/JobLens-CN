"""Source-agnostic JSON/CSV importers with a strict public field whitelist."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from .db import connect, initialize, upsert_company, upsert_job


def _items(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [item.strip() for item in str(value).replace("|", ",").split(",") if item.strip()]


def normalize_record(raw: dict) -> dict:
    """Map common source fields into JobLens' safe canonical schema."""
    company_name = (
        raw.get("company_name") or raw.get("company") or raw.get("boss_name") or "Unknown company"
    )
    description = raw.get("description") or raw.get("jd") or raw.get("job_description") or ""
    source_url = raw.get("source_url") or raw.get("job_link") or raw.get("link") or ""
    requirements = str(raw.get("requirements") or raw.get("tags") or raw.get("job_labels") or "")
    experience = raw.get("experience") or ""
    education = raw.get("education") or ""
    if requirements and not experience and "|" in requirements:
        parts = [item.strip() for item in requirements.split("|")]
        experience = parts[0] if parts else ""
        education = parts[1] if len(parts) > 1 else ""
    return {
        "source": str(raw.get("source") or "manual"),
        "external_id": str(raw.get("external_id") or ""),
        "job_id": str(raw.get("job_id") or ""),
        "title": str(raw.get("title") or raw.get("job_title") or "Untitled role"),
        "salary": str(raw.get("salary") or ""),
        "location": str(raw.get("location") or ""),
        "experience": str(experience),
        "education": str(education),
        "employment_type": str(raw.get("employment_type") or ""),
        "skills": _items(raw.get("skills") or raw.get("skill_tags")),
        "directions": _items(raw.get("directions")),
        "description": str(description),
        "source_url": str(source_url),
        "status": str(raw.get("status") or "active"),
        "first_seen": str(raw.get("first_seen") or ""),
        "last_seen": str(raw.get("last_seen") or ""),
        "company": {
            "company_id": str(raw.get("company_id") or ""),
            "name": str(company_name),
            "industry": str(raw.get("industry") or raw.get("company_industry") or ""),
            "size": str(raw.get("company_size") or raw.get("size") or ""),
            "stage": str(raw.get("company_stage") or raw.get("stage") or ""),
            "introduction": str(raw.get("company_introduction") or raw.get("introduction") or ""),
            "website": str(raw.get("company_website") or raw.get("website") or ""),
            "source_url": str(raw.get("company_source_url") or raw.get("company_link") or ""),
        },
    }


def load_records(path: str | Path) -> list[dict]:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as handle:
            return [normalize_record(row) for row in csv.DictReader(handle)]
    data = json.loads(source.read_text(encoding="utf-8"))
    raw_records = data.get("jobs", []) if isinstance(data, dict) else data
    if not isinstance(raw_records, list):
        raise ValueError("JSON input must be a list or an object containing a 'jobs' list")
    return [normalize_record(item) for item in raw_records]


def import_records(db_path: str | Path, records: Iterable[dict]) -> dict:
    initialize(db_path)
    imported = changed = 0
    with connect(db_path) as connection:
        for record in records:
            company_id = upsert_company(connection, record["company"])
            _, was_changed = upsert_job(connection, record, company_id)
            imported += 1
            changed += int(was_changed)
    return {"imported": imported, "changed": changed, "unchanged": imported - changed}


def import_file(db_path: str | Path, input_path: str | Path) -> dict:
    return import_records(db_path, load_records(input_path))
