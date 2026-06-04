from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
repository_root_path = str(REPOSITORY_ROOT)
if repository_root_path not in sys.path:
    sys.path.insert(0, repository_root_path)
