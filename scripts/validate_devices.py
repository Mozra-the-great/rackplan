#!/usr/bin/env python3
"""Validate data/devices/<brand-id>.jsonl.

Checks syntax, schema, per-file and cross-file integrity (brand references),
and sort order. Exits 0 when the dataset is clean, 1 otherwise. No third-party
dependencies.
"""

from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

DEFAULT_DEVICES_DIR = Path(__file__).resolve().parent.parent / "data" / "devices"
DEFAULT_BRANDS_FILE = Path(__file__).resolve().parent.parent / "data" / "brands" / "brands.jsonl"

KNOWN_CATEGORIES = ("audio_proav", "infrastructure_ups", "network", "servers")
KNOWN_WIDTHS = ("full", "half", "third", "other")
KNOWN_MOUNTINGS = ("0U", "rack-ears", "rail", "shelf")
FIELD_ORDER = ("id", "brand", "model", "category", "height_u", "width", "depth_mm", "weight_kg", "power_w", "mounting", "source", "ports")
REQUIRED_FIELDS = ("id", "brand", "model", "category", "height_u", "width", "mounting", "source")
# Matched with fullmatch, not match: `$` also matches just before a trailing
# newline, so "foo\n" would otherwise pass as a valid slug — and then count as a
# separate id from "foo", defeating the duplicate check too.
SLUG_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def sort_key(name: str) -> str:
    """Deterministic collation key: strip accents, then casefold.

    Plain `sorted()` on the raw model name is locale- and case-sensitive, which
    would place "dbx", "3M" and "Ätna" differently across runs and platforms.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold()


class _JsonObject(list):
    """A JSON object, kept as key/value pairs so field order stays inspectable.

    `object_pairs_hook` fires only for objects, but hands us a list — which makes a
    real JSON array indistinguishable from an object by type alone. Tagging objects
    with this subclass keeps the two apart.
    """


def parse_lines(raw: str, errors: list[str]) -> list[tuple[int, dict]]:
    """Parse each line into an object, recording errors instead of raising."""
    entries: list[tuple[int, dict]] = []

    if not raw.endswith("\n"):
        errors.append("file does not end with a newline")

    for lineno, line in enumerate(raw.split("\n")[:-1] if raw.endswith("\n") else raw.split("\n"), 1):
        if not line.strip():
            errors.append(f"line {lineno}: empty line — JSONL allows exactly one object per line")
            continue
        if line != line.strip():
            errors.append(f"line {lineno}: leading or trailing whitespace")

        try:
            obj = json.loads(line, object_pairs_hook=_JsonObject)
        except json.JSONDecodeError as exc:
            errors.append(f"line {lineno}: invalid JSON — {exc.msg} at column {exc.colno}")
            continue

        if not isinstance(obj, _JsonObject):
            kind = "array" if isinstance(obj, list) else type(obj).__name__
            errors.append(f"line {lineno}: expected a JSON object, got {kind}")
            continue

        keys = [k for k, _ in obj]
        if len(keys) != len(set(keys)):
            errors.append(f"line {lineno}: duplicate keys in object")
            continue

        expected_order = [f for f in FIELD_ORDER if f in keys]
        if keys != expected_order:
            errors.append(
                f"line {lineno}: field order is {keys}, expected {expected_order}"
            )

        entries.append((lineno, dict(obj)))

    return entries


def check_positive_number(lineno: int, field: str, value: object, errors: list[str]) -> None:
    """Check that an optional measure is a finite, strictly positive number.

    bool is a subclass of int, so True would sneak past an isinstance(value,
    (int, float)) check — reject bools explicitly. Missing data is omitted,
    not zero, so 0 is as invalid as a negative number here.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"line {lineno}: '{field}' must be a number")
    elif not math.isfinite(value):
        errors.append(f"line {lineno}: '{field}' must be finite")
    elif value <= 0:
        errors.append(f"line {lineno}: '{field}' must be positive, got {value}")


def check_entry(lineno: int, entry: dict, errors: list[str]) -> None:
    """Validate a single entry's fields in isolation."""
    unknown = [k for k in entry if k not in FIELD_ORDER]
    if unknown:
        errors.append(f"line {lineno}: unknown field(s) {unknown}")

    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"line {lineno}: missing required field '{field}'")

    device_id = entry.get("id")
    if device_id is not None:
        if not isinstance(device_id, str):
            errors.append(f"line {lineno}: 'id' must be a string")
        elif not SLUG_RE.fullmatch(device_id):
            errors.append(f"line {lineno}: id {device_id!r} is not a valid slug")

    brand = entry.get("brand")
    if brand is not None:
        if not isinstance(brand, str):
            errors.append(f"line {lineno}: 'brand' must be a string")
        elif not SLUG_RE.fullmatch(brand):
            errors.append(f"line {lineno}: brand {brand!r} is not a valid slug")

    model = entry.get("model")
    if model is not None:
        if not isinstance(model, str):
            errors.append(f"line {lineno}: 'model' must be a string")
        elif not model.strip():
            errors.append(f"line {lineno}: 'model' is empty")
        elif model != model.strip():
            errors.append(f"line {lineno}: model {model!r} has leading/trailing whitespace")
        elif any(unicodedata.category(c) == "Cc" for c in model):
            errors.append(f"line {lineno}: model {model!r} contains control characters")

    category = entry.get("category")
    if category is not None and (not isinstance(category, str) or category not in KNOWN_CATEGORIES):
        errors.append(f"line {lineno}: category {category!r} is not a known category key")

    if "height_u" in entry:
        height = entry.get("height_u")
        # bool is a subclass of int, so gate the 0U exception on a clean
        # integer explicitly before comparing against 0.
        if isinstance(height, bool) or not isinstance(height, int):
            errors.append(f"line {lineno}: 'height_u' must be an integer")
        elif height < 0:
            errors.append(f"line {lineno}: 'height_u' must not be negative, got {height}")
        elif height == 0 and entry.get("mounting") != "0U":
            errors.append(f"line {lineno}: height_u 0 is only allowed with mounting '0U'")

    width = entry.get("width")
    if width is not None and (not isinstance(width, str) or width not in KNOWN_WIDTHS):
        errors.append(f"line {lineno}: unknown width key {width!r} (expected one of {list(KNOWN_WIDTHS)})")

    if "depth_mm" in entry:
        check_positive_number(lineno, "depth_mm", entry.get("depth_mm"), errors)
    if "weight_kg" in entry:
        check_positive_number(lineno, "weight_kg", entry.get("weight_kg"), errors)
    if "power_w" in entry:
        check_positive_number(lineno, "power_w", entry.get("power_w"), errors)

    mounting = entry.get("mounting")
    if mounting is not None and (not isinstance(mounting, str) or mounting not in KNOWN_MOUNTINGS):
        errors.append(f"line {lineno}: unknown mounting key {mounting!r} (expected one of {list(KNOWN_MOUNTINGS)})")

    source = entry.get("source")
    if source is not None:
        if not isinstance(source, str):
            errors.append(f"line {lineno}: 'source' must be a string")
        elif not URL_RE.fullmatch(source.strip()) or source != source.strip():
            errors.append(f"line {lineno}: 'source' must be an http(s) URL, got {source!r}")

    if "ports" in entry:
        ports = entry.get("ports")
        if isinstance(ports, _JsonObject) or not isinstance(ports, list):
            errors.append(f"line {lineno}: 'ports' must be an array")
        elif not ports:
            errors.append(f"line {lineno}: 'ports' must not be empty")
        elif not all(isinstance(p, str) for p in ports):
            errors.append(f"line {lineno}: 'ports' must contain only strings")
        elif any(not p.strip() or p != p.strip() for p in ports):
            errors.append(f"line {lineno}: 'ports' entries must be non-empty and trimmed")
        else:
            dupes = [p for p, n in Counter(ports).items() if n > 1]
            if dupes:
                errors.append(f"line {lineno}: duplicate entries in 'ports': {dupes}")

    for field in ("depth_mm", "power_w", "ports", "weight_kg"):
        if field in entry and entry.get(field) is None:
            errors.append(f"line {lineno}: omit '{field}' entirely instead of writing null")


def check_file(
    stem: str,
    entries: list[tuple[int, dict]],
    brands_ids: set[str] | None,
    errors: list[str],
) -> None:
    """Validate a device file's name and the properties that hold file-wide.

    `brands_ids` is None when no brands.jsonl could be loaded — every dangling
    reference check then degrades to a mention in the summary instead of a
    line-level error, so a missing brands file does not produce one error per
    record.
    """
    expected_filename = f"{stem}.jsonl"
    for lineno, entry in entries:
        brand = entry.get("brand")
        if isinstance(brand, str) and brand != stem:
            errors.append(
                f"line {lineno}: brand {brand!r} does not match the filename {expected_filename!r}"
            )
        if isinstance(brand, str) and brands_ids is not None and brand not in brands_ids:
            errors.append(f"line {lineno}: brand {brand!r} does not exist in brands.jsonl")

    ids: dict[str, int] = {}
    for lineno, entry in entries:
        device_id = entry.get("id")
        if not isinstance(device_id, str):
            continue
        if device_id in ids:
            errors.append(f"line {lineno}: duplicate id {device_id!r} (first seen on line {ids[device_id]})")
        else:
            ids[device_id] = lineno

    ordered = [entry for _, entry in entries if isinstance(entry.get("model"), str)]
    expected = sorted(ordered, key=lambda e: (sort_key(e["model"]), e.get("id", "")))
    if ordered != expected:
        for actual, want in zip(ordered, expected):
            if actual != want:
                errors.append(
                    f"sort order broken: expected {want.get('model')!r} where {actual.get('model')!r} is"
                )
                break


def collect_files(path: Path) -> list[Path]:
    """Return the device files to validate: a single file, or every .jsonl in a directory."""
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    return [path]


def load_brands_ids() -> tuple[set[str], list[str]]:
    """Load the brand ids from brands.jsonl; return (ids, load errors)."""
    if not DEFAULT_BRANDS_FILE.exists():
        return set(), [f"brands file {DEFAULT_BRANDS_FILE} does not exist"]

    try:
        raw = DEFAULT_BRANDS_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return set(), [f"brands file {DEFAULT_BRANDS_FILE} cannot be read: {exc}"]

    ids: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            ids.add(entry["id"])
    return ids, []


def _run(
    path: Path, brands_ids: set[str] | None, brands_errors: list[str]
) -> tuple[list[str], int, Counter]:
    """Validate every device file under `path`.

    Returns the errors, the device count and a counter of category keys, so a
    passing run can print a summary without re-reading the files.
    """
    if not path.exists():
        return [f"{path} does not exist"], 0, Counter()
    if path.is_dir():
        files = collect_files(path)
    elif path.suffix == ".jsonl":
        files = [path]
    else:
        return [f"{path} is not a .jsonl file or a directory"], 0, Counter()

    errors: list[str] = []
    total = 0
    categories: Counter = Counter()
    seen_ids: dict[str, Path] = {}

    for file in sorted(files):
        try:
            raw = file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{file.name} is not valid UTF-8: {exc}")
            continue
        except OSError as exc:
            errors.append(f"{file.name} cannot be read: {exc}")
            continue

        if not raw.strip():
            errors.append(f"{file.name} is empty")
            continue

        file_errors: list[str] = []
        entries = parse_lines(raw, file_errors)
        for lineno, entry in entries:
            check_entry(lineno, entry, file_errors)
        check_file(file.stem, entries, brands_ids, file_errors)

        if file_errors:
            errors.append(f"file {file.name}: {len(file_errors)} problem(s)")
        errors.extend(file_errors)

        if brands_errors:
            errors.append(f"file {file.name}: brand cross-check skipped — {'; '.join(brands_errors)}")

        for _, entry in entries:
            total += 1
            category = entry.get("category")
            if isinstance(category, str) and category in KNOWN_CATEGORIES:
                categories[category] += 1
            device_id = entry.get("id")
            if isinstance(device_id, str):
                if device_id in seen_ids and seen_ids[device_id] != file:
                    errors.append(
                        f"{file.name}: duplicate id {device_id!r}"
                        f" (first seen in {seen_ids[device_id].name})"
                    )
                else:
                    seen_ids[device_id] = file

    return errors, total, categories


def report(total: int, files: list[Path], categories: Counter) -> None:
    """Print a summary of a dataset that passed validation."""
    print(f"OK — {total} devices in {len(files)} file(s)")
    for category in KNOWN_CATEGORIES:
        print(f"  {category:<20} {categories[category]:>4}")


def validate(path: Path, brands_ids: set[str] | None = None, brands_errors: list[str] | None = None) -> list[str]:
    """Return every problem found under `path`. An empty list means the dataset is clean.

    With no brands context passed, the ids are loaded from the repository's
    brands.jsonl; when that file is missing, a cross-check warning is reported
    instead of a per-record brand error.
    """
    if brands_ids is None and brands_errors is None:
        brands_ids, brands_errors = load_brands_ids()
    errors, _, _ = _run(path, brands_ids, brands_errors or [])
    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_DEVICES_DIR

    if not path.exists():
        if path == DEFAULT_DEVICES_DIR:
            print(f"OK — no device files yet ({path} does not exist)")
            return 0
        print(f"FAIL — {path} does not exist", file=sys.stderr)
        return 1

    brands_ids, brands_errors = load_brands_ids()
    errors, total, categories = _run(path, brands_ids, brands_errors)
    if errors:
        print(f"FAIL — {len(errors)} problem(s) in {path.name}:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    report(total, collect_files(path), categories)
    return 0


if __name__ == "__main__":
    sys.exit(main())
