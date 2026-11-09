import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import sync_labels


class PlanSyncTests(unittest.TestCase):
    def setUp(self):
        self.wanted = [{"name": "area/app", "color": "1d76db", "description": "App"}]

    def test_creates_missing_label(self):
        self.assertEqual(sync_labels.plan_sync({}, self.wanted), [("create", self.wanted[0])])

    def test_updates_changed_color_or_description(self):
        existing = {"area/app": {"color": "ededed", "description": "App"}}
        self.assertEqual(sync_labels.plan_sync(existing, self.wanted), [("update", self.wanted[0])])
        existing = {"area/app": {"color": "1d76db", "description": None}}
        self.assertEqual(sync_labels.plan_sync(existing, self.wanted), [("update", self.wanted[0])])

    def test_unchanged_label_is_left_alone(self):
        existing = {"area/app": {"color": "1D76DB", "description": "App"}}
        self.assertEqual(sync_labels.plan_sync(existing, self.wanted), [])

    def test_name_match_is_case_insensitive_and_extra_labels_are_ignored(self):
        existing = {
            "Area/App": {"color": "1d76db", "description": "App"},
            "unrelated": {"color": "000000", "description": ""},
        }
        self.assertEqual(sync_labels.plan_sync(existing, self.wanted), [])


class ConfigTests(unittest.TestCase):
    def load(self):
        return json.loads((ROOT / ".github" / "labels.json").read_text(encoding="utf-8"))

    def test_shipped_config_is_valid(self):
        sync_labels.validate_config(self.load())

    def test_every_category_has_a_label(self):
        names = {label["name"] for label in self.load()["labels"]}
        for category in ("network", "audio_proav", "infrastructure_ups", "servers"):
            self.assertIn(f"cat/{category}", names)

    def test_rejects_duplicates_and_bad_colors(self):
        dup = {"labels": [{"name": "a", "color": "000000", "description": ""},
                          {"name": "A", "color": "000000", "description": ""}]}
        with self.assertRaises(ValueError):
            sync_labels.validate_config(dup)
        bad = {"labels": [{"name": "a", "color": "xyz", "description": ""}]}
        with self.assertRaises(ValueError):
            sync_labels.validate_config(bad)


if __name__ == "__main__":
    unittest.main()
