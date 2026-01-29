"""Demo scripts packaged with Tinman."""

from .github_demo import main as github_demo_main
from .huggingface_demo import main as huggingface_demo_main
from .replicate_demo import main as replicate_demo_main
from .fal_demo import main as fal_demo_main
from .runner import main as demo_runner_main
from .env_check import main as demo_env_check_main

__all__ = [
    "github_demo_main",
    "huggingface_demo_main",
    "replicate_demo_main",
    "fal_demo_main",
    "demo_runner_main",
    "demo_env_check_main",
]