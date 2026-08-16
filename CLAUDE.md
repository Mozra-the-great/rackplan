# rackplan

> Cross-platform desktop app for planning 19-inch equipment racks.

## Type
Desktop application (Windows/Linux) — currently in data-groundwork stage, no app code yet.

## Stack
Tauri (Rust backend + web frontend). Data files are plain JSONL, validated by a
dependency-free Python 3 script. There are no third-party Python packages and there
should not be any — keep the validator and its tests on the standard library.

## Structure
```
data/brands/brands.jsonl        1243 brands that make 19-inch rack hardware
scripts/validate_brands.py      schema + integrity validation
tests/test_validate_brands.py   35 unittest cases for the validator
```

The Tauri app is not scaffolded yet. When it is, it goes into `src/` (frontend) and
`src-tauri/` (Rust); `.gitignore` already covers both.

## Commands
```sh
python3 scripts/validate_brands.py      # validate the dataset (exit 0 = clean)
python3 -m unittest discover -s tests   # test the validator itself
```

## Data model — `data/brands/brands.jsonl`

One JSON object per line, sorted alphabetically by `name`.

```json
{"id": "apc", "name": "APC", "categories": ["infrastructure_ups"], "parent": "schneider-electric"}
{"id": "cisco", "name": "Cisco", "categories": ["audio_proav", "network", "servers"]}
```

| Field | Rule |
|---|---|
| `id` | Globally unique slug, `^[a-z0-9]+(-[a-z0-9]+)*$`, ASCII only. `FS.com` → `fs-com`, `Rohde & Schwarz` → `rohde-schwarz` |
| `name` | As printed on the rack bezel, not the legal entity. `HPE`, not `Hewlett Packard Enterprise Company`. Brand capitalization preserved verbatim (`dbx`, `MikroTik`, `NETGEAR`) |
| `categories` | Non-empty, sorted, deduplicated. Keys: `network` · `audio_proav` · `infrastructure_ups` · `servers`. A brand may hold several |
| `parent` | Optional. `id` of the umbrella brand, set only when that umbrella is itself a real rack badge. Pure holdings (Harman, Music Tribe) are not in the dataset at all, so their brands are correctly parentless |

Field order is fixed: `id`, `name`, `categories`, `parent`. Omit `parent` rather than
writing `null`.

Sorting is by casefolded, ASCII-normalized `name` — deterministic, so a regenerated file
produces no phantom diffs. The validator enforces this; do not re-sort by hand.

## Notes
- No environment variables, no secrets.
- Run the validator before committing any dataset edit. It catches duplicate ids and
  names, bad slugs, unknown categories, dangling or cyclic `parent` references, wrong
  field order and broken sort order.

---

## Working rules

These rules apply regardless of what's above. They mirror the operator's global
Claude Code configuration so this repo behaves consistently even if opened on a
different machine or by a collaborator.

### Language
- Chat responses: German
- Everything that goes into the repo — code, comments, commit messages, branch
  names, PR descriptions, CHANGELOG: English (default, more compact)
- Respect a project's already-established language convention if one exists

### Approach — get it right once instead of fixing it ten times
1. Fully understand the task before starting
2. Think through the solution: edge cases, error handling, dependencies, blast radius
3. Only then implement it completely and correctly

No placeholders. No `// TODO` without a resolution attached. No half-finished
implementations.

For larger tasks: use Plan Mode before writing code. If something is fundamentally
unclear and would change the direction of the solution, ask once rather than
building in the wrong direction.

### Coding rules
- TypeScript: no `any`, explicit types
- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`
- Follow the project's existing conventions over these defaults when they conflict

### Git workflow
- Never commit directly to `main`/`master` — always a feature branch
- Branch names in English, kebab-case (`feat/...`, `fix/...`)
- Before every push: check `git status` and `git diff --staged`
- No `git push --force` on main/master

### Security
- `.env`, `.env.*`, `*.pem`, `*.key`, `*.secret` — never read, log, or commit
- No credentials/tokens/passwords in code
- Secrets via environment variables or a secrets manager, never in plaintext

### Subagents — delegate proactively
Use these specialists without being asked each time, as soon as the situation fits:

- **test-runner** → right after writing or changing application code
- **security-reviewer** → after auth/input/dependency changes, and before any release
- **code-reviewer** → before a merge / after finishing a feature
- **debugger** → as soon as a test fails, a stack trace shows up, or behavior is unexpected

Run independent analyses (e.g. security + tests) in parallel. Skip subagents for
trivial changes — the overhead isn't worth it.
