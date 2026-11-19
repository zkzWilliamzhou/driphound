"""Minimal unittest runner: python3 tests/runner.py [pattern]"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else "test_*.py"
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern=pattern, top_level_dir=str(ROOT))
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
