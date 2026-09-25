#!/usr/bin/env python3
"""End-to-end check: exercise the installed package the way a caller would.

Runs every line of the spec's acceptance list against the real public API and
the real CLI, then prints a pass/fail line for each. Exits non-zero if any
check fails. No network, no credentials.

    python3 e2e_check.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runway_unitcost import estimate, estimate_json, unit_cost  # noqa: E402

HERE = Path(__file__).resolve().parent
failures = []


def check(label, got, want):
    ok = got == want
    print("  {}  {:<52s} -> {!r}".format("PASS" if ok else "FAIL", label, got))
    if not ok:
        failures.append("{}: got {!r}, want {!r}".format(label, got, want))


def main() -> int:
    print("acceptance tests, against the real API")
    check('unit_cost("gen4.5")[1]', unit_cost("gen4.5")[1], Decimal("0.12"))
    check('estimate("gen4.5", 5)', estimate("gen4.5", 5), Decimal("0.6000"))
    check(
        'estimate("seedance2_5",10,"720p",input_sec=5)',
        estimate("seedance2_5", 10, "720p", input_sec=5),
        Decimal("3.7500"),
    )
    check('estimate("aleph2",1,"0")', estimate("aleph2", 1, "0"), Decimal("0.5600"))
    check(
        'estimate_json("gen4_turbo",1)["usd_per_sec"]',
        estimate_json("gen4_turbo", 1)["usd_per_sec"],
        0.05,
    )

    try:
        estimate("nope", 1)
        check('estimate("nope",1) raises ValueError', "no exception", "ValueError")
    except ValueError:
        check('estimate("nope",1) raises ValueError', "ValueError", "ValueError")

    print("\nacceptance tests, against the real CLI")
    out = subprocess.run(
        [sys.executable, "-m", "runway_unitcost", "gen4.5", "5", "--json"],
        cwd=HERE, capture_output=True, text=True,
    )
    check("python -m runway_unitcost gen4.5 5 --json (exit)", out.returncode, 0)
    check(
        "  ... total_usd",
        json.loads(out.stdout)["total_usd"] if out.returncode == 0 else None,
        0.60,
    )

    bad = subprocess.run(
        [sys.executable, "-m", "runway_unitcost", "nope", "5"],
        cwd=HERE, capture_output=True, text=True,
    )
    check("python -m runway_unitcost nope 5 (exit)", bad.returncode, 2)

    print("\nerror paths")
    for label, fn in (
        ('estimate("seedance2",5,"8K")', lambda: estimate("seedance2", 5, "8K")),
        ('estimate("seedance2",5) with no tier', lambda: estimate("seedance2", 5)),
        ('estimate("gen4.5",-1)', lambda: estimate("gen4.5", -1)),
        ('estimate("grok",5) (no published rate)', lambda: estimate("grok", 5)),
    ):
        try:
            fn()
            check(label + " raises", "no exception", "ValueError")
        except ValueError:
            check(label + " raises", "ValueError", "ValueError")

    print()
    if failures:
        for f in failures:
            print("FAILED:", f)
        return 1
    print("all end-to-end checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
