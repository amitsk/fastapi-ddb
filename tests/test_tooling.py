import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_declares_uv_toolchain():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.14"
    assert data["build-system"]["build-backend"] == "hatchling.build"
    assert data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["app"]
    dev = " ".join(data["dependency-groups"]["dev"])
    for name in ("pytest", "moto", "httpx2", "ruff", "ty"):
        assert name in dev
    assert data["tool"]["pytest"]["ini_options"]["pythonpath"] == ["."]
    assert (ROOT / "uv.lock").exists()


def test_makefile_has_the_dev_targets_and_no_coverage_gate():
    makefile = (ROOT / "Makefile").read_text()
    for target in (
        "help",
        "install",
        "lint",
        "type_check",
        "test",
        "coverage",
        "check",
        "check_format",
        "fix_format",
    ):
        assert re.search(rf"^{target}:.*## ", makefile, re.MULTILINE), target
    assert "uv run ty check app scripts" in makefile
    assert "cov-fail-under" not in makefile
