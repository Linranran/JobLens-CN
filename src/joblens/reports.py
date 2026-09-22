"""Markdown reports and JD version diffs."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from .db import connect


def _value(value) -> str:
    return str(value or "Not provided").strip()


def build_report(db_path: str | Path, output_path: str | Path) -> Path:
    with connect(db_path) as connection:
        companies = connection.execute(
            """
            SELECT c.*, COUNT(j.job_id) AS job_count,
                   MAX(COALESCE(j.match_score, 0)) AS best_score
            FROM companies c LEFT JOIN jobs j ON j.company_id = c.company_id
            GROUP BY c.company_id ORDER BY best_score DESC, job_count DESC, c.name
            """
        ).fetchall()
        total_jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        scored_jobs = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE match_score IS NOT NULL"
        ).fetchone()[0]
        lines = [
            "# JobLens Company–Job Report",
            "",
            f"- Companies: {len(companies)}",
            f"- Jobs: {total_jobs}",
            f"- Scored jobs: {scored_jobs}",
            "- Match scores are explainable heuristics, not hiring predictions.",
            "",
        ]
        for index, company in enumerate(companies, 1):
            lines += [
                f"## {index}. {company['name']}",
                "",
                f"- Industry: {_value(company['industry'])}",
                f"- Size: {_value(company['company_size'])}",
                f"- Stage: {_value(company['stage'])}",
                f"- Website: {_value(company['website'])}",
                "",
                "### Company introduction",
                "",
                company["introduction"] or "No introduction available.",
                "",
                "### Jobs",
                "",
            ]
            jobs = connection.execute(
                """
                SELECT * FROM jobs WHERE company_id=?
                ORDER BY COALESCE(match_score, -1) DESC, title
                """,
                (company["company_id"],),
            ).fetchall()
            for job in jobs:
                score = "unscored" if job["match_score"] is None else f"{job['match_score']:.1f}"
                link = f"[source]({job['source_url']})" if job["source_url"] else "no source URL"
                lines.append(
                    f"- **{job['title']}** · {_value(job['salary'])} · {_value(job['location'])} · "
                    f"score {score} · {job['recommendation'] or 'unscored'} · {link}"
                )
            lines.append("")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def version_diff(db_path: str | Path, job_id: str) -> str:
    with connect(db_path) as connection:
        versions = connection.execute(
            "SELECT * FROM job_versions WHERE job_id=? ORDER BY version DESC LIMIT 2",
            (job_id,),
        ).fetchall()
    if not versions:
        return f"No versions found for {job_id}."
    if len(versions) == 1:
        return f"Only version 1 exists for {job_id}; no diff is available."
    current, previous = versions[0], versions[1]
    before = previous["description"].splitlines()
    after = current["description"].splitlines()
    diff = difflib.unified_diff(
        before,
        after,
        fromfile=f"v{previous['version']}",
        tofile=f"v{current['version']}",
        lineterm="",
    )
    return "\n".join(diff) or "The JD text is unchanged; another tracked field changed."


def export_public_json(db_path: str | Path, output_path: str | Path) -> Path:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT j.job_id, c.name AS company_name, j.title, j.salary, j.location,
                   j.experience, j.education, j.employment_type, j.skills_json,
                   j.directions_json, j.description, j.source_url, j.status,
                   j.first_seen, j.last_seen, j.match_score, j.recommendation,
                   j.matched_skills_json, j.missing_skills_json, j.match_explanation
            FROM jobs j JOIN companies c ON c.company_id=j.company_id
            ORDER BY COALESCE(j.match_score, -1) DESC, c.name, j.title
            """
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        for key in ("skills_json", "directions_json", "matched_skills_json", "missing_skills_json"):
            item[key.removesuffix("_json")] = json.loads(item.pop(key))
        jobs.append(item)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output
