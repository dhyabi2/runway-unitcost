# runway-unitcost

Pre-flight per-second cost estimates for Runway video generation.

Runway bills video generation in credits per second of output, at $0.01 per
credit, with per-model minimum charges and surcharges for input video and
reference images. `runway-unitcost` turns that table into an exact dollar figure
**before** a generation is submitted, so an agent can compare models and decide
whether to spend.

Pure arithmetic. No network, no credentials, no API calls, no third-party
dependencies — the whole package is the standard library.

## Install

Not on PyPI yet, so install it from the repository:

```
pip install git+https://github.com/dhyabi2/runway-unitcost
```

Or just vendor the `runway_unitcost/` directory; it has no dependencies.

## Use it

```python
from runway_unitcost import estimate, estimate_json, unit_cost

# What does one second cost on this model?
unit_cost("gen4.5")                       # (12, Decimal('0.12'))

# What will this generation cost?
estimate("gen4.5", 5)                     # Decimal('0.6000')

# 10s of seedance2_5 at 720p, transforming 5s of input video
estimate("seedance2_5", 10, "720p", input_sec=5)   # Decimal('3.7500')

# Short clips can hit a model's minimum charge
estimate("aleph2", 1)                     # Decimal('0.5600')  — 28cr billed as 56cr

# The itemised version an agent can log or compare on
estimate_json("seedance2_5", 10, "720p")
```

```json
{
  "model": "seedance2_5",
  "tier": "720p",
  "duration_sec": 10,
  "rate_credits_per_sec": 30,
  "usd_per_sec": 0.3,
  "items": [{"kind": "output", "units": 10, "per_unit_usd": 0.3, "usd": 3.0}],
  "input_total_usd": 0.0,
  "min_credits_floor": 80,
  "floor_applied": false,
  "total_credits": 300.0,
  "total_usd": 3.0
}
```

### Pick the cheapest model that fits

A complete, runnable example — copy it into a file and run it:

```python
from runway_unitcost import CREDITS_PER_SECOND, estimate

DURATION = 6
BUDGET = 1.50

options = []
for model, tiers in CREDITS_PER_SECOND.items():
    for tier in tiers:
        options.append((estimate(model, DURATION, tier), model, tier))

print(f"{DURATION}s of video, budget ${BUDGET:.2f}\n")
for usd, model, tier in sorted(options):
    mark = "  " if usd > BUDGET else "ok"
    print(f"{mark}  ${usd:>9}  {model}:{tier}")
```

```
6s of video, budget $1.50

ok  $   0.3000  gen4_turbo:0
ok  $   0.6000  gemini_omni_flash:i2v
ok  $   0.6000  gemini_omni_flash:t2v
ok  $   0.6000  hailuo3:768p
ok  $   0.6000  veo3.1_fast:no_audio
ok  $   0.6600  gemini_omni_flash:v2v
ok  $   0.7200  gen4.5:0
ok  $   0.9000  hailuo3:2K
ok  $   0.9000  veo3.1_fast:audio
ok  $   1.2000  seedance2_5:480p
ok  $   1.2000  veo3.1:no_audio
    $   1.6800  aleph2:0
    $   1.8000  seedance2_5:720p
    $   2.1600  seedance2:480p
    $   2.1600  seedance2:720p
    $   2.4000  seedance2:1080p
    $   2.4000  veo3.1:audio
    $   4.0800  seedance2_5:1080p
    $   9.0000  seedance2:4K
```

### CLI

```
$ python -m runway_unitcost gen4.5 5
$0.6000

$ python -m runway_unitcost gen4.5 5 --json
{"model": "gen4.5", "tier": "0", "duration_sec": 5, ... "total_usd": 0.6}

$ python -m runway_unitcost seedance2_5 10 --tier 720p --input-sec 5 --json
{... "total_credits": 375.0, "total_usd": 3.75}

$ python -m runway_unitcost --list
aleph2               0=28cr/s
gemini_omni_flash    t2v=10cr/s, i2v=10cr/s, v2v=11cr/s
...
```

Exit code is `2` on an unknown model or tier, with the message on stderr.

## API

| Call | Returns |
|---|---|
| `estimate(model, duration_sec, tier=None, *, input_sec=0, ref_images=0, ref_video_sec=0, with_audio=None, first_frame_image=False)` | `Decimal` dollars, 4 dp |
| `estimate_json(...)` | `dict`, same arguments, itemised and JSON-serialisable |
| `unit_cost(model, tier=None)` | `(credits_per_second, Decimal usd_per_second)` |
| `resolve_tier(model, tier=None, with_audio=None)` | the tier key that would be billed |

`estimate` and `unit_cost` raise `ValueError` on an unknown model or an unknown
tier, and on a negative duration or count.

**Tiers.** A single-tier model (`gen4.5`, `gen4_turbo`, `aleph2`) resolves
without one. `veo3.1` and `veo3.1_fast` bill the `audio` tier unless you pass
`with_audio=False`. `gemini_omni_flash` defaults to `t2v`. `seedance2`,
`seedance2_5` and `hailuo3` have no safe default, so omitting the tier is a
`ValueError` rather than a guess about your money.

**Surcharges.**

| Model | Rule |
|---|---|
| `seedance2_5` | input video at half the output rate, capped at 30s |
| `hailuo3`, `grok` | 2 credits per reference image |
| `hailuo3` | reference video at the output rate, capped at 15s |
| `gemini_omni_flash` | +1 credit for a first-frame image, +1 per reference image |
| `gemini_omni_flash` `v2v` | source video at the output rate, capped at 10s |

Surcharges count towards clearing a model's minimum-credit floor.

## Money handling

Every amount is a `Decimal`. Credits are integers, the credit-to-dollar rate is
`Decimal("0.01")`, and the only rounding is a single `ROUND_HALF_UP` to 4
decimal places on the final dollar figure. `estimate_json` converts to `float`
at the JSON boundary because JSON has no decimal type — if you are comparing or
summing amounts, use `estimate`.

## Scope

This package estimates dollar cost and nothing else. It does not call Runway,
hold credentials, move money, or model plan allowances, and it covers Runway
only.

## Coverage of the rate table

The rates here are the ones published for the models below. Two names appear in
Runway's billing rules without a per-second rate in this release:

- `grok` carries the 2-credits-per-reference-image rule but has no rate, and
- `seedance2_mini` has a 64-credit minimum but has no rate.

Estimating either raises `ValueError` rather than inventing a price. Add the
rate to `CREDITS_PER_SECOND` and both start working; the surcharge and floor
rules are already in place.

## Tests

```
python -m unittest discover -s tests -v
```

46 tests, no network. Every line of the acceptance spec has a test of its own in
`TestAcceptance`, plus the error paths, the surcharge caps, the floor, the JSON
schema, and invariants checked across every model and tier in the table.

## Licence

MIT
