import sys
from pathlib import Path

# Make the skill repo root importable so tests can `from bootstrap_lib...`
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))
