"""Phase 1 validation test.

If this passes, your environment, dependencies, and test runner are all
wired up correctly. Later phases will add real tests alongside their code
(e.g. tests/test_ingestion.py, tests/test_categorization.py, ...).
"""

import importlib


def test_core_dependencies_importable():
    for module in ("pandas", "dotenv", "sqlalchemy"):
        importlib.import_module(module)


def test_repo_layout_exists():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    expected_dirs = [
        "data",
        "db",
        "src/ingestion",
        "src/categorization",
        "src/analytics",
        "src/anomaly",
        "src/agent",
        "src/interface",
        "notebooks",
        "docs",
    ]
    for d in expected_dirs:
        assert (root / d).is_dir(), f"missing expected directory: {d}"
