"""Source-agnostic JSON/CSV importers with a strict public field whitelist."""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .db import connect, initialize, upsert_company, upsert_job, utc_now

SENSITIVE_FIELDS = {
    "security_id",
    "securityId",
    "lid",
    "encrypt_boss_id",
    "encryptBossId",
    "boss_title",
    "boss_active_status",
    "recruiter",
    "recruiter_active_status",
    "phone",
    "mobile",
    "wechat",
    "cookie",
    "token",
}
SENSITIVE_QUERY_KEYS = {"securityid", "security_id", "lid", "token", "cookie"}


def _items(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [item.strip() for item in str(value).replace("|", ",").split(",") if item.strip()]


def _safe_url(value) -> str:
    """Remove request context from imported links while preserving ordinary query parameters."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query)
            if key.lower() not in SENSITIVE_QUERY_KEYS
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def normalize_record(raw: dict) -> dict:
    """Map common source fields into JobLens' safe canonical schema."""
    company_name = (
        raw.get("company_name") or raw.get("company") or raw.get("boss_name") or "Unknown company"
    )
    description = raw.get("description") or raw.get("jd") or raw.get("job_description") or ""
    source_url = _safe_url(raw.get("source_url") or raw.get("job_link") or raw.get("link") or "")
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
            "size": str(
                raw.get("company_size") or raw.get("company_scale") or raw.get("size") or ""
            ),
            "stage": str(raw.get("company_stage") or raw.get("stage") or ""),
            "introduction": str(raw.get("company_introduction") or raw.get("introduction") or ""),
            "website": str(raw.get("company_website") or raw.get("website") or ""),
            "source_url": _safe_url(raw.get("company_source_url") or raw.get("company_link") or ""),
        },
    }


def _read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _records_from_json(data, keys: tuple[str, ...]) -> list[dict]:
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = next((data[key] for key in keys if isinstance(data.get(key), list)), [])
    else:
        records = []
    if not all(isinstance(item, dict) for item in records):
        raise ValueError("Bundle records must be JSON objects")
    return records


def _record_key(record: dict) -> str:
    external_id = str(record.get("job_id") or record.get("external_id") or "").strip()
    if external_id:
        return f"id:{external_id}"
    link = _safe_url(record.get("job_link") or record.get("link") or record.get("source_url"))
    return f"url:{link}" if link else ""


def _observed_at(list_data) -> str:
    if isinstance(list_data, dict) and list_data.get("scraped_at"):
        return str(list_data["scraped_at"])
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sensitive_field_counts(records: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for field in SENSITIVE_FIELDS.intersection(record):
            if record.get(field) not in (None, "", [], {}):
                counts[field] = counts.get(field, 0) + 1
    return dict(sorted(counts.items()))


def load_bundle(
    input_path: str | Path,
    details_path: str | Path | None = None,
    *,
    source_name: str = "manual-json",
) -> tuple[list[dict], dict]:
    """Merge an offline list/details export and return safe canonical records plus diagnostics."""
    list_data = _read_json(input_path)
    list_records = _records_from_json(list_data, ("jobs", "records"))
    detail_data = _read_json(details_path) if details_path else []
    detail_records = _records_from_json(detail_data, ("details", "jobs", "records"))
    observed_at = _observed_at(list_data)

    details_by_key = {key: record for record in detail_records if (key := _record_key(record))}
    merged_records: list[dict] = []
    matched_keys: set[str] = set()
    missing_details = 0

    for list_record in list_records:
        key = _record_key(list_record)
        detail = details_by_key.get(key)
        merged = dict(list_record)
        if detail:
            matched_keys.add(key)
            for field in ("jd", "jd_status"):
                if detail.get(field) not in (None, "", [], {}):
                    merged[field] = detail[field]
            merged_skills = [*_items(merged.get("skills")), *_items(detail.get("skill_tags"))]
            if merged_skills:
                merged["skills"] = list(dict.fromkeys(merged_skills))
            if not merged.get("tags") and detail.get("tags_list"):
                merged["tags"] = detail["tags_list"]
        elif details_path:
            missing_details += 1
        merged_records.append(merged)

    details_only_records = [
        record
        for record in detail_records
        if (key := _record_key(record)) and key not in matched_keys
    ]
    merged_records.extend(details_only_records)

    canonical: list[dict] = []
    for raw in merged_records:
        external_id = str(raw.get("job_id") or raw.get("external_id") or "").strip()
        if not external_id:
            fallback = "|".join(
                str(raw.get(field) or "")
                for field in ("job_link", "link", "company", "boss_name", "title", "location")
            )
            external_id = hashlib.sha256(fallback.encode()).hexdigest()[:16]
        if not raw.get("tags") and raw.get("tags_list"):
            raw = {**raw, "tags": raw["tags_list"]}
        prepared = {
            **raw,
            "source": source_name,
            "external_id": external_id,
            "job_id": "",
            "first_seen": observed_at,
            "last_seen": observed_at,
            "status": "active",
        }
        canonical.append(normalize_record(prepared))

    metadata = list_data if isinstance(list_data, dict) else {}
    all_raw = [*list_records, *detail_records]
    diagnostics = {
        "source": source_name,
        "input": Path(input_path).name,
        "details": Path(details_path).name if details_path else "",
        "query": str(metadata.get("keyword") or ""),
        "city": str(metadata.get("city") or ""),
        "filters": metadata.get("filters") or {},
        "observed_at": observed_at,
        "list_count": len(list_records),
        "detail_count": len(detail_records),
        "matched_details": len(matched_keys),
        "missing_details": missing_details,
        "details_only": len(details_only_records),
        "canonical_count": len(canonical),
        "discarded_sensitive_fields": _sensitive_field_counts(all_raw),
    }
    return canonical, diagnostics


def import_bundle(
    db_path: str | Path,
    input_path: str | Path,
    details_path: str | Path | None = None,
    *,
    source_name: str = "manual-json",
    dry_run: bool = False,
) -> dict:
    records, diagnostics = load_bundle(input_path, details_path, source_name=source_name)
    result = {**diagnostics, "dry_run": dry_run}
    if dry_run:
        return result

    initialize(db_path)
    new_jobs = updated_jobs = unchanged_jobs = 0
    with connect(db_path) as connection:
        for record in records:
            existed = connection.execute(
                "SELECT 1 FROM jobs WHERE source = ? AND external_id = ? LIMIT 1",
                (record["source"], record["external_id"]),
            ).fetchone()
            company_id = upsert_company(connection, record["company"])
            _, was_changed = upsert_job(connection, record, company_id)
            if not existed:
                new_jobs += 1
            elif was_changed:
                updated_jobs += 1
            else:
                unchanged_jobs += 1

        run_id = f"run_{uuid.uuid4().hex[:16]}"
        connection.execute(
            """
            INSERT INTO import_runs (
                run_id, source, input_name, details_name, query, city, filters_json,
                observed_at, list_count, detail_count, matched_details, missing_details,
                details_only, imported, new_jobs, updated_jobs, unchanged_jobs, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_name,
                diagnostics["input"],
                diagnostics["details"],
                diagnostics["query"],
                diagnostics["city"],
                json.dumps(diagnostics["filters"], ensure_ascii=False),
                diagnostics["observed_at"],
                diagnostics["list_count"],
                diagnostics["detail_count"],
                diagnostics["matched_details"],
                diagnostics["missing_details"],
                diagnostics["details_only"],
                len(records),
                new_jobs,
                updated_jobs,
                unchanged_jobs,
                utc_now(),
            ),
        )
    return {
        **result,
        "run_id": run_id,
        "imported": len(records),
        "new": new_jobs,
        "updated": updated_jobs,
        "unchanged": unchanged_jobs,
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
