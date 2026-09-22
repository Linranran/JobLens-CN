"""SQLite persistence and version tracking."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    company_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    industry TEXT NOT NULL DEFAULT '',
    company_size TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT '',
    introduction TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'manual',
    external_id TEXT NOT NULL DEFAULT '',
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    title TEXT NOT NULL,
    salary TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    experience TEXT NOT NULL DEFAULT '',
    education TEXT NOT NULL DEFAULT '',
    employment_type TEXT NOT NULL DEFAULT '',
    skills_json TEXT NOT NULL DEFAULT '[]',
    directions_json TEXT NOT NULL DEFAULT '[]',
    description TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    match_score REAL,
    recommendation TEXT NOT NULL DEFAULT '',
    matched_skills_json TEXT NOT NULL DEFAULT '[]',
    missing_skills_json TEXT NOT NULL DEFAULT '[]',
    match_explanation TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS company_jobs (
    company_id TEXT NOT NULL REFERENCES companies(company_id),
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    PRIMARY KEY (company_id, job_id)
);

CREATE TABLE IF NOT EXISTS job_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    version INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    salary TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    UNIQUE(job_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_versions_job ON job_versions(job_id, version DESC);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_company_name(name: str) -> str:
    return "".join((name or "Unknown company").lower().split())


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def content_hash(job: dict) -> str:
    content = "\n".join(
        str(job.get(key, "")) for key in ("title", "salary", "location", "description")
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize(db_path: str | Path) -> Path:
    path = Path(db_path).expanduser().resolve()
    with connect(path) as connection:
        connection.executescript(SCHEMA)
    return path


def upsert_company(connection: sqlite3.Connection, company: dict) -> str:
    now = utc_now()
    name = str(company.get("name") or "Unknown company").strip()
    normalized = normalize_company_name(name)
    company_id = str(company.get("company_id") or stable_id("company", normalized))
    connection.execute(
        """
        INSERT INTO companies (
            company_id, name, normalized_name, industry, company_size, stage,
            introduction, website, source_url, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            name=excluded.name,
            industry=COALESCE(NULLIF(excluded.industry, ''), companies.industry),
            company_size=COALESCE(NULLIF(excluded.company_size, ''), companies.company_size),
            stage=COALESCE(NULLIF(excluded.stage, ''), companies.stage),
            introduction=COALESCE(NULLIF(excluded.introduction, ''), companies.introduction),
            website=COALESCE(NULLIF(excluded.website, ''), companies.website),
            source_url=COALESCE(NULLIF(excluded.source_url, ''), companies.source_url),
            updated_at=excluded.updated_at
        """,
        (
            company_id,
            name,
            normalized,
            str(company.get("industry") or ""),
            str(company.get("size") or company.get("company_size") or ""),
            str(company.get("stage") or ""),
            str(company.get("introduction") or ""),
            str(company.get("website") or ""),
            str(company.get("source_url") or ""),
            now,
            now,
        ),
    )
    return company_id


def upsert_job(connection: sqlite3.Connection, job: dict, company_id: str) -> tuple[str, bool]:
    now = utc_now()
    source = str(job.get("source") or "manual")
    external_id = str(job.get("external_id") or "")
    identity = (
        external_id
        or str(job.get("source_url") or "")
        or "|".join((company_id, str(job.get("title") or ""), str(job.get("location") or "")))
    )
    job_id = str(job.get("job_id") or stable_id("job", f"{source}|{identity}"))
    normalized = {
        **job,
        "title": str(job.get("title") or "Untitled role").strip(),
        "description": str(job.get("description") or "").strip(),
        "salary": str(job.get("salary") or "").strip(),
        "location": str(job.get("location") or "").strip(),
    }
    digest = content_hash(normalized)
    existing = connection.execute(
        "SELECT content_hash, first_seen FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    changed = existing is None or existing["content_hash"] != digest
    first_seen = existing["first_seen"] if existing else str(job.get("first_seen") or now)
    skills = sorted(set(str(item).strip() for item in job.get("skills", []) if str(item).strip()))
    directions = sorted(
        set(str(item).strip() for item in job.get("directions", []) if str(item).strip())
    )

    connection.execute(
        """
        INSERT INTO jobs (
            job_id, source, external_id, company_id, title, salary, location,
            experience, education, employment_type, skills_json, directions_json,
            description, source_url, status, first_seen, last_seen, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            company_id=excluded.company_id, title=excluded.title, salary=excluded.salary,
            location=excluded.location, experience=excluded.experience,
            education=excluded.education, employment_type=excluded.employment_type,
            skills_json=excluded.skills_json, directions_json=excluded.directions_json,
            description=excluded.description, source_url=excluded.source_url,
            status=excluded.status, last_seen=excluded.last_seen,
            content_hash=excluded.content_hash
        """,
        (
            job_id,
            source,
            external_id,
            company_id,
            normalized["title"],
            normalized["salary"],
            normalized["location"],
            str(job.get("experience") or ""),
            str(job.get("education") or ""),
            str(job.get("employment_type") or ""),
            json.dumps(skills, ensure_ascii=False),
            json.dumps(directions, ensure_ascii=False),
            normalized["description"],
            str(job.get("source_url") or ""),
            str(job.get("status") or "active"),
            first_seen,
            str(job.get("last_seen") or now),
            digest,
        ),
    )
    connection.execute(
        "DELETE FROM company_jobs WHERE job_id = ? AND company_id != ?",
        (job_id, company_id),
    )
    connection.execute(
        """
        INSERT INTO company_jobs (company_id, job_id, first_seen, last_seen, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(company_id, job_id) DO UPDATE SET
            last_seen=excluded.last_seen, status=excluded.status
        """,
        (company_id, job_id, first_seen, now, str(job.get("status") or "active")),
    )
    if changed:
        next_version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM job_versions WHERE job_id = ?",
            (job_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT OR IGNORE INTO job_versions (
                job_id, version, captured_at, content_hash, title, salary, location, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                next_version,
                now,
                digest,
                normalized["title"],
                normalized["salary"],
                normalized["location"],
                normalized["description"],
            ),
        )
    return job_id, changed
