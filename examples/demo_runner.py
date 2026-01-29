#!/usr/bin/env python
"""One-command demo runner for Tinman examples."""

import argparse
import os
import subprocess
import sys


DEMO_COMMANDS = {
    "github": [sys.executable, "-m", "tinman.demo.github_demo"],
    "huggingface": [sys.executable, "-m", "tinman.demo.huggingface_demo"],
    "replicate": [sys.executable, "-m", "tinman.demo.replicate_demo"],
    "fal": [sys.executable, "-m", "tinman.demo.fal_demo"],
}

REQUIRED_ENV = {
    "github": ["GITHUB_TOKEN"],
    "huggingface": ["HUGGINGFACE_API_KEY"],
    "replicate": ["REPLICATE_API_TOKEN"],
    "fal": ["FAL_API_KEY"],
}


def _check_env(demo: str) -> None:
    missing = [k for k in REQUIRED_ENV.get(demo, []) if not os.environ.get(k)]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Missing required env var(s) for '{demo}': {names}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("demo", choices=sorted(DEMO_COMMANDS.keys()))
    parser.add_argument("--", dest="pass_through", action="store_true", help="pass args after --")
    args, extra = parser.parse_known_args()

    _check_env(args.demo)

            cmd = list(DEMO_COMMANDS[args.demo]) + extra
            raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
