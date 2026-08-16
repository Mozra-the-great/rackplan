# rackplan

Cross-platform desktop app for planning 19-inch equipment racks — pick your hardware,
lay it out by rack unit, see what fits.

Targets Windows and Linux, built with [Tauri](https://tauri.app/) (Rust backend,
web frontend).

> **Status:** early. The application is not scaffolded yet. What exists today is the
> brand dataset that the device catalogue will be built on.

## Data

### `data/brands/brands.jsonl`

1243 manufacturer brands that produce hardware in 19-inch rack format. One JSON object
per line ([JSON Lines](https://jsonlines.org/)), sorted alphabetically by `name`.

```json
{"id": "apc", "name": "APC", "categories": ["infrastructure_ups"], "parent": "schneider-electric"}
{"id": "dell-emc", "name": "Dell EMC", "categories": ["network", "servers"], "parent": "dell-technologies"}
{"id": "dbx", "name": "dbx", "categories": ["audio_proav"]}
```

| Field | Required | Description |
|---|---|---|
| `id` | yes | Globally unique slug matching `^[a-z0-9]+(-[a-z0-9]+)*$`. The stable key that device data will reference later |
| `name` | yes | Brand name as printed on the rack bezel |
| `categories` | yes | Non-empty, sorted array of category keys. Brands that span segments carry several |
| `parent` | no | `id` of the umbrella brand, when that umbrella is itself a rack badge |

#### Categories

| Key | Brands | Covers |
|---|---:|---|
| `network` | 416 | Networking and telecommunications — switches, routers, firewalls, optical transport, access gear |
| `audio_proav` | 423 | Pro audio, studio, live sound and pro AV — amplifiers, DSP, outboard, matrix switchers, wireless receivers, lighting control |
| `infrastructure_ups` | 311 | Rack infrastructure and power — UPS, PDUs, enclosures, KVM, rackmount chassis, cooling |
| `servers` | 182 | Server hardware, mainboards, blade systems and rack storage |

84 brands hold more than one category; 20 carry a `parent`.

#### Conventions

**Naming.** The name on the bezel wins over the legal entity: `HPE`, not
`Hewlett Packard Enterprise Company`; `APC`, not `APC by Schneider Electric`. A brand's
own capitalization is preserved verbatim — `dbx`, `MikroTik`, `Lab.gruppen`, `tvONE`,
`NETGEAR`, `beyerdynamic`.

**Multiple categories.** A brand belongs to every category it genuinely serves. Cisco is
`audio_proav` + `network` + `servers`; Huawei and Supermicro likewise span three. A single
category would have forced an arbitrary choice for 84 brands.

**Sub-brands.** `parent` links a brand to its umbrella, but only when that umbrella is
itself a real rack badge — `APC` → `schneider-electric`, `Tripp Lite` → `eaton`,
`Liebert` → `vertiv`. Pure holding companies are deliberately absent: it says `Crown` or
`Midas` on the front panel, never `Harman` or `Music Tribe`. Those brands therefore stand
on their own without a `parent`.

**Scope.** Discontinued and acquired badges are included — `3Com`, `Nortel`, `Compaq`,
`Sun Microsystems`, `Powerware`. Used equipment sits in real racks, and a planning tool
has to be able to name it.

**Sorting.** Lines are sorted by casefolded, ASCII-normalized `name`, so regenerating the
file yields a byte-identical result instead of a diff full of reordered lines.

**Field order** is fixed (`id`, `name`, `categories`, `parent`), and `parent` is omitted
entirely when absent rather than written as `null`.

## Validation

```sh
python3 scripts/validate_brands.py              # or pass a path
python3 -m unittest discover -s tests           # 35 tests for the validator itself
```

No dependencies, Python 3.9+. Checks JSON syntax per line, `id` uniqueness and slug
format, duplicate names, category keys, `parent` resolution and cycles, field order, sort
order, and rejects unknown fields. Exit code 0 means clean.

## License

Apache-2.0 — see [LICENSE](LICENSE).
