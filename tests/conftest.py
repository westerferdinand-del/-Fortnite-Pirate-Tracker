import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Les tests n'écrivent jamais dans les vraies données de l'utilisateur
os.environ.setdefault("PIRATE_TRACKER_HOME", tempfile.mkdtemp(prefix="pt_test_"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
