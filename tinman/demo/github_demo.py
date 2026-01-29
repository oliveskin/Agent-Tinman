"""Run a Tinman research cycle using GitHub repo issues/PRs as focus context."""

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

import requests

from tinman.config import load_config
from tinman.config.modes import OperatingMode
from tinman.cli.main import get_db_session, get_model_client
from tinman.tinman import create_tinman


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "tinman-github-demo",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    resp = requests.get(url, params=params, headers=_github_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def fetch_issues(repo: str, limit: int) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/issues"
    items = _get_json(url, {"state": "open", "per_page": limit})
    # Filter out pull requests from issues endpoint
    return [i for i in items if "pull_request" not in i]


def fetch_prs(repo: str, limit: int) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/pulls"
    return _get_json(url, {"state": "open", "per_page": limit})


def _trim(text: str, max_len: int = 500) -> str:
    text = (text or "").strip().replace("\r\n", "\n")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_focus(repo: str, issues: list[dict[str, Any]], prs: list[dict[str, Any]]) -> str:
    lines = [
        f"GitHub repo: {repo}",
        "Summarize issues/PRs and identify potential failure modes in tooling, reasoning, or context handling.",
        "",
        "Open issues:",
    ]
    for issue in issues:
        lines.append(f"- #{issue.get('number')}: {issue.get('title')}")
        body = _trim(issue.get("body", ""))
        if body:
            lines.append(f"  {body}")
    lines.append("")
    lines.append("Open pull requests:")
    for pr in prs:
        lines.append(f"- #{pr.get('number')}: {pr.get('title')}")
        body = _trim(pr.get("body", ""))
        if body:
            lines.append(f"  {body}")
    return "\n".join(lines)


async def run(repo: str,
              config_path: str | None,
              issues: int,
              prs: int,
              inject_failure: bool,
              mode: str) -> None:
    settings = load_config(Path(config_path)) if config_path else load_config()
    settings.mode = OperatingMode(mode)

    model_client = get_model_client(settings)
    provider_settings = settings.models.providers.get(settings.models.default)
    if provider_settings and not provider_settings.api_key:
        model_client = None
    if not model_client:
        print("Warning: No model client configured. Falling back to template-based hypotheses.")

    db = get_db_session(settings)
    db_url = settings.database_url if db else None
    skip_db = db is None

    issues_data = fetch_issues(repo, issues)
    prs_data = fetch_prs(repo, prs)
    focus = build_focus(repo, issues_data, prs_data)

    tinman = await create_tinman(
        model_client=model_client,
        db_url=db_url,
        mode=settings.mode,
        skip_db=skip_db,
    )

    try:
        results = await tinman.research_cycle(
            focus=focus,
            max_hypotheses=5,
            max_experiments=3,
            runs_per_experiment=2,
        )
    finally:
        await tinman.close()

    if inject_failure and not results["failures"] and db:
        from tinman.memory.graph import MemoryGraph
        from tinman.memory.models import Node, NodeType
        with db.session() as session:
            graph = MemoryGraph(session)
            run_node = Node(
                node_type=NodeType.RUN,
                data={
                    "experiment_id": "demo_injection",
                    "total_runs": 1,
                    "failures_triggered": 1,
                    "reproduction_rate": 1.0,
                    "hypothesis_validated": True,
                    "notes": "Injected failure for demo reporting.",
                },
            )
            graph.add_node(run_node)
            graph.record_failure(
                run_id=run_node.id,
                primary_class="tool_use",
                secondary_class="demo_injection",
                severity="S2",
                trigger_signature=["demo_injection"],
                reproducibility=1.0,
                description="Synthetic demo failure to populate reports.",
                is_novel=True,
                is_synthetic=True,
            )

    print("\n=== Demo Results ===")
    print(f"Hypotheses: {len(results['hypotheses'])}")
    print(f"Experiments: {len(results['experiments'])}")
    print(f"Failures: {len(results['failures'])}")
    print(f"Interventions: {len(results['interventions'])}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="moltbot/moltbot")
    parser.add_argument("--config", default=None)
    parser.add_argument("--issues", type=int, default=10)
    parser.add_argument("--prs", type=int, default=3)
    parser.add_argument("--inject-failure", action="store_true",
                        help="Inject a synthetic failure if none are found")
    parser.add_argument("--mode", default="lab",
                        choices=["lab", "shadow", "production"],
                        help="Operating mode for the demo run")
    args = parser.parse_args()
    asyncio.run(run(
        args.repo,
        args.config,
        args.issues,
        args.prs,
        args.inject_failure,
        args.mode,
    ))


if __name__ == "__main__":
    main()
