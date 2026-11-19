"""Run the focused session and memory checks with ``python backend/test.py``."""

import unittest
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from tests.test_chat_memory import ChatMemoryTests


if __name__ == "__main__":
    unittest.main()
