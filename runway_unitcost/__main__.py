"""CLI: python -m runway_unitcost <model> <duration_sec> [--tier T] [--input-sec N] [--json]"""

from __future__ import annotations

import argparse
import json
import sys

from . import CREDITS_PER_SECOND, estimate, estimate_json


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m runway_unitcost",
        description="Pre-flight dollar cost of a Runway video generation.",
    )
    p.add_argument("model", help="model name, e.g. gen4.5 (--list to see them all)")
    p.add_argument("duration_sec", type=int, help="seconds of video to generate")
    p.add_argument("--tier", default=None, help="model tier, e.g. 720p / audio / v2v")
    p.add_argument("--input-sec", type=int, default=0, help="seconds of input video")
    p.add_argument("--ref-images", type=int, default=0, help="reference images used")
    p.add_argument("--ref-video-sec", type=int, default=0, help="seconds of reference video")
    p.add_argument(
        "--no-audio", dest="with_audio", action="store_false", default=None,
        help="veo models: bill the no_audio tier",
    )
    p.add_argument(
        "--first-frame-image", action="store_true",
        help="gemini_omni_flash: a first-frame image is supplied",
    )
    p.add_argument("--json", action="store_true", help="print the itemised JSON breakdown")
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--list" in argv:
        for model, tiers in sorted(CREDITS_PER_SECOND.items()):
            print("{:20s} {}".format(model, ", ".join("{}={}cr/s".format(t, r) for t, r in tiers.items())))
        return 0

    args = build_parser().parse_args(argv)
    kwargs = dict(
        input_sec=args.input_sec,
        ref_images=args.ref_images,
        ref_video_sec=args.ref_video_sec,
        with_audio=args.with_audio,
        first_frame_image=args.first_frame_image,
    )
    try:
        if args.json:
            print(json.dumps(estimate_json(args.model, args.duration_sec, args.tier, **kwargs)))
        else:
            usd = estimate(args.model, args.duration_sec, args.tier, **kwargs)
            print("${}".format(usd))
    except ValueError as e:
        print("error: {}".format(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
