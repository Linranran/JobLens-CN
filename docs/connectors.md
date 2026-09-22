# Connector design

JobLens core is source-agnostic. A connector should produce canonical JSON or call `import_records` directly.

## Connector requirements

1. Use an official API, public ATS endpoint, user-owned export, or manual paste wherever possible.
2. Respect the source's robots policy, terms of service, rate limits and applicable law.
3. Never persist login cookies, session storage, request signatures or private messages.
4. Emit only canonical public fields from `docs/data-model.md`.
5. Include a stable `source` and `external_id` so repeated imports update instead of duplicate.
6. Implement bounded retries and clear failure reporting.
7. Add unit tests using recorded synthetic fixtures, not live user accounts.

## Recommended first-party connectors

- Manual JSON/CSV export
- Clipboard/pasted job description
- Greenhouse public job-board API
- Lever public postings API
- Ashby public job-board API

Site-specific authenticated automation should live outside the public core unless the platform explicitly permits it.

## Optional BOSS offline workflow

The external [boss-zhipin-scraper](https://github.com/eatmoreduck/boss-zhipin-scraper)
skill can be used as an optional upstream exporter. It is not bundled, imported, or invoked by
JobLens. Keep its authenticated browser profile outside this repository, export a list JSON and
a detail JSON into `data/private/`, and then use the offline bundle importer:

```bash
joblens import-bundle data/private/boss/jobs.json \
  --details data/private/boss/details.json \
  --source boss-manual-export \
  --dry-run
```

Review the preview before repeating the command without `--dry-run`. Use the same stable source
name for later snapshots so that JobLens can update existing jobs and retain JD history. The
step-by-step installation, browser setup and export commands are documented in the main README.

## Offline list/details bundles

Tools that export a lightweight job list and a separate JD-detail file can be used without
embedding the tool in JobLens:

```bash
joblens import-bundle data/private/jobs.json \
  --details data/private/details.json \
  --source manual-json \
  --dry-run
```

After reviewing the diagnostics, omit `--dry-run` to write the database. JobLens joins records
by the source job ID (falling back to a sanitized URL), namespaces the external ID by `source`,
and strips request context and recruiter-related fields. Never import the two files sequentially:
a detail-only record can otherwise overwrite richer list metadata with empty values.

An absent job is not automatically closed. The dashboard classifies records by `last_seen` as
recent (0–7 days), possibly stale (8–30 days), or stale (over 30 days). Confirm closure at the
source before changing a job to `closed`.
