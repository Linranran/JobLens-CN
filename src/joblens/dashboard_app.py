"""Optional Streamlit dashboard for local JobLens databases."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def parse_db() -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--db", default=".joblens/joblens.db")
    args, _ = parser.parse_known_args()
    return Path(args.db).expanduser().resolve()


def selected_job_id_from_cells(
    rows: list[dict], selected_cells: list[tuple[int, str]]
) -> str | None:
    """Resolve a dataframe cell-selection event to a stable job ID."""
    if not selected_cells:
        return None
    index = selected_cells[0][0]
    if index < 0 or index >= len(rows):
        return None
    return str(rows[index]["job_id"])


def main():
    import streamlit as st

    db_path = parse_db()
    st.set_page_config(page_title="JobLens-CN", page_icon="🔭", layout="wide")
    st.markdown(
        "<style>[data-testid='stToolbar']{display:none}</style>",
        unsafe_allow_html=True,
    )
    st.title("🔭 JobLens-CN")
    st.caption("Local-first company–job intelligence")
    if not db_path.exists():
        st.error(f"Database does not exist: {db_path}")
        st.code("joblens demo && joblens dashboard --db demo-output/joblens.db")
        return

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    company_count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    job_count = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    scored_count = connection.execute(
        "SELECT COUNT(*) FROM jobs WHERE match_score IS NOT NULL"
    ).fetchone()[0]
    version_count = connection.execute("SELECT COUNT(*) FROM job_versions").fetchone()[0]
    cols = st.columns(4)
    for col, label, value in zip(
        cols,
        ("Companies", "Jobs", "Scored", "JD versions"),
        (company_count, job_count, scored_count, version_count),
        strict=True,
    ):
        col.metric(label, value)

    locations = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT location FROM jobs WHERE location != '' ORDER BY location"
        )
    ]
    statuses = [
        row[0] for row in connection.execute("SELECT DISTINCT status FROM jobs ORDER BY status")
    ]
    with st.sidebar:
        st.header("Filters")
        query = st.text_input("Search title / company / JD")
        location = st.selectbox("Location", ["All", *locations])
        status = st.selectbox("Status", ["All", *statuses])
        minimum_score = st.slider("Minimum match score", 0, 100, 0)

    sql = """
        SELECT j.job_id, c.name AS company, j.title, j.salary, j.location, j.status,
               j.match_score, j.recommendation, j.matched_skills_json,
               j.missing_skills_json, j.match_explanation, j.description,
               j.source_url, c.industry, c.introduction
        FROM jobs j JOIN companies c ON c.company_id=j.company_id WHERE 1=1
    """
    params: list[object] = []
    if query:
        sql += " AND (j.title LIKE ? OR c.name LIKE ? OR j.description LIKE ?)"
        token = f"%{query}%"
        params += [token, token, token]
    if location != "All":
        sql += " AND j.location=?"
        params.append(location)
    if status != "All":
        sql += " AND j.status=?"
        params.append(status)
    sql += (
        " AND COALESCE(j.match_score, 0) >= ?"
        " ORDER BY COALESCE(j.match_score, -1) DESC, c.name, j.title"
    )
    params.append(minimum_score)
    rows = [dict(row) for row in connection.execute(sql, params)]
    st.subheader(f"Jobs ({len(rows)})")
    recommendation_labels = {
        "must_review": "重点关注",
        "recommended": "建议关注",
        "consider": "可考虑",
        "low_match": "低匹配",
    }
    table = [
        {
            "company": row["company"],
            "title": row["title"],
            "salary": row["salary"],
            "location": row["location"],
            "score": row["match_score"],
            "recommendation": recommendation_labels.get(
                row["recommendation"], row["recommendation"]
            ),
            "status": row["status"],
        }
        for row in rows
    ]
    st.caption("点击 company、title 等任意单元格，可自动在下方展示对应岗位详情。")

    def choose_from_table() -> None:
        table_state = st.session_state.get("job_table")
        selected_cells = list(table_state.selection.cells) if table_state else []
        clicked_job_id = selected_job_id_from_cells(rows, selected_cells)
        if clicked_job_id:
            st.session_state["selected_job_id"] = clicked_job_id
            st.session_state["job_inspector"] = clicked_job_id

    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        key="job_table",
        on_select=choose_from_table,
        selection_mode="single-cell",
    )
    if rows:
        job_ids = [str(row["job_id"]) for row in rows]
        labels = {str(row["job_id"]): f"{row['company']} · {row['title']}" for row in rows}
        selected_job_id = st.session_state.get("job_inspector") or st.session_state.get(
            "selected_job_id"
        )
        if selected_job_id not in job_ids:
            selected_job_id = job_ids[0]

        # This assignment happens before the selectbox is instantiated, so a table click
        # and a dropdown selection stay in sync without requiring a second user action.
        st.session_state["job_inspector"] = selected_job_id
        selected_job_id = st.selectbox(
            "岗位详情（也可下拉选择）",
            job_ids,
            format_func=labels.__getitem__,
            key="job_inspector",
        )
        st.session_state["selected_job_id"] = selected_job_id
        selected = next(row for row in rows if str(row["job_id"]) == selected_job_id)
        left, right = st.columns([2, 1])
        with left:
            st.markdown(f"### {selected['title']}")
            st.markdown(selected["description"] or "No JD available.")
        with right:
            st.markdown(f"### {selected['company']}")
            st.caption(selected["industry"] or "Industry not provided")
            st.write(selected["introduction"] or "No company introduction available.")
            st.metric(
                "Match score",
                selected["match_score"] if selected["match_score"] is not None else "—",
            )
            st.write(selected["match_explanation"] or "Not scored")
            st.write(
                "**Matched skills**",
                ", ".join(json.loads(selected["matched_skills_json"])) or "None",
            )
            st.write(
                "**Skill gaps**", ", ".join(json.loads(selected["missing_skills_json"])) or "None"
            )
            if selected["source_url"]:
                st.link_button("Open source", selected["source_url"])
    connection.close()


if __name__ == "__main__":
    main()
