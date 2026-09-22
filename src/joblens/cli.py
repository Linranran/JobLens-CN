"""JobLens command-line interface."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .db import connect, initialize
from .importers import import_file
from .matching import load_profile, score_database
from .reports import build_report, export_public_json, version_diff

DEFAULT_DB = ".joblens/joblens.db"


def command_init(args):
    print(f"Initialized {initialize(args.db)}")


def command_import(args):
    result = import_file(args.db, args.input)
    print(json.dumps(result, ensure_ascii=False))


def command_score(args):
    count = score_database(args.db, load_profile(args.profile))
    print(f"Scored {count} jobs")


def command_report(args):
    print(build_report(args.db, args.output))


def command_export(args):
    print(export_public_json(args.db, args.output))


def command_stats(args):
    initialize(args.db)
    with connect(args.db) as connection:
        companies = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        versions = connection.execute("SELECT COUNT(*) FROM job_versions").fetchone()[0]
        scored = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE match_score IS NOT NULL"
        ).fetchone()[0]
    print(
        json.dumps({"companies": companies, "jobs": jobs, "versions": versions, "scored": scored})
    )


def command_history(args):
    print(version_diff(args.db, args.job_id))


def command_demo(args):
    examples = Path(__file__).with_name("data")
    workspace = Path(args.output).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "joblens.db"
    import_file(db_path, examples / "sample_jobs.json")
    score_database(db_path, load_profile(examples / "profile.example.json"))
    report = build_report(db_path, workspace / "company_job_report.md")
    export_public_json(db_path, workspace / "jobs_export.json")
    print(f"Demo ready: {report}")


def command_dashboard(args):
    try:
        import streamlit  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Install dashboard support first: pip install 'joblens-cn[dashboard]'"
        ) from exc
    app = Path(__file__).with_name("dashboard_app.py")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app), "--", "--db", str(args.db)],
        check=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="joblens", description="Local-first company–job intelligence"
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(required=True)

    init = sub.add_parser("init", help="Initialize a local SQLite database")
    init.add_argument("--db", default=DEFAULT_DB)
    init.set_defaults(func=command_init)

    importer = sub.add_parser("import", help="Import canonical or common JSON/CSV job data")
    importer.add_argument("input")
    importer.add_argument("--db", default=DEFAULT_DB)
    importer.set_defaults(func=command_import)

    scorer = sub.add_parser("score", help="Score jobs against a local candidate profile")
    scorer.add_argument("--profile", required=True)
    scorer.add_argument("--db", default=DEFAULT_DB)
    scorer.set_defaults(func=command_score)

    report = sub.add_parser("report", help="Generate a company–job Markdown report")
    report.add_argument("--output", default="out/company_job_report.md")
    report.add_argument("--db", default=DEFAULT_DB)
    report.set_defaults(func=command_report)

    export = sub.add_parser("export", help="Export a safe canonical JSON file")
    export.add_argument("--output", default="out/jobs_export.json")
    export.add_argument("--db", default=DEFAULT_DB)
    export.set_defaults(func=command_export)

    stats = sub.add_parser("stats", help="Print database statistics")
    stats.add_argument("--db", default=DEFAULT_DB)
    stats.set_defaults(func=command_stats)

    history = sub.add_parser("history", help="Show the latest JD change for a job")
    history.add_argument("job_id")
    history.add_argument("--db", default=DEFAULT_DB)
    history.set_defaults(func=command_history)

    demo = sub.add_parser("demo", help="Build a complete demo from synthetic data")
    demo.add_argument("--output", default="demo-output")
    demo.set_defaults(func=command_demo)

    dashboard = sub.add_parser("dashboard", help="Launch the optional local Streamlit dashboard")
    dashboard.add_argument("--db", default=DEFAULT_DB)
    dashboard.set_defaults(func=command_dashboard)
    return parser


def main(argv: list[str] | None = None):
    args = build_parser().parse_args(argv)
    args.func(args)
