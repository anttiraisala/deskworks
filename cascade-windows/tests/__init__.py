"""Tests for cascade-windows.

The shared `deskmap` library lives next to this project in the repository; make it importable
when it is not installed.
"""

import os
import sys

_DESKMAP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "deskmap", "src")
if os.path.isdir(_DESKMAP) and _DESKMAP not in sys.path:
    sys.path.insert(0, _DESKMAP)
