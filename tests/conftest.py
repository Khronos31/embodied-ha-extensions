from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "embodied_ha_extensions"
sys.path.insert(0, str(ADDON))
