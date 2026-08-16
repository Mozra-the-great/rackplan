#!/usr/bin/env python3
"""Validate data/brands/brands.jsonl.

Checks syntax, schema, referential integrity of `parent`, and sort order.
Exits 0 when the dataset is clean, 1 otherwise. No third-party dependencies.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

DEFAULT_BRANDS_FILE = Path(__file__).resolve().parent.parent / "data" / "brands" / "brands.jsonl"

KNOWN_CATEGORIES = ("audio_proav", "infrastructure_ups", "network", "servers")
FIELD_ORDER = ("id", "name", "categories", "parent")
REQUIRED_FIELDS = ("id", "name", "categories")
# Matched with fullmatch, not match: `$` also matches just before a trailing
# newline, so "foo\n" would otherwise pass as a valid slug — and then count as a
# separate id from "foo", defeating the duplicate check too.
SLUG_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def sort_key(name: str) -> str:
    """Deterministic collation key: strip accents, then casefold.

    Plain `sorted()` on the raw name is locale- and case-sensitive, which would
    place "dbx", "3M" and "Ätna" differently across runs and platforms.
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


def check_entry(lineno: int, entry: dict, errors: list[str]) -> None:
    """Validate a single entry's fields in isolation."""
    unknown = [k for k in entry if k not in FIELD_ORDER]
    if unknown:
        errors.append(f"line {lineno}: unknown field(s) {unknown}")

    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"line {lineno}: missing required field '{field}'")

    brand_id = entry.get("id")
    if brand_id is not None:
        if not isinstance(brand_id, str):
            errors.append(f"line {lineno}: 'id' must be a string")
        elif not SLUG_RE.fullmatch(brand_id):
            errors.append(f"line {lineno}: id {brand_id!r} is not a valid slug")

    name = entry.get("name")
    if name is not None:
        if not isinstance(name, str):
            errors.append(f"line {lineno}: 'name' must be a string")
        elif not name.strip():
            errors.append(f"line {lineno}: 'name' is empty")
        elif name != name.strip():
            errors.append(f"line {lineno}: name {name!r} has leading/trailing whitespace")
        elif any(unicodedata.category(c) == "Cc" for c in name):
            errors.append(f"line {lineno}: name {name!r} contains control characters")

    categories = entry.get("categories")
    if categories is not None:
        # _JsonObject subclasses list, so a JSON object would pass a plain
        # isinstance check and produce a nonsense "unknown category key" error.
        if isinstance(categories, _JsonObject) or not isinstance(categories, list):
            errors.append(f"line {lineno}: 'categories' must be an array")
        elif not categories:
            errors.append(f"line {lineno}: 'categories' must not be empty")
        elif not all(isinstance(c, str) for c in categories):
            # Bail out before set()/sorted(), which raise on unhashable or
            # mixed-type elements instead of recording an error.
            errors.append(f"line {lineno}: 'categories' must contain only strings")
        else:
            unknown_cats = [c for c in categories if c not in KNOWN_CATEGORIES]
            if unknown_cats:
                errors.append(f"line {lineno}: unknown category key(s) {unknown_cats}")
            if len(categories) != len(set(categories)):
                errors.append(f"line {lineno}: duplicate entries in 'categories'")
            if categories != sorted(categories):
                errors.append(f"line {lineno}: 'categories' must be sorted alphabetically")

    parent = entry.get("parent")
    if parent is not None:
        if not isinstance(parent, str):
            errors.append(f"line {lineno}: 'parent' must be a string")
        elif not SLUG_RE.fullmatch(parent):
            errors.append(f"line {lineno}: parent {parent!r} is not a valid slug")
        elif parent == brand_id:
            errors.append(f"line {lineno}: {brand_id!r} references itself as parent")
    elif "parent" in entry:
        errors.append(f"line {lineno}: omit 'parent' entirely instead of writing null")


def check_dataset(entries: list[tuple[int, dict]], errors: list[str]) -> None:
    """Validate properties that only hold across the whole file."""
    ids: dict[str, int] = {}
    for lineno, entry in entries:
        brand_id = entry.get("id")
        if not isinstance(brand_id, str):
            continue
        if brand_id in ids:
            errors.append(f"line {lineno}: duplicate id {brand_id!r} (first seen on line {ids[brand_id]})")
        else:
            ids[brand_id] = lineno

    names: dict[str, int] = {}
    for lineno, entry in entries:
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        key = sort_key(name)
        if key in names:
            errors.append(f"line {lineno}: duplicate name {name!r} (first seen on line {names[key]})")
        else:
            names[key] = lineno

    # parent must resolve to a brand that exists in this same file
    parents: dict[str, str] = {}
    for lineno, entry in entries:
        parent = entry.get("parent")
        brand_id = entry.get("id")
        if not isinstance(parent, str) or not isinstance(brand_id, str):
            continue
        if parent not in ids:
            errors.append(f"line {lineno}: parent {parent!r} does not exist in the dataset")
        else:
            parents[brand_id] = parent

    # Walk each chain once and report a cycle by its actual members. Tracking
    # settled nodes globally keeps a shared cycle from being reported once per
    # brand pointing into it, and naming the members from the re-entry point
    # avoids blaming a node that merely leads into a cycle without being in one.
    settled: set[str] = set()
    reported: set[frozenset[str]] = set()
    for start in parents:
        if start in settled:
            continue
        path: list[str] = []
        cursor: str | None = start
        while cursor is not None and cursor not in settled:
            if cursor in path:
                members = path[path.index(cursor):]
                if frozenset(members) not in reported:
                    reported.add(frozenset(members))
                    errors.append(f"parent cycle: {' -> '.join(members)} -> {cursor}")
                break
            path.append(cursor)
            cursor = parents.get(cursor)
        settled.update(path)

    ordered = [entry for _, entry in entries if isinstance(entry.get("name"), str)]
    expected = sorted(ordered, key=lambda e: (sort_key(e["name"]), e.get("id", "")))
    if ordered != expected:
        for actual, want in zip(ordered, expected):
            if actual != want:
                errors.append(
                    f"sort order broken: expected {want.get('name')!r} where {actual.get('name')!r} is"
                )
                break


def report(entries: list[tuple[int, dict]], path: Path) -> None:
    """Print a summary of a dataset that passed validation."""
    counts = Counter(c for _, e in entries for c in e.get("categories", []))
    with_parent = sum(1 for _, e in entries if "parent" in e)
    multi = sum(1 for _, e in entries if len(e.get("categories", [])) > 1)

    print(f"OK — {len(entries)} brands in {path.name}")
    for category in KNOWN_CATEGORIES:
        print(f"  {category:<20} {counts[category]:>4}")
    print(f"  {'multi-category':<20} {multi:>4}")
    print(f"  {'with parent':<20} {with_parent:>4}")


def _run(path: Path) -> tuple[list[str], list[tuple[int, dict]]]:
    """Validate `path`, returning both the problems and the parsed entries."""
    if not path.exists():
        return [f"{path} does not exist"], []

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"{path} is not valid UTF-8: {exc}"], []
    except OSError as exc:
        return [f"{path} cannot be read: {exc}"], []

    if not raw.strip():
        return [f"{path} is empty"], []

    errors: list[str] = []
    entries = parse_lines(raw, errors)
    for lineno, entry in entries:
        check_entry(lineno, entry, errors)
    check_dataset(entries, errors)
    return errors, entries


def validate(path: Path) -> list[str]:
    """Return every problem found in `path`. An empty list means the file is clean."""
    return _run(path)[0]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_BRANDS_FILE

    errors, entries = _run(path)
    if errors:
        print(f"FAIL — {len(errors)} problem(s) in {path.name}:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    report(entries, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
