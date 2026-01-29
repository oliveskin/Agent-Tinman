import os
import json
from pathlib import Path
from datetime import datetime
import modal

APP_NAME = "tinman-fdra-gemini-demo"

REPOS = [
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "pydantic/pydantic",
]

image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install("pip", "setuptools", "wheel", "google-genai")
    .run_commands(
        "git clone https://github.com/oliveskin/Agent-Tinman.git /app",
        "cd /app && pip install -e '.[dev,all]'",
    )
)

app = modal.App(APP_NAME)

# Requires Modal secret: gemini (GEMINI_API_KEY)
secrets = [modal.Secret.from_name("gemini")]


def write_config(path: Path) -> None:
    config = {
        "mode": "lab",
        "database": {"url": "sqlite:///tinman.db"},
        "models": {
            "default": "google",
            "providers": {
                "google": {
                    "api_key": "${GEMINI_API_KEY}",
                    "model": "gemini-2.5-flash",
                }
            },
        },
        "experiments": {"max_parallel": 3, "default_timeout_seconds": 300, "cost_limit_usd": 5.0},
        "risk": {"auto_approve_safe": True, "block_on_destructive": True},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


@app.function(
    image=image,
    secrets=secrets,
    timeout=60 * 30,
    cpu=2,
    memory=4096,
)
def run_tinman():
    os.chdir("/app")

    config_path = Path("/app/.tinman/config.yaml")
    write_config(config_path)

    os.system("tinman init")
    os.system('tinman research --focus "trace_bundle" --max-hypotheses 3 --max-experiments 2')
    os.system("tinman report --format markdown")

    for repo in REPOS:
        os.system(f'tinman research --focus "github:{repo}" --max-hypotheses 3 --max-experiments 2')
        os.system("tinman report --format markdown")

    reports_dir = Path("/app/reports")
    reports_dir.mkdir(exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    os.system(f"cp -r /app/reports /app/reports-{stamp}")

    return f"Completed. Reports in /app/reports-{stamp}"


if __name__ == "__main__":
    with app.run():
        print(run_tinman.remote())
