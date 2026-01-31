#!/usr/bin/env python
"""Validate required env vars for demo scripts without running providers."""

import argparse
import os
import sys


REQUIRED = {
    "github": ["GITHUB_TOKEN"],
    "huggingface": ["HUGGINGFACE_API_KEY"],
    "replicate": ["REPLICATE_API_TOKEN"],
    "fal": ["FAL_API_KEY"],
    "gemini": ["GEMINI_API_KEY"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("demo", choices=sorted(REQUIRED.keys()) + ["all"])
    args = parser.parse_args()

    demos = REQUIRED.keys() if args.demo == "all" else [args.demo]
    missing = {}
    for demo in demos:
        keys = REQUIRED.get(demo, [])
        miss = [k for k in keys if not os.environ.get(k)]
        if miss:
            missing[demo] = miss

    if missing:
        for demo, keys in missing.items():
            print(f"{demo}: missing {', '.join(keys)}")
        raise SystemExit(2)

    print("All required env vars are set.")


if __name__ == "__main__":
    main()
