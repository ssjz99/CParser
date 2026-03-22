"""Validation tests for searchCStruct."""

from __future__ import annotations

import unittest
from pathlib import Path

from searchCStruct import searchCStruct


class TestSearchCStruct(unittest.TestCase):
    """Test coverage for searchCStruct requirements."""

    def setUp(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.src_dir = self.base_dir / "src"

    def test_ifdef_wrapped_fields(self) -> None:
        results = searchCStruct(
            src_path=str(self.src_dir),
            target_list=["Config", "Device"],
            include_path_list=[str(self.src_dir)],
            log_dir=str(self.base_dir),
        )

        self.assertGreaterEqual(len(results), 2)

        by_name = {item["name"]: item for item in results}
        self.assertIn("Config", by_name)
        self.assertIn("Device", by_name)

        config_members = {m["name"] for m in by_name["Config"]["members"]}
        self.assertIn("version", config_members)
        self.assertIn("timeout", config_members)

        device_members = {m["name"] for m in by_name["Device"]["members"]}
        self.assertIn("device_id", device_members)
        self.assertIn("device_name", device_members)

        self.assertGreater(by_name["Config"]["line"], 0)
        self.assertGreater(by_name["Config"]["column"], 0)
        self.assertIn("struct Config", by_name["Config"]["definition"])

    def test_invalid_path(self) -> None:
        results = searchCStruct(
            src_path=str(self.base_dir / "does_not_exist"),
            target_list=["Config"],
            include_path_list=[str(self.src_dir)],
            log_dir=str(self.base_dir),
        )
        self.assertEqual(results, [])

    def test_empty_target_list(self) -> None:
        results = searchCStruct(
            src_path=str(self.src_dir),
            target_list=[],
            include_path_list=[str(self.src_dir)],
            log_dir=str(self.base_dir),
        )
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
