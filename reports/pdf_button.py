"""
Trigger quick PDF generation locally (opens default viewer).

Run from project root::

    cd forex_regime
    python reports/pdf_button.py
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from reports.pdf_generator import generate_report  # noqa: E402


def open_pdf(path: str) -> None:
    if platform.system() == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def click_generate_pdf() -> dict:
    """Single entry: build PDF from ``state/*.json`` (+ optional trades log) and open it."""
    print("Generating PDF report...")
    try:
        path = generate_report()
        print(f"PDF ready: {path}")
        open_pdf(path)
        return {"success": True, "path": path}
    except Exception as e:
        print(f"PDF failed: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = click_generate_pdf()
    if result["success"]:
        print(f"Opened: {result['path']}")
    else:
        print(f"Error: {result['error']}")
