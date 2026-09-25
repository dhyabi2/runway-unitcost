"""Tests for runway-unitcost.

Every line of the spec's `## Acceptance tests` is covered below under
`TestAcceptance`, one test per line, plus the error paths and the invariants
that hold across the whole pricing table. Nothing here touches the network.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runway_unitcost import (  # noqa: E402
    CREDITS_PER_SECOND,
    CREDIT_TO_USD,
    MIN_CREDITS,
    estimate,
    estimate_json,
    resolve_tier,
    unit_cost,
)
from runway_unitcost.__main__ import main  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestAcceptance(unittest.TestCase):
    """One test per line of the spec's `## Acceptance tests`."""

    def test_gen45_unit_cost_is_12_credits_at_a_cent_each(self):
        # GIVEN gen4.5 WHEN unit_cost()[1] THEN 0.12
        self.assertEqual(unit_cost("gen4.5")[1], Decimal("0.12"))
        self.assertEqual(unit_cost("gen4.5")[0], 12)

    def test_gen45_five_seconds(self):
        # GIVEN estimate("gen4.5", 5) THEN 0.60
        self.assertEqual(estimate("gen4.5", 5), Decimal("0.6000"))

    def test_seedance2_5_720p_with_input_video(self):
        # GIVEN estimate("seedance2_5",10,"720p",input_sec=5) THEN 3.75
        # 10s * 30cr + 5s * 15cr = 375cr
        self.assertEqual(estimate("seedance2_5", 10, "720p", input_sec=5), Decimal("3.7500"))

    def test_aleph2_one_second_hits_the_minimum_credit_floor(self):
        # GIVEN estimate("aleph2",1,"0") THEN 0.56 (28cr < 56 floor)
        self.assertEqual(estimate("aleph2", 1, "0"), Decimal("0.5600"))

    def test_gen4_turbo_usd_per_sec_in_json(self):
        # GIVEN estimate_json("gen4_turbo",1)["usd_per_sec"] THEN 0.05
        self.assertEqual(estimate_json("gen4_turbo", 1)["usd_per_sec"], 0.05)

    def test_unknown_model_raises_value_error(self):
        # GIVEN estimate("nope",1) THEN ValueError
        with self.assertRaises(ValueError):
            estimate("nope", 1)

    def test_cli_json_total(self):
        # GIVEN python -m runway_unitcost gen4.5 5 --json THEN {"...","total_usd":0.60}
        out = subprocess.run(
            [sys.executable, "-m", "runway_unitcost", "gen4.5", "5", "--json"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        payload = json.loads(out.stdout)
        self.assertEqual(payload["total_usd"], 0.60)
        self.assertEqual(payload["model"], "gen4.5")


class TestErrorPaths(unittest.TestCase):
    def test_unknown_tier_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            estimate("seedance2", 5, "8K")
        self.assertIn("unknown tier", str(ctx.exception))

    def test_unknown_model_message_names_the_model(self):
        with self.assertRaises(ValueError) as ctx:
            unit_cost("definitely_not_a_model")
        self.assertIn("definitely_not_a_model", str(ctx.exception))

    def test_multi_tier_model_without_a_default_requires_a_tier(self):
        with self.assertRaises(ValueError) as ctx:
            estimate("seedance2", 5)
        self.assertIn("no default tier", str(ctx.exception))

    def test_negative_duration_raises(self):
        with self.assertRaises(ValueError):
            estimate("gen4.5", -1)

    def test_negative_input_sec_raises(self):
        with self.assertRaises(ValueError):
            estimate("seedance2_5", 5, "720p", input_sec=-3)

    def test_negative_ref_images_raises(self):
        with self.assertRaises(ValueError):
            estimate("hailuo3", 5, "768p", ref_images=-1)

    def test_grok_has_a_surcharge_rule_but_no_published_rate_yet(self):
        # The surcharge rule names grok; the rate table in this release does not,
        # so estimating it must fail loudly rather than invent a price.
        with self.assertRaises(ValueError):
            estimate("grok", 5)

    def test_seedance2_mini_has_a_floor_but_no_published_rate_yet(self):
        self.assertIn("seedance2_mini", MIN_CREDITS)
        with self.assertRaises(ValueError):
            estimate("seedance2_mini", 5)

    def test_cli_unknown_model_exits_nonzero(self):
        self.assertEqual(main(["nope", "5"]), 2)

    def test_cli_unknown_tier_exits_nonzero(self):
        self.assertEqual(main(["seedance2", "5", "--tier", "8K"]), 2)


class TestTierResolution(unittest.TestCase):
    def test_single_tier_model_resolves_without_a_tier(self):
        self.assertEqual(resolve_tier("gen4.5"), "0")
        self.assertEqual(resolve_tier("aleph2"), "0")

    def test_veo_defaults_to_audio_and_honours_with_audio_false(self):
        self.assertEqual(resolve_tier("veo3.1"), "audio")
        self.assertEqual(resolve_tier("veo3.1", with_audio=True), "audio")
        self.assertEqual(resolve_tier("veo3.1", with_audio=False), "no_audio")
        self.assertEqual(estimate("veo3.1", 2), Decimal("0.8000"))              # 2 * 40cr
        self.assertEqual(estimate("veo3.1", 2, with_audio=False), Decimal("0.4000"))  # 2 * 20cr

    def test_veo_fast_defaults_the_same_way(self):
        self.assertEqual(estimate("veo3.1_fast", 4), Decimal("0.6000"))         # 4 * 15cr
        self.assertEqual(estimate("veo3.1_fast", 4, with_audio=False), Decimal("0.4000"))

    def test_gemini_defaults_to_t2v(self):
        self.assertEqual(resolve_tier("gemini_omni_flash"), "t2v")

    def test_explicit_tier_overrides_the_default(self):
        self.assertEqual(resolve_tier("veo3.1", "no_audio", with_audio=True), "no_audio")


class TestSurcharges(unittest.TestCase):
    def test_seedance2_5_input_video_is_capped_at_30_seconds(self):
        # 5s * 20cr output = 100cr; input capped at 30s * 10cr = 300cr -> 400cr
        self.assertEqual(estimate("seedance2_5", 5, "480p", input_sec=90), Decimal("4.0000"))

    def test_hailuo3_reference_images_are_two_credits_each(self):
        # 3s * 10cr = 30cr, + 4 images * 2cr = 8cr -> 38cr
        self.assertEqual(estimate("hailuo3", 3, "768p", ref_images=4), Decimal("0.3800"))

    def test_hailuo3_reference_video_is_capped_at_15_seconds(self):
        # 3s * 15cr = 45cr, + min(40,15)s * 15cr = 225cr -> 270cr
        self.assertEqual(estimate("hailuo3", 3, "2K", ref_video_sec=40), Decimal("2.7000"))

    def test_gemini_first_frame_and_ref_images_are_one_credit_each(self):
        # 5s * 10cr = 50cr, + 1 first frame + 2 ref images = 53cr
        got = estimate("gemini_omni_flash", 5, "i2v", ref_images=2, first_frame_image=True)
        self.assertEqual(got, Decimal("0.5300"))

    def test_gemini_v2v_input_video_is_capped_at_10_seconds(self):
        # 4s * 11cr = 44cr, + min(25,10)s * 11cr = 110cr -> 154cr
        self.assertEqual(estimate("gemini_omni_flash", 4, "v2v", input_sec=25), Decimal("1.5400"))

    def test_surcharges_do_not_leak_across_models(self):
        # ref_images carries no charge on a model without that rule.
        self.assertEqual(
            estimate("gen4.5", 5, ref_images=9), estimate("gen4.5", 5)
        )
        # input_sec carries no charge on seedance2 (only seedance2_5 bills it).
        self.assertEqual(
            estimate("seedance2", 5, "720p", input_sec=20), estimate("seedance2", 5, "720p")
        )


class TestFloor(unittest.TestCase):
    def test_floor_lifts_a_short_generation(self):
        b = estimate_json("aleph2", 1, "0")
        self.assertTrue(b["floor_applied"])
        self.assertEqual(b["total_credits"], 56.0)
        self.assertEqual(b["min_credits_floor"], 56)

    def test_floor_does_not_apply_once_the_run_is_long_enough(self):
        b = estimate_json("aleph2", 5, "0")  # 140cr > 56
        self.assertFalse(b["floor_applied"])
        self.assertEqual(b["total_credits"], 140.0)
        self.assertEqual(b["total_usd"], 1.40)

    def test_seedance2_5_floor_is_80_credits(self):
        b = estimate_json("seedance2_5", 1, "480p")  # 20cr < 80
        self.assertTrue(b["floor_applied"])
        self.assertEqual(b["total_usd"], 0.80)

    def test_surcharges_count_towards_clearing_the_floor(self):
        # 1s * 20cr + 8s input * 10cr = 100cr, above the 80 floor.
        b = estimate_json("seedance2_5", 1, "480p", input_sec=8)
        self.assertFalse(b["floor_applied"])
        self.assertEqual(b["total_credits"], 100.0)

    def test_model_without_a_floor_reports_zero(self):
        self.assertEqual(estimate_json("gen4.5", 1)["min_credits_floor"], 0)


class TestJsonSchema(unittest.TestCase):
    def test_schema_matches_the_spec_example(self):
        self.assertEqual(
            estimate_json("seedance2_5", 10, "720p"),
            {
                "model": "seedance2_5",
                "tier": "720p",
                "duration_sec": 10,
                "rate_credits_per_sec": 30,
                "usd_per_sec": 0.3,
                "items": [
                    {"kind": "output", "units": 10, "per_unit_usd": 0.3, "usd": 3.0}
                ],
                "input_total_usd": 0.0,
                "min_credits_floor": 80,
                "floor_applied": False,
                "total_credits": 300.0,
                "total_usd": 3.0,
            },
        )

    def test_json_is_serialisable(self):
        payload = estimate_json("hailuo3", 3, "2K", ref_images=2, ref_video_sec=5)
        json.dumps(payload)  # must not raise

    def test_items_carry_every_applied_surcharge(self):
        kinds = [i["kind"] for i in estimate_json(
            "gemini_omni_flash", 4, "v2v", input_sec=6, ref_images=1, first_frame_image=True
        )["items"]]
        self.assertEqual(kinds, ["output", "first_frame_image", "ref_image", "input_video"])

    def test_input_total_usd_is_the_non_output_subtotal(self):
        b = estimate_json("seedance2_5", 10, "720p", input_sec=5)
        self.assertAlmostEqual(b["input_total_usd"], 0.75, places=9)
        self.assertAlmostEqual(
            b["input_total_usd"] + b["items"][0]["usd"], b["total_usd"], places=9
        )


class TestInvariantsAcrossTheTable(unittest.TestCase):
    def test_estimate_json_total_agrees_with_estimate_for_every_tier(self):
        for model, tiers in CREDITS_PER_SECOND.items():
            for tier in tiers:
                with self.subTest(model=model, tier=tier):
                    self.assertEqual(
                        float(estimate(model, 7, tier)),
                        estimate_json(model, 7, tier)["total_usd"],
                    )

    def test_unit_cost_is_rate_times_one_cent_for_every_tier(self):
        for model, tiers in CREDITS_PER_SECOND.items():
            for tier, rate in tiers.items():
                with self.subTest(model=model, tier=tier):
                    self.assertEqual(unit_cost(model, tier), (rate, Decimal(rate) * CREDIT_TO_USD))

    def test_cost_is_linear_in_duration_above_the_floor(self):
        for model, tiers in CREDITS_PER_SECOND.items():
            for tier in tiers:
                with self.subTest(model=model, tier=tier):
                    # 100s is well clear of every floor in the table.
                    self.assertEqual(
                        estimate(model, 100, tier), estimate(model, 50, tier) * 2
                    )

    def test_estimate_returns_decimal_not_float(self):
        self.assertIsInstance(estimate("gen4.5", 5), Decimal)

    def test_zero_duration_is_free_unless_a_floor_applies(self):
        self.assertEqual(estimate("gen4.5", 0), Decimal("0.0000"))
        self.assertEqual(estimate("aleph2", 0, "0"), Decimal("0.5600"))

    def test_no_float_rounding_drift_on_a_long_run(self):
        # 3600s of seedance2 4K = 540000cr = $5400 exactly.
        self.assertEqual(estimate("seedance2", 3600, "4K"), Decimal("5400.0000"))


class TestCli(unittest.TestCase):
    def test_plain_output_prints_dollars(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["gen4.5", "5"])
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue().strip(), "$0.6000")

    def test_tier_and_input_sec_flags(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["seedance2_5", "10", "--tier", "720p", "--input-sec", "5", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["total_usd"], 3.75)

    def test_list_flag_prints_every_model(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--list"])
        self.assertEqual(rc, 0)
        for model in CREDITS_PER_SECOND:
            self.assertIn(model, buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
