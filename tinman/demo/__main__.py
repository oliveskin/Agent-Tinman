"""Entry points for packaged demos."""

import sys

from .fal_demo import main as fal_demo_main
from .github_demo import main as github_demo_main
from .huggingface_demo import main as huggingface_demo_main
from .replicate_demo import main as replicate_demo_main

DEMO_ENTRYPOINTS = {
    "github": github_demo_main,
    "huggingface": huggingface_demo_main,
    "replicate": replicate_demo_main,
    "fal": fal_demo_main,
}


def run(demo: str, args: list[str]) -> None:
    if demo not in DEMO_ENTRYPOINTS:
        raise SystemExit(f"Unknown demo: {demo}")
    sys.argv = [sys.argv[0]] + args
    DEMO_ENTRYPOINTS[demo]()
