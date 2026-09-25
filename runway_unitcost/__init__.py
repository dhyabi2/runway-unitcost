"""runway-unitcost - pre-flight per-second cost estimates for Runway video generation.

Turns Runway Dev's published per-second credit rates into an exact dollar
estimate *before* a generation is submitted, so an agent can compare models and
decide whether to spend. Pure arithmetic: no network, no credentials, no
payment code.

    >>> from runway_unitcost import estimate, unit_cost
    >>> estimate("gen4.5", 5)
    Decimal('0.6000')
    >>> unit_cost("gen4.5")
    (12, Decimal('0.12'))

Money is carried as ``Decimal`` end to end. Floats appear only at the JSON
boundary in :func:`estimate_json`, which has to be serialisable.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

__all__ = [
    "estimate",
    "estimate_json",
    "unit_cost",
    "resolve_tier",
    "CREDITS_PER_SECOND",
    "MIN_CREDITS",
    "CREDIT_TO_USD",
    "__version__",
]

__version__ = "0.1.0"

# ── Pricing data ────────────────────────────────────────────────────────────
# Credits charged per second of generated output, by model and tier. Tier keys
# are strings so the table round-trips through JSON unchanged. A model with a
# single tier uses the key "0", which callers may pass explicitly or omit.
CREDITS_PER_SECOND = {
    "gen4.5": {"0": 12},
    "gen4_turbo": {"0": 5},
    "aleph2": {"0": 28},
    "seedance2": {"480p": 36, "720p": 36, "1080p": 40, "4K": 150},
    "seedance2_5": {"480p": 20, "720p": 30, "1080p": 68},
    "veo3.1": {"audio": 40, "no_audio": 20},
    "veo3.1_fast": {"audio": 15, "no_audio": 10},
    "hailuo3": {"768p": 10, "2K": 15},
    "gemini_omni_flash": {"t2v": 10, "i2v": 10, "v2v": 11},
}

# Minimum credits charged for a generation, whatever its duration.
MIN_CREDITS = {
    "aleph2": 56,
    "seedance2_5": 80,
    "seedance2_mini": 64,
}

CREDIT_TO_USD = Decimal("0.01")

# Models whose reference images are billed at a flat 2 credits each.
# ``grok`` carries this surcharge in Runway's published rules but has no
# per-second rate in this release's table, so estimating it raises ValueError
# until that rate lands.
_REF_IMAGE_FLAT_2 = ("grok", "hailuo3")

# Caps on billable input/reference footage, in seconds.
_SEEDANCE2_5_INPUT_CAP = 30
_HAILUO3_REF_VIDEO_CAP = 15
_GEMINI_V2V_INPUT_CAP = 10

# Tier chosen when the caller does not name one and the model has more than one.
_TIER_DEFAULTS = {
    "veo3.1": ("no_audio", "audio"),       # (with_audio False, with_audio True/None)
    "veo3.1_fast": ("no_audio", "audio"),
    "gemini_omni_flash": ("t2v", "t2v"),
}

_USD_PLACES = Decimal("0.0001")


def _quantize_usd(value: Decimal) -> Decimal:
    """Round a dollar amount to 4 decimal places, half away from zero."""
    return value.quantize(_USD_PLACES, rounding=ROUND_HALF_UP)


def _rates(model: str) -> dict:
    try:
        return CREDITS_PER_SECOND[model]
    except KeyError:
        raise ValueError(
            "unknown model {!r}; known models: {}".format(
                model, ", ".join(sorted(CREDITS_PER_SECOND))
            )
        ) from None


def resolve_tier(model: str, tier=None, with_audio=None) -> str:
    """Return the tier key to bill ``model`` at.

    An explicit *tier* is validated against the model's table. Otherwise a
    single-tier model resolves to its only key, the veo models resolve by
    *with_audio* (audio unless it is explicitly False), and
    ``gemini_omni_flash`` resolves to ``t2v``. Any other multi-tier model has
    no safe default, so omitting the tier is a ValueError.
    """
    rates = _rates(model)

    if tier is not None:
        tier = str(tier)
        if tier not in rates:
            raise ValueError(
                "unknown tier {!r} for model {!r}; known tiers: {}".format(
                    tier, model, ", ".join(rates)
                )
            )
        return tier

    if len(rates) == 1:
        return next(iter(rates))

    if model in _TIER_DEFAULTS:
        no_audio, audio = _TIER_DEFAULTS[model]
        return no_audio if with_audio is False else audio

    raise ValueError(
        "model {!r} has no default tier; pass one of: {}".format(model, ", ".join(rates))
    )


def unit_cost(model: str, tier=None):
    """Return ``(credits_per_second, usd_per_second)`` for a model tier."""
    resolved = resolve_tier(model, tier)
    rate = CREDITS_PER_SECOND[model][resolved]
    return rate, Decimal(rate) * CREDIT_TO_USD


def _breakdown(
    model,
    duration_sec,
    tier=None,
    input_sec=0,
    ref_images=0,
    ref_video_sec=0,
    with_audio=None,
    first_frame_image=False,
):
    """Shared costing core. Returns a dict of Decimals plus the item list."""
    if duration_sec is None or duration_sec < 0:
        raise ValueError("duration_sec must be >= 0, got {!r}".format(duration_sec))
    for name, value in (
        ("input_sec", input_sec),
        ("ref_images", ref_images),
        ("ref_video_sec", ref_video_sec),
    ):
        if value is None or value < 0:
            raise ValueError("{} must be >= 0, got {!r}".format(name, value))

    resolved_tier = resolve_tier(model, tier, with_audio=with_audio)
    rate = CREDITS_PER_SECOND[model][resolved_tier]
    usd_per_sec = Decimal(rate) * CREDIT_TO_USD

    output_credits = Decimal(duration_sec) * rate
    items = [
        {
            "kind": "output",
            "units": duration_sec,
            "per_unit_usd": usd_per_sec,
            "usd": output_credits * CREDIT_TO_USD,
        }
    ]

    extra_credits = Decimal(0)

    # seedance2_5 bills input video at half the output rate, capped at 30s.
    if model == "seedance2_5" and input_sec:
        units = min(input_sec, _SEEDANCE2_5_INPUT_CAP)
        per_unit = Decimal(rate) / 2
        credits = Decimal(units) * per_unit
        extra_credits += credits
        items.append(
            {
                "kind": "input_video",
                "units": units,
                "per_unit_usd": per_unit * CREDIT_TO_USD,
                "usd": credits * CREDIT_TO_USD,
            }
        )

    # grok / hailuo3 bill reference images at a flat 2 credits each.
    if model in _REF_IMAGE_FLAT_2 and ref_images:
        credits = Decimal(ref_images) * 2
        extra_credits += credits
        items.append(
            {
                "kind": "ref_image",
                "units": ref_images,
                "per_unit_usd": Decimal(2) * CREDIT_TO_USD,
                "usd": credits * CREDIT_TO_USD,
            }
        )

    # hailuo3 bills reference video at the output rate, capped at 15s.
    if model == "hailuo3" and ref_video_sec:
        units = min(ref_video_sec, _HAILUO3_REF_VIDEO_CAP)
        credits = Decimal(units) * rate
        extra_credits += credits
        items.append(
            {
                "kind": "ref_video",
                "units": units,
                "per_unit_usd": usd_per_sec,
                "usd": credits * CREDIT_TO_USD,
            }
        )

    if model == "gemini_omni_flash":
        if first_frame_image:
            extra_credits += 1
            items.append(
                {
                    "kind": "first_frame_image",
                    "units": 1,
                    "per_unit_usd": CREDIT_TO_USD,
                    "usd": CREDIT_TO_USD,
                }
            )
        if ref_images:
            credits = Decimal(ref_images)
            extra_credits += credits
            items.append(
                {
                    "kind": "ref_image",
                    "units": ref_images,
                    "per_unit_usd": CREDIT_TO_USD,
                    "usd": credits * CREDIT_TO_USD,
                }
            )
        # v2v bills the source video at the output rate, capped at 10s.
        if resolved_tier == "v2v" and input_sec:
            units = min(input_sec, _GEMINI_V2V_INPUT_CAP)
            credits = Decimal(units) * rate
            extra_credits += credits
            items.append(
                {
                    "kind": "input_video",
                    "units": units,
                    "per_unit_usd": usd_per_sec,
                    "usd": credits * CREDIT_TO_USD,
                }
            )

    total_credits = output_credits + extra_credits
    floor = MIN_CREDITS.get(model, 0)
    floor_applied = total_credits < floor
    if floor_applied:
        total_credits = Decimal(floor)

    return {
        "model": model,
        "tier": resolved_tier,
        "duration_sec": duration_sec,
        "rate_credits_per_sec": rate,
        "usd_per_sec": usd_per_sec,
        "items": items,
        "input_total_usd": extra_credits * CREDIT_TO_USD,
        "min_credits_floor": floor,
        "floor_applied": floor_applied,
        "total_credits": total_credits,
        "total_usd": _quantize_usd(total_credits * CREDIT_TO_USD),
    }


def estimate(
    model: str,
    duration_sec: int,
    tier=None,
    *,
    input_sec: int = 0,
    ref_images: int = 0,
    ref_video_sec: int = 0,
    with_audio=None,
    first_frame_image: bool = False,
) -> Decimal:
    """Dollar cost of one generation, as a ``Decimal`` rounded to 4 places.

    Raises ValueError on an unknown model or an unknown tier.

        >>> estimate("seedance2_5", 10, "720p", input_sec=5)
        Decimal('3.7500')
    """
    return _breakdown(
        model,
        duration_sec,
        tier,
        input_sec=input_sec,
        ref_images=ref_images,
        ref_video_sec=ref_video_sec,
        with_audio=with_audio,
        first_frame_image=first_frame_image,
    )["total_usd"]


def estimate_json(
    model: str,
    duration_sec: int,
    tier=None,
    *,
    input_sec: int = 0,
    ref_images: int = 0,
    ref_video_sec: int = 0,
    with_audio=None,
    first_frame_image: bool = False,
) -> dict:
    """The same estimate as a JSON-serialisable dict with an itemised breakdown.

    ``total_usd`` equals ``float(estimate(...))`` for the same arguments.
    """
    b = _breakdown(
        model,
        duration_sec,
        tier,
        input_sec=input_sec,
        ref_images=ref_images,
        ref_video_sec=ref_video_sec,
        with_audio=with_audio,
        first_frame_image=first_frame_image,
    )
    return {
        "model": b["model"],
        "tier": b["tier"],
        "duration_sec": b["duration_sec"],
        "rate_credits_per_sec": b["rate_credits_per_sec"],
        "usd_per_sec": float(b["usd_per_sec"]),
        "items": [
            {
                "kind": i["kind"],
                "units": i["units"],
                "per_unit_usd": float(i["per_unit_usd"]),
                "usd": float(i["usd"]),
            }
            for i in b["items"]
        ],
        "input_total_usd": float(b["input_total_usd"]),
        "min_credits_floor": b["min_credits_floor"],
        "floor_applied": b["floor_applied"],
        "total_credits": float(b["total_credits"]),
        "total_usd": float(b["total_usd"]),
    }
