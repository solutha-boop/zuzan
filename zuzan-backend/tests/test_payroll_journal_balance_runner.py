"""Runs the long-standing payroll <-> journal balance script (it wires its own throwaway DB) and requires it to pass."""
import os, subprocess, sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_payroll_field_posts_a_balanced_journal():
    r = subprocess.run([sys.executable, "test_payroll_journal_balance.py"], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
