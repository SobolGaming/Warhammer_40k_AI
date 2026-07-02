from __future__ import annotations

import re

WEAPON_PROFILE_SUFFIX_RE = re.compile(r"^(?P<base>.+?)\s+-\s+(?P<profile>.+)$")
