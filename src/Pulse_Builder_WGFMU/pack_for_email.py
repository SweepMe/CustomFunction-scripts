"""
pack_for_email.py — Package the WGFMU Pulse Builder for sending by e-mail.

Copies all relevant files from this folder, renames .py → .txt so mail
providers don't block them, and writes a timestamped .zip file to the
Desktop (or a custom output directory).

Usage:
    python pack_for_email.py              # zip lands on Desktop
    python pack_for_email.py C:\Temp      # zip lands in C:\Temp
"""

import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Root of the driver folder (the folder that contains this script)
SOURCE_DIR = Path(__file__).parent

# Files/folders to exclude from the zip
EXCLUDE = {
    "__pycache__",
    "pack_for_email.py",    # don't include this helper script itself
}

# Output directory — Desktop by default, overridable via CLI argument
if len(sys.argv) > 1:
    OUTPUT_DIR = Path(sys.argv[1])
else:
    OUTPUT_DIR = Path.home() / "Desktop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_include(path: Path) -> bool:
    """Return True if the file/dir should be included in the zip."""
    for part in path.parts:
        if part in EXCLUDE:
            return False
    return True


def _zip_name() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"Pulse_Builder_WGFMU_{timestamp}.zip"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUTPUT_DIR / _zip_name()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp) / SOURCE_DIR.name

        # Copy the whole tree into a temp directory, applying exclusions
        for src_file in SOURCE_DIR.rglob("*"):
            rel = src_file.relative_to(SOURCE_DIR)
            if not _should_include(rel):
                continue
            if src_file.is_dir():
                continue

            dst_file = tmp_root / rel
            # Rename .py → .txt
            if dst_file.suffix == ".py":
                dst_file = dst_file.with_suffix(".txt")

            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)

        # Zip the temp tree
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(tmp_root.rglob("*")):
                if file.is_file():
                    zf.write(file, file.relative_to(tmp))

    print(f"Created: {zip_path}")


if __name__ == "__main__":
    main()
