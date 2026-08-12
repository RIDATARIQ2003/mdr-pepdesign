from pathlib import Path

# This file lives at mdr-pepdesign/dashboard/utils/paths.py, so ROOT needs
# to go up THREE levels (utils -> dashboard -> mdr-pepdesign), not two.
# The old version only went up two levels and landed on dashboard/ itself,
# which silently pointed DATA_DIR/DOCKING_DIR/etc. one folder too deep.
ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = ROOT / "data"

DOCKING_DIR = ROOT / "docking"

DASHBOARD_DIR = ROOT / "dashboard"

COMPLEX_DIR = DATA_DIR / "complex_top20"

FOLDED_DIR = DATA_DIR / "folded"