"""One-command demo runner for Tinman demos."""

import argparse
import os
import sys

from . import github_demo, huggingface_demo, replicate_demo, fal_demo


DEMO_MAP = {
    "github": github_demo.main,
    "huggingface": huggingface_demo.main,
    "replicate": replicate_demo.main,
    "fal": fal_demo.main,
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
    parser.add_argument("demo", choices=sorted(DEMO_MAP.keys()))
    args, extra = parser.parse_known_args()

    _check_env(args.demo)

    # Rewrite argv to pass through demo-specific args
    sys.argv = [sys.argv[0]] + extra
    DEMO_MAP[args.demo]()


if __name__ == "__main__":
    main()
