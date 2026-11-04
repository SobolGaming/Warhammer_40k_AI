from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(os.environ["EVENT_LAYOUT_AUDIT_WORK_DIR"])
REPO = Path(__file__).resolve().parents[2]
OLD = REPO / "docs/source_rules/eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"
NEW = REPO / "docs/source_rules/eng_14-10_wh40k_event_companion-rdwnqprl4c-nj8oqogadv.pdf"
REFERENCE = REPO / (
    "data/source_audits/event_companion_2026_06/phase17n_event_companion_ba"
    "ttlefields_pages_9_53_extraction.json"
)
REF = json.loads(REFERENCE.read_text())
