"""Tests for scripts/validate_devices.py.

Uses only the standard library (unittest + tempfile). The module under test is
loaded directly from its file path so no package __init__.py is required
anywhere in the repo.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_devices.py"

_spec = importlib.util.spec_from_file_location("validate_devices", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
vd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vd)


def _device(
    device_id: str = "sg-3100",
    model: str = "SG-3100",
    **overrides: object,
) -> dict:
    """Build a minimal, valid device record; overrides patch single fields.

    Keys are re-emitted in the validator's FIELD_ORDER; unknown override keys
    used by negative tests are appended last so fixtures stay dumpable.
    """
    entry: dict = {
        "id": device_id,
        "brand": "netgate",
        "model": model,
        "category": "network",
        "height_u": 1,
        "width": "half",
        "mounting": "rack-ears",
        "source": "https://www.netgate.com/assets/sg-3100-datasheet.pdf",
    }
    entry.update(overrides)
    # Re-emit keys in the validator's FIELD_ORDER; unknown override keys used
    # by negative tests are appended last so they stay dumpable directly.
    ordered = {f: entry[f] for f in vd.FIELD_ORDER if f in entry}
    ordered.update({k: v for k, v in entry.items() if k not in ordered})
    return ordered


def _dump(entry: dict) -> str:
    return json.dumps(entry, separators=(", ", ": "))


VALID_ENTRIES = [
    _device(),  # SG-3100 sorts before XG-7100 by (sort_key(model), id)
    _device(
        device_id="xg-7100",
        model="XG-7100",
        category="network",
        height_u=1,
        width="full",
        depth_mm=439,
        weight_kg=4.2,
        power_w=30,
        ports=["8x RJ45 1GbE", "2x SFP+"],
    ),
]

def valid_content() -> str:
    lines = [_dump(entry) for entry in sorted(VALID_ENTRIES, key=lambda e: (vd.sort_key(e["model"]), e["id"]))]
    return "\n".join(lines) + "\n"


class DevicesFixtureTestCase(unittest.TestCase):
    """Base class providing helpers for temporary brand/device fixtures."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)

    def write_file(self, content: str, name: str = "netgate.jsonl") -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def write_tree(self, device_content: str, brand_lines: list[str] | None = None, name: str = "netgate.jsonl") -> Path:
        """Create tmproot/data/{brands,devices}/ and return the devices file path."""
        brands = self.root / "data" / "brands"
        devices = self.root / "data" / "devices"
        brands.mkdir(parents=True)
        devices.mkdir(parents=True)
        brand_names = brand_lines if brand_lines is not None else [
            _dump({"id": "netgate", "name": "Netgate", "categories": ["network"]}),
        ]
        (brands / "brands.jsonl").write_text("\n".join(brand_names) + "\n", encoding="utf-8")
        path = devices / name
        path.write_text(device_content, encoding="utf-8")
        return path

    def assert_error_mentioning(self, errors: list[str], needle: str) -> None:
        self.assertTrue(errors, "expected at least one error, got none")
        self.assertTrue(
            any(needle in e for e in errors),
            f"expected an error mentioning {needle!r}, got: {errors}",
        )


class ValidDatasetTests(DevicesFixtureTestCase):
    def test_valid_dataset_passes(self) -> None:
        path = self.write_file(valid_content())
        self.assertEqual(vd.validate(path, brands_ids={"netgate"}, brands_errors=[]), [])

    def test_valid_file_via_default_brands_context(self) -> None:
        path = self.write_tree(valid_content())
        # Point the loader at the fixture tree for the duration of the call.
        original = vd.DEFAULT_BRANDS_FILE
        vd.DEFAULT_BRANDS_FILE = self.root / "data" / "brands" / "brands.jsonl"
        try:
            self.assertEqual(vd.validate(path), [])
        finally:
            vd.DEFAULT_BRANDS_FILE = original

    def test_missing_devices_dir_default_is_clean(self) -> None:
        original = vd.DEFAULT_DEVICES_DIR
        vd.DEFAULT_DEVICES_DIR = self.root / "data" / "devices"
        try:
            self.assertEqual(vd.main([]), 0)
        finally:
            vd.DEFAULT_DEVICES_DIR = original

    def test_directory_mode_validates_every_file(self) -> None:
        devices = self.root / "data" / "devices"
        devices.mkdir(parents=True)
        (devices / "netgate.jsonl").write_text(valid_content(), encoding="utf-8")
        other = _device(device_id="other-model", model="Other Model", brand="otherinc")
        (devices / "otherinc.jsonl").write_text(_dump(other) + "\n", encoding="utf-8")
        self.assertEqual(vd.validate(devices, brands_ids={"netgate", "otherinc"}, brands_errors=[]), [])

    def test_duplicate_id_across_files(self) -> None:
        devices = self.root / "data" / "devices"
        devices.mkdir(parents=True)
        (devices / "netgate.jsonl").write_text(valid_content(), encoding="utf-8")
        other = _device(device_id="sg-3100", model="Model B", brand="otherinc")
        (devices / "otherinc.jsonl").write_text(_dump(other) + "\n", encoding="utf-8")
        errors = vd.validate(devices, brands_ids={"netgate", "otherinc"}, brands_errors=[])
        self.assert_error_mentioning(errors, "first seen in netgate.jsonl")

    def test_missing_explicit_path_fails(self) -> None:
        errors, _, _ = vd._run(self.root / "nope.jsonl", {"netgate"}, [])
        self.assertTrue(errors)


class ParseLinesTests(DevicesFixtureTestCase):
    def test_missing_trailing_newline(self) -> None:
        path = self.write_file(valid_content().rstrip("\n"))
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "does not end with a newline")

    def test_empty_line(self) -> None:
        content = valid_content() + "\n"
        path = self.write_file(content)
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "empty line")

    def test_leading_whitespace(self) -> None:
        content = "\n".join("    " + line for line in valid_content().splitlines())
        path = self.write_file(content + "\n")
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "leading or trailing whitespace")

    def test_invalid_json(self) -> None:
        path = self.write_file('{"id": "sg-3100"\n')
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "invalid JSON")

    def test_array_line(self) -> None:
        path = self.write_file('["sg-3100"]\n')
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "expected a JSON object")

    def test_duplicate_object_keys(self) -> None:
        line = '{"id": "sg-3100", "id": "other", "brand": "netgate", "model": "SG-3100", "category": "network", "height_u": 1, "width": "half", "mounting": "rack-ears", "source": "https://example.com/x.pdf"}'
        path = self.write_file(line + "\n")
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "duplicate keys")

    def test_field_order(self) -> None:
        lines = [
            _dump(_device()),
            '{"brand": "netgate", "id": "xg-7100", "model": "XG-7100", "category": "network", "height_u": 1, "width": "full", "mounting": "rack-ears", "source": "https://example.com/xg.pdf"}',
        ]
        path = self.write_file("\n".join(lines) + "\n")
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "field order")


class EntryFieldTests(DevicesFixtureTestCase):
    def entry_errors(self, **overrides: object) -> list[str]:
        entry = _device(**overrides)
        return vd.validate(self.write_file(_dump(entry) + "\n"), {"netgate"}, [])

    def test_missing_required_fields(self) -> None:
        entry = _device()
        for field in ("id", "brand", "model", "category", "width", "mounting", "source"):
            del entry[field]
        errors = vd.validate(self.write_file(_dump(entry) + "\n"), {"netgate"}, [])
        for field in ("id", "brand", "model", "category", "width", "mounting", "source"):
            self.assert_error_mentioning(errors, f"missing required field '{field}'")

    def test_unknown_field(self) -> None:
        self.assert_error_mentioning(self.entry_errors(rack_units=2), "unknown field")

    def test_bad_id_slug(self) -> None:
        self.assert_error_mentioning(self.entry_errors(device_id="SG_3100"), "not a valid slug")

    def test_bad_brand_slug(self) -> None:
        self.assert_error_mentioning(self.entry_errors(brand="Netgate Inc."), "not a valid slug")

    def test_empty_model(self) -> None:
        self.assert_error_mentioning(self.entry_errors(model="   "), "is empty")

    def test_control_character_in_model(self) -> None:
        self.assert_error_mentioning(self.entry_errors(model="SG\x0c3100"), "control characters")

    def test_unknown_category(self) -> None:
        self.assert_error_mentioning(self.entry_errors(category="cooling"), "not a known category")

    def test_height_u_must_be_integer(self) -> None:
        self.assert_error_mentioning(self.entry_errors(height_u=1.5), "must be an integer")

    def test_height_u_boolean_rejected(self) -> None:
        self.assert_error_mentioning(self.entry_errors(height_u=True), "must be an integer")

    def test_negative_height_u(self) -> None:
        self.assert_error_mentioning(self.entry_errors(height_u=-1), "must not be negative")

    def test_zero_height_u_requires_0u_mounting(self) -> None:
        self.assert_error_mentioning(self.entry_errors(height_u=0, mounting="rack-ears"), "only allowed with mounting '0U'")

    def test_zero_height_u_with_0u_mounting_passes(self) -> None:
        pdu = _device(
            device_id="rm2fr",
            model="RM2FR",
            category="infrastructure_ups",
            height_u=0,
            width="full",
            mounting="0U",
            source="https://example.com/rm2fr.pdf",
        )
        path = self.write_file(_dump(pdu) + "\n")
        self.assertEqual(vd.validate(path, {"netgate"}, []), [])

    def test_unknown_width(self) -> None:
        self.assert_error_mentioning(self.entry_errors(width="quarter"), "unknown width")

    def test_depth_mm_zero_rejected(self) -> None:
        self.assert_error_mentioning(self.entry_errors(depth_mm=0), "must be positive")

    def test_weight_kg_negative_rejected(self) -> None:
        self.assert_error_mentioning(self.entry_errors(weight_kg=-2.5), "must be positive")

    def test_power_w_string_rejected(self) -> None:
        self.assert_error_mentioning(self.entry_errors(power_w="30"), "must be a number")

    def test_power_w_bool_rejected(self) -> None:
        self.assert_error_mentioning(self.entry_errors(power_w=True), "must be a number")

    def test_power_w_infinite_rejected(self) -> None:
        path = self.write_file(_dump(_device(power_w=1e999)) + "\n")
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "must be finite")

    def test_unknown_mounting(self) -> None:
        self.assert_error_mentioning(self.entry_errors(mounting="magnetic"), "unknown mounting")

    def test_source_not_a_url(self) -> None:
        self.assert_error_mentioning(self.entry_errors(source="netgate.com/datasheet"), "http(s) URL")

    def test_source_with_newline_rejected(self) -> None:
        entry = _device(source="https://example.com/a\nb")
        path = self.write_file(_dump(entry) + "\n")
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "http(s) URL")

    def test_ftp_source_rejected(self) -> None:
        self.assert_error_mentioning(self.entry_errors(source="ftp://example.com/ds.pdf"), "http(s) URL")

    def test_ports_not_a_list(self) -> None:
        self.assert_error_mentioning(self.entry_errors(ports="1x RJ45"), "'ports' must be an array")

    def test_ports_empty_list(self) -> None:
        self.assert_error_mentioning(self.entry_errors(ports=[]), "must not be empty")

    def test_ports_with_number(self) -> None:
        self.assert_error_mentioning(self.entry_errors(ports=[8]), "must contain only strings")

    def test_ports_duplicate(self) -> None:
        ports = ["8x RJ45 1GbE", "8x RJ45 1GbE"]
        self.assert_error_mentioning(self.entry_errors(ports=ports), "duplicate entries in 'ports'")

    def test_ports_untrimmed(self) -> None:
        self.assert_error_mentioning(self.entry_errors(ports=[" x "]), "non-empty and trimmed")

    def test_null_optional_field(self) -> None:
        self.assert_error_mentioning(self.entry_errors(depth_mm=None), "instead of writing null")


class FileLevelTests(DevicesFixtureTestCase):
    def test_brand_missing_from_brands_jsonl(self) -> None:
        self.assert_error_mentioning(
            vd.validate(self.write_file(valid_content()), {"otherinc"}, []),
            "does not exist in brands.jsonl",
        )

    def test_brand_differs_from_filename(self) -> None:
        self.assert_error_mentioning(
            vd.validate(self.write_file(valid_content(), name="netgear.jsonl"), {"netgate"}, []),
            "does not match the filename",
        )

    def test_missing_brands_file_skips_cross_check(self) -> None:
        # brands_errors non-empty simulates an unloadable brands.jsonl: the
        # validator warns once instead of failing every record as dangling.
        errors, _, _ = vd._run(self.write_file(valid_content()), None, ["brands.jsonl does not exist"])
        self.assertTrue(any("cross-check skipped" in e for e in errors))
        self.assertFalse(any("does not exist in brands.jsonl" in e for e in errors))

    def test_duplicate_id_in_one_file(self) -> None:
        lines = [_dump(_device()), _dump(_device(model="SG-3100 (v2)"))]
        path = self.write_file("\n".join(lines) + "\n")
        errors, _, _ = vd._run(path, {"netgate"}, [])
        self.assert_error_mentioning(errors, "duplicate id 'sg-3100'")

    def test_wrong_sort_order(self) -> None:
        lines = [_dump(e) for e in VALID_ENTRIES]
        # SG-3100 sorts before XG-7100; swap them.
        path = self.write_file("\n".join(reversed(lines)) + "\n")
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "sort order broken")

    def test_empty_file(self) -> None:
        errors, _, _ = vd._run(self.write_file(""), {"netgate"}, [])
        self.assert_error_mentioning(errors, "is empty")

    def test_non_utf8_file(self) -> None:
        path = self.root / "netgate.jsonl"
        path.write_bytes(b'{"id": "\xff\xfe"}\n')
        self.assert_error_mentioning(vd.validate(path, {"netgate"}, []), "not valid UTF-8")

    def test_directory_counts_devices(self) -> None:
        devices = self.root / "data" / "devices"
        devices.mkdir(parents=True)
        (devices / "netgate.jsonl").write_text(valid_content(), encoding="utf-8")
        _, total, categories = vd._run(devices, {"netgate"}, [])
        self.assertEqual(total, len(VALID_ENTRIES))
        self.assertEqual(categories["network"], len(VALID_ENTRIES))


class MainTests(DevicesFixtureTestCase):
    """main() writes to stdout/stderr; capture with redirect stand-ins."""

    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = vd.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_missing_explicit_path_exits_1(self) -> None:
        code, _, _ = self.run_main([str(self.root / "nope.jsonl")])
        self.assertEqual(code, 1)

    def test_valid_dataset_exits_0(self) -> None:
        path = self.write_file(valid_content())
        # Isolate main() from the repository's real brands.jsonl.
        brands = self.root / "brands.jsonl"
        brands.write_text(
            _dump({"id": "netgate", "name": "Netgate", "categories": ["network"]}) + "\n",
            encoding="utf-8",
        )
        original = vd.DEFAULT_BRANDS_FILE
        vd.DEFAULT_BRANDS_FILE = brands
        try:
            code, out, _ = self.run_main([str(path)])
        finally:
            vd.DEFAULT_BRANDS_FILE = original
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_invalid_dataset_exits_1(self) -> None:
        lines = [_dump(e) for e in reversed(VALID_ENTRIES)]
        path = self.write_file("\n".join(lines) + "\n")
        code, _, err = self.run_main([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", err)
