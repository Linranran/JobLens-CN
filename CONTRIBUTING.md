# Contributing

Thanks for helping improve JobLens-CN.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest
```

## Pull requests

- Keep the core source-agnostic and local-first.
- Add tests for behavior changes.
- Use synthetic fixtures; never commit real resumes, cookies, private messages or request tokens.
- Explain any data-source permissions and rate limits when proposing a connector.
- Keep matching results explainable and label probabilistic output clearly.

Good first contributions include import adapters, Chinese skill aliases, report templates, accessibility improvements and documentation translations.
