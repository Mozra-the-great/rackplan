# Contributing

This is primarily a personal/solo-maintained project. If you're proposing a
change:

## Workflow

1. Never commit directly to `main` — create a feature branch.
2. Branch names: English, kebab-case, prefixed by type — `feat/...`,
   `fix/...`, `chore/...`, `docs/...`, `refactor/...`, `test/...`.
3. Commits follow [Conventional Commits](https://www.conventionalcommits.org/):
   `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
4. Open a pull request against `main`. CI (and, where configured, Claude Code
   review) must pass before merge.
5. No `git push --force` on `main`.

## Reporting bugs / requesting features

Use the issue templates under `.github/ISSUE_TEMPLATE/`.

## Contributing device data

Device records store factual specifications only, each with a `source` URL. Read the
[Data policy](docs/DATA-POLICY.md) before contributing, the schema documentation in
[`README.md`](README.md) (Data) for the record format, and validate with
`python3 scripts/validate_devices.py` before opening the PR.

## Security issues

Do not open a public issue — see [`SECURITY.md`](SECURITY.md).
