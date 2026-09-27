# runway-unitcost — audit, 2026-09-27

First audit of this repository. Read in full: `runway_unitcost/__init__.py`,
`runway_unitcost/__main__.py`, `README.md`, `pyproject.toml`, the CI workflow,
`e2e_check.py` and the test file.

## What was checked, and how

Baseline before any change, all green: `python3 -m unittest discover -s tests`
(46 tests) and `python3 e2e_check.py`.

**Every worked example in the README was executed, not read.** All of them
produce exactly the output the README prints, including the 19-line
"pick the cheapest model that fits" table character for character, the four
docstring examples, and the `estimate_json` block. That is worth recording
because a pricing table is the one thing in this package a user cannot check for
themselves.

**The package builds and installs.** `pip install .` into a clean venv succeeds,
and the installed copy imports and runs from a different working directory, both
as a library and as `python -m runway_unitcost` (`$0.6000`, and `--list`).

**The arithmetic was probed at the edges**: both surcharge caps
(`seedance2_5` input at 30s, `hailuo3` reference video at 15s, `gemini_omni_flash`
v2v input at 10s) clamp correctly; the minimum-credit floor applies where
documented and surcharges count towards clearing it; `unit_cost` and
`resolve_tier` agree with the table for every model and tier; unknown models and
tiers, and negative durations and counts, all raise `ValueError` as the README
promises. Money is `Decimal` end to end with a single `ROUND_HALF_UP` at the
boundary, exactly as documented. No defect found in the costing code.

## Fixed

**The README's install command does not work.** `README.md` opened with
`pip install runway-unitcost`, and that package does not exist on PyPI —
`https://pypi.org/pypi/runway-unitcost/json` returns 404. It is the first
instruction a reader follows, so every user hit it on their first minute.

Replaced with the command that was verified to work from a clean venv in this
audit:

    pip install git+https://github.com/dhyabi2/runway-unitcost

and a plain statement that it is not on PyPI yet, so the README stops promising
something that is not there. The existing "or just vendor the directory"
fallback is kept.

**No test accompanies this change, deliberately.** The defect is that a name is
absent from a third-party index; a test for it would either need the network
(making the suite fail offline and in CI for reasons unrelated to this code) or
would assert that the README does not contain a particular string, which would
pass while saying nothing about whether the command it does contain works. The
verification is recorded above instead: the 404, and the successful install of
the replacement command. If the package is later published to PyPI, revert this
hunk — nothing else in the repository depends on it.

## Looked at and deliberately not changed

- **`seedance2_mini` has a `MIN_CREDITS` entry but no per-second rate**, so
  estimating it raises `ValueError` on an unknown model rather than reporting the
  floor. The same is true of `grok`, which carries the reference-image rule with
  no rate. Both are stated plainly in the README's "Coverage of the rate table"
  section as a deliberate refusal to invent a price, which is the right call;
  the dead-looking entries are the groundwork for the rate landing later.
- **A non-numeric `duration_sec` raises `TypeError`, not `ValueError`** (from the
  `duration_sec < 0` comparison). The README promises `ValueError` for a
  *negative* duration and for unknown models and tiers, which is what happens; it
  does not promise anything about a string, and the CLI's `type=int` means the
  command line cannot reach it. Not worth widening the contract for.
- **`--list` is honoured before the argument parser runs**, so it works without
  the two required positionals, at the cost of `... gen4.5 5 --list` listing
  instead of estimating. That is the ordinary shape of a shortcut flag.
- **Surcharge arguments are ignored for models that have no such surcharge**
  (for example `ref_images` on `gen4.5`). Correct against the published rules as
  the README states them, so silence is right rather than an error.

## Not found

No secret, key or seed in the tree or in `git log -p`. No dependency of any kind
(standard library only, and `dependencies = []` in `pyproject.toml`). No network
access, no credentials, no file or shell path anywhere in the package — it is
pure arithmetic, as it claims.
