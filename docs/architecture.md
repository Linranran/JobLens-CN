# Architecture

```text
Import adapters
    │
    ▼
Safe canonical schema
    │
    ├── companies
    ├── jobs
    ├── company_jobs
    └── job_versions
    │
    ├── explainable matcher
    ├── Markdown / JSON export
    └── local Streamlit dashboard
```

The core package intentionally has no runtime dependency. SQLite, CLI, import, scoring, reports and version history use the Python standard library. Streamlit is an optional extra.
