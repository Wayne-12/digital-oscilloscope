"""Launch the scope UI without putting Unicode filenames in a batch file."""

from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    runpy.run_path(str(root / "scope_ui.py"), run_name="__main__")
