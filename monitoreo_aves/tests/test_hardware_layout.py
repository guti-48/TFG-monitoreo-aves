from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType

import pytest

from hardware.raspberry_pi.node import node_config, supervisor


HARDWARE_DIR = Path(__file__).resolve().parents[1] / "hardware" / "raspberry_pi"


def test_storage_and_local_configuration_keep_existing_locations():
    for value, relative in (
        (node_config.LOCAL_ENV_FILE, "birdmonitor.env"),
        (supervisor.LOCAL_ENV_FILE, "birdmonitor.env"),
        (node_config.OUTBOX_DB, "offline_outbox.db"),
        (node_config.OUTPUT_FOLDER_AUDIO, "records"),
        (node_config.OUTPUT_FOLDER_IMG, "spectrograms"),
        (node_config.CSV_BACKUP, "backup_data.csv"),
        (node_config.GEO_CACHE_FILE, "node_location_cache.json"),
    ):
        assert Path(value) == HARDWARE_DIR / relative


@pytest.mark.parametrize("script,module", [("mainNode.py", "main"), ("supervisor.py", "supervisor")])
def test_service_entrypoints_work_from_another_directory(script, module, tmp_path, monkeypatch):
    called = []
    target = ModuleType(f"hardware.raspberry_pi.node.{module}")
    target.main = lambda: called.append(True)
    monkeypatch.setitem(sys.modules, target.__name__, target)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    runpy.run_path(str(HARDWARE_DIR / script), run_name="__main__")
    assert called == [True]


@pytest.mark.parametrize("script", ["configure_site.py", "configure_delivery.py"])
def test_configurators_can_run_by_absolute_path(script, tmp_path):
    result = subprocess.run(
        [sys.executable, str(HARDWARE_DIR / "tools" / script), "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "--env-file" in result.stdout
