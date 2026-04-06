"""Compatibility entrypoint for ChatBuddy."""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from chatbuddy.main import main
from chatbuddy.runtime import bot

__all__ = ["bot", "main"]


if __name__ == "__main__":
    main()
