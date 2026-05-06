# Contributing

Thanks for your interest in Trust Auditor.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
export PYTHONPATH=src
pytest tests/
```

## Pull requests

- Keep changes focused; match existing style and typing.
- Add or update tests for behavior changes.
- Do not commit secrets (`.env`, API keys, service accounts). See [docs/GITHUB_PUBLISH.md](docs/GITHUB_PUBLISH.md).

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
