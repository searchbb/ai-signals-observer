from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import publish_portal_site


def test_sync_failure_exposes_nested_validator_error(monkeypatch) -> None:
    nested_error = "public payload contains an absolute workstation path"

    monkeypatch.setattr(
        publish_portal_site.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr=nested_error,
        ),
    )

    with pytest.raises(RuntimeError, match=nested_error):
        publish_portal_site.sync_site_data(
            repo_root=Path("/tmp/kfc"),
            python_bin=sys.executable,
            preserve_existing_collections=[],
        )
