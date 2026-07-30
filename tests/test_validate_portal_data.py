from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from validate_portal_data import contains_absolute_workstation_path


def test_editorial_windows_system_path_is_allowed() -> None:
    payload = {
        "collections": {
            "news": [
                {
                    "summary": (
                        "Windows 11 installs "
                        r"C:\Program Files\Microsoft OneDrive\OneDrive.exe"
                    )
                }
            ]
        }
    }

    assert not contains_absolute_workstation_path(payload)


def test_windows_user_home_path_is_rejected() -> None:
    payload = {
        "collections": {
            "news": [{"summary": r"debug artifact: C:\Users\alice\private.json"}]
        }
    }

    assert contains_absolute_workstation_path(payload)


def test_macos_user_home_path_is_rejected() -> None:
    payload = {"buildMeta": {"sourcePath": "/Users/mac/private/source.json"}}

    assert contains_absolute_workstation_path(payload)
