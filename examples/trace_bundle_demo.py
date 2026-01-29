"""Test 1: Run Tinman cycle using a fixed synthetic trace bundle."""

import argparse
import asyncio
import json
from pathlib import Path

from tinman.config import load_config
from tinman.config.modes import OperatingMode
from tinman.cli.main import get_db_session, get_model_client
from tinman.tinman import create_tinman
from tinman.agents.hypothesis_engine import Hypothesis
from tinman.agents.experiment_architect import ExperimentDesign
from tinman.agents.experiment_executor import ExperimentResult, RunResult
from tinman.agents.failure_discovery import DiscoveredFailure
from tinman.taxonomy.failure_types import FailureClass, Severity
from tinman.reporting.lab_reporter import LabReporter


def _load_bundle(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def run(config_path: str | None, bundle_path: str) -> None:
    settings = load_config(Path(config_path)) if config_path else load_config()
    settings.mode = OperatingMode.LAB

    model_client = get_model_client(settings)
    provider_settings = settings.models.providers.get(settings.models.default)
    if provider_settings and not provider_settings.api_key:
        model_client = None
    db = get_db_session(settings)
    db_url = settings.database_url if db else None
    skip_db = db is None

    tinman = await create_tinman(
        model_client=model_client,
        db_url=db_url,
        mode=settings.mode,
        skip_db=skip_db,
    )

    bundle = _load_bundle(Path(bundle_path))

    context = tinman.hypothesis_engine._context or None
    if context is None:
        from tinman.agents.base import AgentContext
        context = AgentContext(mode=settings.mode)

    h_result = await tinman.hypothesis_engine.run(context)
    hypotheses = []
    if h_result.success:
        for h in h_result.data.get("hypotheses", [])[:1]:
            hypotheses.append(
                Hypothesis(
                    id=h["id"],
                    target_surface=h["target_surface"],
                    expected_failure=h["expected_failure"],
                    failure_class=FailureClass(h["failure_class"]),
                    confidence=h["confidence"],
                    priority=h["priority"],
                    rationale=h.get("rationale", ""),
                    suggested_experiment=h.get("suggested_experiment", ""),
                )
            )

    if not hypotheses:
        hypotheses = [
            Hypothesis(
                target_surface="tool_use",
                expected_failure="tool timeout during fetch_url",
                failure_class=FailureClass.TOOL_USE,
                confidence=0.6,
                priority="high",
                rationale="Synthetic trace bundle contains tool errors.",
            )
        ]

    arch_result = await tinman.experiment_architect.run(context, hypotheses=hypotheses)
    experiments = []
    if arch_result.success:
        for e in arch_result.data.get("experiments", [])[:1]:
            experiments.append(
                ExperimentDesign(
                    id=e["id"],
                    hypothesis_id=e["hypothesis_id"],
                    name=e["name"],
                    description=e.get("description", ""),
                    stress_type=e["stress_type"],
                    mode=e["mode"],
                    parameters=e.get("parameters", {}),
                    constraints=e.get("constraints", {}),
                    estimated_runs=e.get("estimated_runs", 2),
                )
            )

    if not experiments:
        experiments = [
            ExperimentDesign(
                hypothesis_id=hypotheses[0].id,
                name="trace_bundle_tool_use",
                description="Synthetic trace bundle test",
                stress_type="tool_injection",
                mode="single",
                parameters={},
                constraints={},
                estimated_runs=2,
            )
        ]

    experiment_results = []
    for exp in experiments:
        result = ExperimentResult(
            experiment_id=exp.id,
            hypothesis_id=exp.hypothesis_id,
        )
        for i, run in enumerate(bundle.get("runs", []), start=1):
            run_result = RunResult(
                id=run.get("run_id", f"run-{i}"),
                experiment_id=exp.id,
                run_number=i,
                success=not run.get("failure_triggered", False),
                failure_triggered=run.get("failure_triggered", False),
                failure_description=run.get("failure_description") or None,
                trace=run.get("trace", {}),
            )
            result.runs.append(run_result)
            result.total_runs += 1
            if run_result.failure_triggered:
                result.failures_triggered += 1
        if result.total_runs:
            result.reproduction_rate = result.failures_triggered / result.total_runs
        result.hypothesis_validated = result.failures_triggered > 0
        experiment_results.append(result)

    if tinman.graph:
        from tinman.memory.models import Node, NodeType
        for result in experiment_results:
            for run in result.runs:
                if tinman.graph.get_node(run.id):
                    continue
                run_node = Node(
                    id=run.id,
                    node_type=NodeType.RUN,
                    data={
                        "experiment_id": result.experiment_id,
                        "trace": run.trace,
                    },
                )
                tinman.graph.add_node(run_node)

    failures = []
    interventions = []
    if tinman.graph and experiment_results:
        run_id = experiment_results[0].runs[0].id
        failure_node = tinman.graph.record_failure(
            run_id=run_id,
            primary_class="tool_use",
            secondary_class="timeout",
            severity="S2",
            trigger_signature=["tool_errors:1"],
            reproducibility=1.0,
            description="Synthetic failure from fixed trace bundle.",
            is_novel=True,
            is_synthetic=True,
        )
        failures.append(
            DiscoveredFailure(
                id=failure_node.id,
                primary_class=FailureClass.TOOL_USE,
                secondary_class="timeout",
                severity=Severity.S2,
                description="Synthetic failure from fixed trace bundle.",
                trigger_signature=["tool_errors:1"],
                reproducibility=1.0,
                is_novel=True,
            )
        )

        intervention_node = tinman.graph.record_intervention(
            failure_id=failure_node.id,
            intervention_type="tool_restriction",
            payload={"mode": "allowlist", "allowed_tools": ["fetch_url"]},
            expected_gains={"failure_reduction": 0.5},
            expected_regressions={"latency_increase": 0.1},
            risk_tier="review",
        )
        interventions.append({"id": intervention_node.id, "type": "tool_restriction"})

    reporter = LabReporter(graph=tinman.graph)
    report = reporter.generate()

    print("\n=== Trace Bundle Results ===")
    print(f"Hypotheses: {len(hypotheses)}")
    print(f"Experiments: {len(experiments)}")
    print(f"Failures: {len(failures)}")
    print(f"Interventions: {len(interventions)}")
    print("\n=== Demo Report ===")
    print(reporter.to_demo_markdown(report))

    await tinman.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--bundle", default=str(Path(__file__).parent / "trace_bundle.json"))
    args = parser.parse_args()
    asyncio.run(run(args.config, args.bundle))


if __name__ == "__main__":
    main()
