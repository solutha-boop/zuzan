"""Regression: the admin clear-data endpoint imported models that don't exist
(StockMovement, BankTransaction, Document) and raised ImportError at runtime."""
import ast
import importlib
import pathlib


def test_clear_data_imports_resolve():
    src = pathlib.Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "admin_clear_company_data")
    checked = 0
    for node in ast.walk(fn):
        if isinstance(node, ast.ImportFrom) and node.module in ("database", "companies"):
            mod = importlib.import_module(node.module)
            for alias in node.names:
                assert hasattr(mod, alias.name), f"{node.module}.{alias.name} does not exist"
                checked += 1
    assert checked > 10
