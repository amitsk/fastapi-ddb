import re
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
SECTIONS = [
    "Overview",
    "Prerequisites",
    "Quick start",
    "Make targets",
    "Configuration",
    "API",
    "Data model",
    "Testing",
    "Development",
    "Project layout",
    "Out of scope",
]
SPEC_COMMANDS = [
    "docker compose up -d",
    "DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/create_table.py",
    "DYNAMODB_ENDPOINT_URL=http://localhost:8000 python scripts/seed.py",
    "DYNAMODB_ENDPOINT_URL=http://localhost:8000 uvicorn app.main:app --port 3000",
    "http://localhost:3000/docs",
]


def test_readme_has_every_section_in_order():
    headings = re.findall(r"^## (.+)$", README, re.MULTILINE)
    assert [h for h in headings if h in SECTIONS] == SECTIONS


def test_readme_links_the_spec_and_states_the_spec_commands():
    assert "docs/superpowers/specs/2026-10-03-skilifts-demo-api-design.md" in README
    for command in SPEC_COMMANDS:
        assert command in README
    assert "spec only" not in README.lower()


def test_readme_documents_every_route():
    # FastAPI 0.142 leaves an included router in ``app.routes`` unresolved, so the
    # route table is read from the generated OpenAPI document of the same app.
    paths = app.openapi()["paths"]
    documented = {
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith(("/lifts", "/resort"))
        for method in operations
    }
    assert len(documented) == 14
    for method, path in documented:
        assert f"{method} {path}" in README, (method, path)


def test_readme_documents_every_make_target_and_setting():
    makefile = (ROOT / "Makefile").read_text()
    for target in re.findall(r"^([a-zA-Z_-]+):.*## ", makefile, re.MULTILINE):
        assert f"make {target}" in README or f"`{target}`" in README, target
    for setting in (
        "DYNAMODB_TABLE_NAME",
        "AWS_REGION",
        "DYNAMODB_ENDPOINT_URL",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ):
        assert setting in README
