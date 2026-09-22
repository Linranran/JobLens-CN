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
