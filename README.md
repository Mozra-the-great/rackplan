# rackplan

Cross-platform desktop app for planning 19-inch equipment racks — pick your hardware,
lay it out by rack unit, see what fits.

Targets Windows and Linux, built with [Tauri](https://tauri.app/) (Rust backend,
web frontend).

> **Status:** early. The application is not scaffolded yet. What exists today is the
> brand dataset that the device catalogue will be built on, plus the device schema
> and its validator (`data/devices/`).

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

84 brands hold more than one category; 25 carry a `parent`.

#### Conventions

**Naming.** The name on the bezel wins over the legal entity: `HPE`, not
`Hewlett Packard Enterprise Company`; `APC`, not `APC by Schneider Electric`. A brand's
own capitalization is preserved verbatim — `dbx`, `MikroTik`, `Lab.gruppen`, `tvONE`,
`NETGEAR`, `beyerdynamic`.

**Multiple categories.** A brand belongs to every category it genuinely serves. Cisco is
`audio_proav` + `network` + `servers`; Huawei and Supermicro likewise span three. A single
category would have forced an arbitrary choice for 84 brands.

**Sub-brands.** `parent` links a brand to its umbrella when two conditions hold: the
umbrella is itself a real rack badge, and the brand was actually marketed under it —
`APC` → `schneider-electric`, `Tripp Lite` → `eaton`, `Ruckus` → `commscope`.

Two cases are excluded on purpose. Pure holding companies are absent from the dataset
entirely: it says `Crown` or `Midas` on the front panel, never `Harman` or `Music Tribe`,
so those brands correctly stand alone. And a mere corporate link is not enough — a renamed
legal entity (`Emerson Network Power` → Vertiv), a joint venture
(`Fujitsu Siemens Computers`) or an acquisition whose badge was retired (`Compaq`,
`Sun Microsystems`) gets no `parent`, because the brand was never sold under the other
name.

`parent` coverage is best-effort rather than exhaustive; more links can be added without
any schema change.

**Scope.** Discontinued and acquired badges are included — `3Com`, `Nortel`, `Compaq`,
`Sun Microsystems`, `Powerware`. Used equipment sits in real racks, and a planning tool
has to be able to name it.

**Sorting.** Lines are sorted by casefolded, ASCII-normalized `name`, with `id` as a
tie-breaker, so regenerating the file yields a byte-identical result instead of a diff
full of reordered lines. (The tie-breaker never actually fires, since duplicate names are
themselves a validation error — but a generator has to pick something deterministic.)

**Field order** is fixed (`id`, `name`, `categories`, `parent`), and `parent` is omitted
entirely when absent rather than written as `null`.

### `data/devices/<brand-id>.jsonl`

One file per brand, named after the brand `id` (`zyxel.jsonl` for brand `zyxel`). One
JSON object per line, one rack-mountable device per line, sorted alphabetically by
`model`. Empty while the catalogue is being filled in.

```json
{
  "id": "zyxel-gs1900-24e",
  "brand": "zyxel",
  "model": "GS1900-24E",
  "category": "network",
  "height_u": 1,
  "width": "full",
  "depth_mm": 300,
  "weight_kg": 2.36,
  "power_w": 10.5,
  "mounting": "rack-ears",
  "source": "https://example.com/datasheet.pdf",
  "ports": ["24x RJ45 1GbE", "2x SFP"]
}
```

| Field | Required | Description |
|---|---|---|
| `id` | yes | Globally unique slug across all device files, matching `^[a-z0-9]+(-[a-z0-9]+)*$`. Convention: `<brand-id>-<model-in-lowercase>` |
| `brand` | yes | `id` of an existing brand in `brands.jsonl`; must match the filename |
| `model` | yes | Model designation as printed on the device |
| `category` | yes | One of the four category keys |
| `height_u` | yes | Rack height in U, integer ≥ 1 — `0` only with `mounting: "0U"` |
| `width` | yes | `full` · `half` · `third` · `other` |
| `depth_mm` | no | Chassis depth in mm |
| `weight_kg` | no | Weight in kg |
| `power_w` | no | Typical/max power draw in W, as per the datasheet |
| `mounting` | yes | `rack-ears` · `shelf` · `rail` · `0U` |
| `source` | yes | URL of the manufacturer datasheet or product page the values were taken from |
| `ports` | no | Array of short strings, e.g. `["24x RJ45 1GbE", "2x SFP+"]` |

**Measured values are never guessed.** Without a published figure, the field is
omitted — never `0`, never `null`, never an estimate. This is the rule behind
"required but absent" for `depth_mm`, `weight_kg` and `power_w`.

**Per-brand provenance.** Every record must point at its source. A device without a
`source` cannot be verified and therefore cannot be merged.

## Validation

```sh
python3 scripts/validate_brands.py              # or pass a path
python3 scripts/validate_devices.py             # validates all of data/devices/
python3 -m unittest discover -s tests           # 49 + 52 tests for the validators
```

All run on every push and pull request (`.github/workflows/validate.yml`).

No dependencies, Python 3.9+. The brand validator checks JSON syntax per line, `id`
uniqueness and slug format, duplicate names, category keys, `parent` resolution and
cycles, field order, sort order, and rejects unknown fields. The device validator
additionally enforces the per-brand file layout, enum keys, positive measurements,
`height_u`/`mounting` consistency, http(s) `source` URLs, and cross-file checks:
every `brand` must exist in `brands.jsonl`, and device `id`s must be unique across all
of `data/devices/`. Exit code 0 means clean.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
