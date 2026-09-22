# Data model

JobLens stores normalized records in SQLite and uses JSON only for import/export.

## Company

| Field | Type | Notes |
|---|---|---|
| `company_id` | string | Stable SHA-256-derived ID unless explicitly supplied |
| `name` | string | Display name |
| `industry` | string | Optional |
| `company_size` | string | Optional |
| `stage` | string | Optional funding or ownership stage |
| `introduction` | string | User-provided or source-attributed introduction |
| `website` | string | Public company website |
| `source_url` | string | Source used for company metadata |

## Job

| Field | Type | Notes |
|---|---|---|
| `job_id` | string | Stable ID based on source and external identity |
| `source` | string | `manual`, ATS name, or custom adapter name |
| `external_id` | string | Source-specific public job ID |
| `company_id` | string | Foreign key to company |
| `title` | string | Required |
| `salary` | string | Original public display text |
| `location` | string | Original location text |
| `experience` | string | Optional |
| `education` | string | Optional |
| `skills` | string[] | Declared public skill tags |
| `directions` | string[] | User/source direction labels |
| `description` | string | Job description text |
| `source_url` | string | Public source URL |
| `status` | string | Usually `active`, `closed`, or `unknown` |
| `first_seen` | datetime | Preserved across repeated imports |
| `last_seen` | datetime | Updated on import |

## Version history

A new `job_versions` row is created when any of title, salary, location, or description changes. Duplicate imports do not create versions.

## Import runs

Each successful `import-bundle` execution creates an `import_runs` audit row with source,
filenames, search metadata, observation time, merge coverage, and new/updated/unchanged counts.
`--dry-run` never creates a database or audit row.

## Explicitly discarded fields

Importers use a whitelist. Browser cookies, request/security tokens, internal encrypted IDs, recruiter private contact details and arbitrary page snapshots are not persisted.
