"""Tests for scripts/validate_brands.py.

Uses only the standard library (unittest + tempfile). The module under test is
loaded directly from its file path so no package __init__.py is required
anywhere in the repo.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_brands.py"

_spec = importlib.util.spec_from_file_location("validate_brands", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
vb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb)


# A minimal, deliberately valid four-brand dataset: one parent/child pair, one
# multi-category brand, and correct global sort order (by sort_key(name)).
VALID_LINES = [
    '{"id": "apc", "name": "APC", "categories": ["infrastructure_ups"], "parent": "schneider-electric"}',
    '{"id": "dbx", "name": "dbx", "categories": ["audio_proav"]}',
    '{"id": "dell-technologies", "name": "Dell Technologies", "categories": ["network", "servers"]}',
    '{"id": "schneider-electric", "name": "Schneider Electric", "categories": ["infrastructure_ups"]}',
]


def valid_content() -> str:
    return "\n".join(VALID_LINES) + "\n"


class BrandsFixtureTestCase(unittest.TestCase):
    """Base class providing a helper to write a temporary .jsonl fixture."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

    def write(self, content: str, name: str = "brands.jsonl") -> Path:
        path = Path(self._tmpdir.name) / name
        path.write_text(content, encoding="utf-8")
        return path

    def assert_error_mentioning(self, errors: list[str], needle: str) -> None:
        self.assertTrue(errors, "expected at least one error, got none")
        self.assertTrue(
            any(needle in e for e in errors),
            f"expected an error mentioning {needle!r}, got: {errors}",
        )


class ValidDatasetTests(BrandsFixtureTestCase):
    def test_valid_dataset_has_no_errors(self) -> None:
        path = self.write(valid_content())
        self.assertEqual(vb.validate(path), [])


class DuplicateTests(BrandsFixtureTestCase):
    def test_duplicate_id_is_caught(self) -> None:
        lines = list(VALID_LINES)
        # Reuse "dbx" as the id of the last (independent, unrelated) entry.
        lines[3] = lines[3].replace('"schneider-electric"', '"dbx"', 1)
        # Fix the sort key collision this would otherwise create by renaming.
        content = "\n".join(lines) + "\n"
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "duplicate id")
        self.assert_error_mentioning(errors, "'dbx'")

    def test_duplicate_name_case_insensitive_is_caught(self) -> None:
        content = (
            '{"id": "mikrotik", "name": "MikroTik", "categories": ["network"]}\n'
            '{"id": "mikrotik-2", "name": "Mikrotik", "categories": ["network"]}\n'
        )
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "duplicate name")


class SlugFormatTests(BrandsFixtureTestCase):
    def _check_bad_id(self, bad_id: str) -> None:
        content = (
            '{"id": ' + repr(bad_id).replace("'", '"') + ', "name": "X", "categories": ["network"]}\n'
        )
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "valid slug")

    def test_uppercase_slug_is_rejected(self) -> None:
        self._check_bad_id("FooBar")

    def test_underscore_slug_is_rejected(self) -> None:
        self._check_bad_id("foo_bar")

    def test_leading_hyphen_slug_is_rejected(self) -> None:
        self._check_bad_id("-foobar")

    def test_trailing_hyphen_slug_is_rejected(self) -> None:
        self._check_bad_id("foobar-")

    def test_double_hyphen_slug_is_rejected(self) -> None:
        self._check_bad_id("foo--bar")

    def test_dotted_slug_is_rejected(self) -> None:
        self._check_bad_id("fs.com")

    def test_empty_slug_is_rejected(self) -> None:
        content = '{"id": "", "name": "X", "categories": ["network"]}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "valid slug")


class CategoryTests(BrandsFixtureTestCase):
    def test_unknown_category_key_is_caught(self) -> None:
        content = '{"id": "foo", "name": "Foo", "categories": ["not_a_real_category"]}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "unknown category")

    def test_empty_categories_array_is_caught(self) -> None:
        content = '{"id": "foo", "name": "Foo", "categories": []}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "must not be empty")

    def test_unsorted_categories_is_caught(self) -> None:
        content = '{"id": "foo", "name": "Foo", "categories": ["network", "audio_proav"]}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "sorted alphabetically")

    def test_duplicate_categories_is_caught(self) -> None:
        content = '{"id": "foo", "name": "Foo", "categories": ["network", "network"]}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "duplicate entries in 'categories'")


class ParentTests(BrandsFixtureTestCase):
    def test_parent_pointing_at_nonexistent_id_is_caught(self) -> None:
        content = '{"id": "foo", "name": "Foo", "categories": ["network"], "parent": "ghost"}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "does not exist")

    def test_self_referencing_parent_is_caught(self) -> None:
        content = '{"id": "foo", "name": "Foo", "categories": ["network"], "parent": "foo"}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "references itself")

    def test_parent_cycle_of_two_is_caught_and_terminates(self) -> None:
        content = (
            '{"id": "a", "name": "A", "categories": ["network"], "parent": "b"}\n'
            '{"id": "b", "name": "B", "categories": ["network"], "parent": "a"}\n'
        )
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "cycle")

    def test_parent_cycle_of_three_is_caught_and_terminates(self) -> None:
        content = (
            '{"id": "a", "name": "A", "categories": ["network"], "parent": "b"}\n'
            '{"id": "b", "name": "B", "categories": ["network"], "parent": "c"}\n'
            '{"id": "c", "name": "C", "categories": ["network"], "parent": "a"}\n'
        )
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "cycle")

    def test_parent_null_is_rejected(self) -> None:
        content = '{"id": "foo", "name": "Foo", "categories": ["network"], "parent": null}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "omit 'parent'")


class SchemaTests(BrandsFixtureTestCase):
    def test_unknown_extra_field_is_caught(self) -> None:
        content = (
            '{"id": "foo", "name": "Foo", "categories": ["network"], "website": "https://foo.example"}\n'
        )
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "unknown field")

    def test_missing_required_field_is_caught(self) -> None:
        content = '{"id": "foo", "categories": ["network"]}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "missing required field")

    def test_wrong_field_order_is_caught(self) -> None:
        content = '{"name": "Foo", "id": "foo", "categories": ["network"]}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "field order")


class LineLevelTests(BrandsFixtureTestCase):
    def test_malformed_json_on_one_line_is_caught_and_does_not_crash(self) -> None:
        content = (
            '{"id": "foo", "name": "Foo", "categories": ["network"]}\n'
            '{"id": "bar", "name": "Bar", "categories": ["network"],}\n'  # trailing comma
        )
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "line 2")
        self.assert_error_mentioning(errors, "invalid JSON")

    def test_line_with_pure_json_array_does_not_crash(self) -> None:
        """Known validator bug: a syntactically valid JSON array (not an object)
        on a line crashes parse_lines with an unhandled TypeError instead of
        being reported as a normal validation error. This test documents the
        desired behaviour and is expected to fail until the validator guards
        against non-object JSON values before unpacking key/value pairs.
        """
        content = (
            '{"id": "foo", "name": "Foo", "categories": ["network"]}\n'
            "[1, 2, 3]\n"
        )
        try:
            errors = vb.validate(self.write(content))
        except Exception as exc:  # noqa: BLE001 - we want to see any crash, not just TypeError
            self.fail(
                f"validate() crashed on a non-object JSON line instead of "
                f"reporting an error: {type(exc).__name__}: {exc}"
            )
        self.assert_error_mentioning(errors, "line 2")

    def test_empty_line_inside_file_is_caught(self) -> None:
        content = (
            '{"id": "foo", "name": "Foo", "categories": ["network"]}\n'
            "\n"
            '{"id": "bar", "name": "Bar", "categories": ["network"]}\n'
        )
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "line 2")
        self.assert_error_mentioning(errors, "empty line")

    def test_leading_trailing_whitespace_on_line_is_caught(self) -> None:
        content = '  {"id": "foo", "name": "Foo", "categories": ["network"]}\n'
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "whitespace")

    def test_file_not_ending_in_newline_is_caught(self) -> None:
        content = valid_content().rstrip("\n")
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "does not end with a newline")


class SortOrderTests(BrandsFixtureTestCase):
    def test_broken_sort_order_is_caught(self) -> None:
        # Swap the first two lines of the valid fixture (apc/dbx), breaking order.
        lines = list(VALID_LINES)
        lines[0], lines[1] = lines[1], lines[0]
        content = "\n".join(lines) + "\n"
        errors = vb.validate(self.write(content))
        self.assert_error_mentioning(errors, "sort order")


class SortKeyTests(unittest.TestCase):
    def test_accents_are_stripped(self) -> None:
        self.assertEqual(vb.sort_key("Ätna"), "atna")

    def test_casefolded(self) -> None:
        self.assertEqual(vb.sort_key("dbx"), vb.sort_key("DBX"))

    def test_digits_sort_before_letters(self) -> None:
        self.assertLess(vb.sort_key("3M"), vb.sort_key("ABB"))


class PathLevelTests(BrandsFixtureTestCase):
    def test_nonexistent_path_produces_error_not_crash(self) -> None:
        missing = Path(self._tmpdir.name) / "does-not-exist.jsonl"
        errors = vb.validate(missing)
        self.assert_error_mentioning(errors, "does not exist")

    def test_empty_file_produces_error_not_crash(self) -> None:
        errors = vb.validate(self.write(""))
        self.assert_error_mentioning(errors, "is empty")


class MainTests(BrandsFixtureTestCase):
    def test_main_returns_zero_on_clean_file(self) -> None:
        path = self.write(valid_content())
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = vb.main([str(path)])
        self.assertEqual(code, 0)

    def test_main_returns_one_on_dirty_file(self) -> None:
        path = self.write('{"id": "Bad_ID", "name": "X", "categories": ["network"]}\n')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = vb.main([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
