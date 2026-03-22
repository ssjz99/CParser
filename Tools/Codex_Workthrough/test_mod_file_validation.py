"""Validation tests for `.mod` generation behavior."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from carryOverCProcessor import carryOverCProcessor
from searchCStruct import searchCStruct


class TestModFileValidation(unittest.TestCase):
    """Verify .mod creation and original file preservation."""

    def setUp(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.src_dir = self.base_dir / "src"
        self.source_file = self.src_dir / "example.c"
        self.mod_file = self.src_dir / "example.c.mod"
        if self.mod_file.exists():
            self.mod_file.unlink()

    def _digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_mod_generation_and_preservation(self) -> None:
        before_hash = self._digest(self.source_file)

        structs = searchCStruct(
            src_path=str(self.src_dir),
            target_list=["Config", "Device","SensorData","RobotSystem"],
            include_path_list=[str(self.src_dir)],
            log_dir=str(self.base_dir),
        )
        result = carryOverCProcessor(structs, log_dir=str(self.base_dir))

        self.assertTrue(result["success"])
        self.assertIn(str(self.source_file.resolve()), result["processed_files"])
        self.assertGreaterEqual(result["total_variables"], 1)
        self.assertTrue(self.mod_file.exists())

        after_hash = self._digest(self.source_file)
        self.assertEqual(before_hash, after_hash)

        mod_content = self.mod_file.read_text(encoding="utf-8")
        self.assertIn("struct Config app_config = {", mod_content)
        self.assertIn("#ifdef DEBUG_MODE", mod_content)
        self.assertIn("#ifdef ENABLE_LOGGING", mod_content)
        self.assertIn("#ifdef ENABLE_DEVICE_EXTENDED", mod_content)
        self.assertIn("struct RobotSystem myBot = {", mod_content)
        self.assertIn("#ifdef SENSOR_READINGS_ENABLED", mod_content)


if __name__ == "__main__":
    unittest.main()
