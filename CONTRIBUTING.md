# Contributing

## Setup

```bash
uv sync --extra dev
uv run sonoscribe
uv run pytest
```

## Pull requests

Open PRs against `main`. Keep the change scoped. Match the surrounding style. Do not commit secrets, Keychain material, or local `library.json` / `stats.json` / `settings.json`.

By submitting a contribution you license it under [GPL-3.0-only](LICENSE), the same terms as this repository.

## Release

```bash
git tag v0.1.0
git push origin v0.1.0
```

The release workflow builds `Sonoscribe.app` and attaches `Sonoscribe-macos-arm64.zip` to the GitHub Release.
