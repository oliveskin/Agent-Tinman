"""Main CLI entry point for Tinman."""

import asyncio
from pathlib import Path

import click
from sqlalchemy.engine.url import make_url

from ..config.modes import OperatingMode
from ..config.settings import Settings, load_settings
from ..db.connection import Database, check_database, ensure_database
from ..utils import get_logger

logger = get_logger("cli")


def get_db_session(settings: Settings):
    """Get database session if configured."""
    if settings.database_url:
        try:
            db = Database(settings.database_url)
            db.create_tables()
            return db
        except Exception as e:
            logger.warning(f"Could not connect to database: {e}")
    return None


def get_model_client(settings: Settings):
    """Get model client based on settings."""
    provider = settings.model_provider
    provider_settings = settings.models.providers.get(provider)
    api_key = provider_settings.api_key if provider_settings else None
    base_url = provider_settings.base_url if provider_settings else None
    default_model = provider_settings.model if provider_settings else None

    if provider == "openai":
        from ..integrations.openai_client import OpenAIClient

        return OpenAIClient(api_key=api_key, base_url=base_url, default_model=default_model)
    elif provider == "anthropic":
        from ..integrations.anthropic_client import AnthropicClient

        return AnthropicClient(api_key=api_key, base_url=base_url, default_model=default_model)
    elif provider == "openrouter":
        from ..integrations.openrouter_client import OpenRouterClient

        return OpenRouterClient(api_key=api_key, default_model=default_model)
    elif provider == "google":
        from ..integrations.google_client import GoogleClient

        return GoogleClient(api_key=api_key, default_model=default_model)
    elif provider == "groq":
        from ..integrations.groq_client import GroqClient

        return GroqClient(api_key=api_key, default_model=default_model)
    elif provider == "together":
        from ..integrations.together_client import TogetherClient

        return TogetherClient(api_key=api_key, default_model=default_model)
    elif provider == "ollama":
        from ..integrations.ollama_client import OllamaClient

        return OllamaClient(base_url=base_url, default_model=default_model)

    return None


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to configuration file")
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["lab", "shadow", "production"]),
    default="lab",
    help="Operating mode",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, config: str | None, mode: str, verbose: bool):
    """
    Tinman - Forward-Deployed Research Agent

    An autonomous AI researcher that discovers and addresses failure modes
    in AI systems through systematic experimentation.
    """
    ctx.ensure_object(dict)

    # Load settings
    if config:
        settings = load_settings(Path(config))
    else:
        settings = load_settings()

    # Override mode from CLI
    settings.mode = OperatingMode(mode)

    ctx.obj["settings"] = settings
    ctx.obj["verbose"] = verbose

    if verbose:
        click.echo(f"Mode: {settings.mode.value}")


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize Tinman in the current directory."""
    settings = ctx.obj["settings"]

    click.echo("Initializing Tinman...")

    # Create config directory
    config_dir = Path(".tinman")
    config_dir.mkdir(exist_ok=True)

    # Create default config
    config_file = config_dir / "config.yaml"
    if not config_file.exists():
        default_config = """# Tinman Configuration
mode: lab

database:
  url: sqlite:///tinman.db

models:
  default: openai
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4-turbo-preview
    anthropic:
      api_key: ${ANTHROPIC_API_KEY}
      model: claude-3-5-sonnet-20241022
    openrouter:
      api_key: ${OPENROUTER_API_KEY}
      model: deepseek/deepseek-chat
    google:
      api_key: ${GOOGLE_API_KEY}
      model: gemini-2.5-flash

experiments:
  max_parallel: 5
  default_timeout_seconds: 300
  cost_limit_usd: 10.0

risk:
  auto_approve_safe: true
  block_on_destructive: true
"""
        config_file.write_text(default_config)
        click.echo(f"Created {config_file}")
    else:
        click.echo(f"Config already exists at {config_file}")

    # Create .env from template if available
    env_file = Path(".env")
    env_template = Path(".env.example")
    if not env_file.exists() and env_template.exists():
        env_file.write_text(env_template.read_text())
        click.echo("Created .env from .env.example (fill in your keys before running).")
    elif not env_file.exists():
        env_file.write_text(
            "# Tinman env\n"
            "# Fill in the keys you use.\n\n"
            "OPENAI_API_KEY=\n"
            "ANTHROPIC_API_KEY=\n"
            "GEMINI_API_KEY=\n"
            "GOOGLE_API_KEY=\n"
            "OPENROUTER_API_KEY=\n"
            "GROQ_API_KEY=\n"
            "TOGETHER_API_KEY=\n"
            "OLLAMA_BASE_URL=\n\n"
            "GITHUB_TOKEN=\n"
            "HUGGINGFACE_API_KEY=\n"
            "REPLICATE_API_TOKEN=\n"
            "FAL_API_KEY=\n"
        )
        click.echo("Created .env template (fill in your keys before running).")

    click.echo("Initialization complete.")


@cli.group()
def db():
    """Database utilities."""
    pass


@db.command("init")
@click.pass_context
def db_init(ctx):
    """Create the database and tables if missing."""
    settings = ctx.obj["settings"]
    if not settings.database_url:
        click.echo("No database URL configured.", err=True)
        raise SystemExit(1)

    try:
        info = ensure_database(settings.database_url)
        created = "created" if info.get("created") else "already exists"
        click.echo(f"{info['backend']} database {created}: {info['database']}")
    except Exception as e:
        click.echo(f"Database init failed: {e}", err=True)
        raise SystemExit(1)


@db.command("check")
@click.pass_context
def db_check(ctx):
    """Check database connectivity and tables."""
    settings = ctx.obj["settings"]
    if not settings.database_url:
        click.echo("No database URL configured.", err=True)
        raise SystemExit(1)

    try:
        info = check_database(settings.database_url)
        click.echo(f"Connected: {info['connected']}")
        click.echo(f"Tables: {', '.join(info['tables']) if info['tables'] else '(none)'}")
    except Exception as e:
        click.echo(f"Database check failed: {e}", err=True)
        raise SystemExit(1)


@cli.command()
@click.option("--focus", "-f", help="Focus area for research")
@click.option("--max-hypotheses", "-h", default=5, help="Maximum hypotheses to generate")
@click.option("--max-experiments", "-e", default=3, help="Maximum experiments to run")
@click.option("--runs-per-experiment", "-r", default=5, help="Runs per experiment")
@click.pass_context
def research(
    ctx, focus: str | None, max_hypotheses: int, max_experiments: int, runs_per_experiment: int
):
    """Run a complete research cycle."""
    settings = ctx.obj["settings"]

    click.echo(f"Starting research cycle (mode: {settings.mode.value})...")
    if focus:
        click.echo(f"Focus: {focus}")

    async def run():
        from ..tinman import create_tinman

        model_client = get_model_client(settings)
        if not model_client:
            click.echo("Warning: No model client configured. Using simulation mode.", err=True)

        db = get_db_session(settings)
        db_url = settings.database_url if db else None
        skip_db = db is None

        tinman = await create_tinman(
            model_client=model_client,
            db_url=db_url,
            mode=settings.mode,
            skip_db=skip_db,
        )

        try:
            results = await tinman.research_cycle(
                focus=focus,
                max_hypotheses=max_hypotheses,
                max_experiments=max_experiments,
                runs_per_experiment=runs_per_experiment,
            )

            # Display results
            click.echo("\n" + "=" * 50)
            click.echo("RESEARCH CYCLE COMPLETE")
            click.echo("=" * 50)

            click.echo(f"\nHypotheses generated: {len(results['hypotheses'])}")
            for h in results["hypotheses"][:5]:
                click.echo(
                    f"  - [{h['priority']}] {h['target_surface']}: {h['expected_failure'][:50]}..."
                )

            click.echo(f"\nExperiments run: {len(results['experiments'])}")
            for e in results["experiments"][:5]:
                click.echo(f"  - {e['name']} ({e['stress_type']})")

            click.echo(f"\nFailures discovered: {len(results['failures'])}")
            for f in results["failures"]:
                click.echo(
                    f"  - [{f['severity']}] {f['primary_class']}: {f['description'][:60]}..."
                )
                if f.get("key_insight"):
                    click.echo(f"    Insight: {f['key_insight'][:80]}...")

            click.echo(f"\nInterventions proposed: {len(results['interventions'])}")
            for i in results["interventions"]:
                click.echo(
                    f"  - [{i['risk_tier']}] {i['name']}: {i.get('description', '')[:50]}..."
                )

            if results["simulations"]:
                click.echo(f"\nSimulations run: {len(results['simulations'])}")

        finally:
            await tinman.close()

    asyncio.run(run())


@cli.command()
@click.option("--target", "-t", help="Target surface to investigate")
@click.option("--limit", "-l", default=10, help="Maximum hypotheses to generate")
@click.pass_context
def hypothesize(ctx, target: str | None, limit: int):
    """Generate failure hypotheses."""
    settings = ctx.obj["settings"]

    click.echo(f"Generating hypotheses (mode: {settings.mode.value})...")

    async def run():
        from ..agents.base import AgentContext
        from ..agents.hypothesis_engine import HypothesisEngine
        from ..reasoning.adaptive_memory import AdaptiveMemory
        from ..reasoning.llm_backbone import LLMBackbone

        model_client = get_model_client(settings)
        llm = LLMBackbone(model_client=model_client) if model_client else None

        db = get_db_session(settings)
        graph = None
        if db:
            from ..memory.graph import MemoryGraph

            with db.session() as session:
                graph = MemoryGraph(session)

        engine = HypothesisEngine(
            graph=graph,
            llm_backbone=llm,
            adaptive_memory=AdaptiveMemory(),
        )
        context = AgentContext(mode=settings.mode)

        result = await engine.run(context)

        if result.success:
            hypotheses = result.data.get("hypotheses", [])
            used_llm = result.data.get("used_llm_reasoning", False)

            click.echo(f"\nGenerated {len(hypotheses)} hypotheses")
            click.echo(f"(LLM reasoning: {'enabled' if used_llm else 'disabled'})\n")

            for i, h in enumerate(hypotheses[:limit], 1):
                click.echo(f"{i}. [{h['priority'].upper()}] {h['target_surface']}")
                click.echo(f"   Expected: {h['expected_failure']}")
                click.echo(f"   Class: {h['failure_class']}")
                click.echo(f"   Confidence: {h['confidence']:.0%}")
                if h.get("rationale"):
                    click.echo(f"   Rationale: {h['rationale'][:100]}...")
                click.echo()
        else:
            click.echo(f"Error: {result.error}", err=True)

    asyncio.run(run())


@cli.command()
@click.argument("hypothesis_id", required=False)
@click.option("--all", "-a", "run_all", is_flag=True, help="Run all pending experiments")
@click.option("--runs", "-r", default=5, help="Number of runs per experiment")
@click.pass_context
def experiment(ctx, hypothesis_id: str | None, run_all: bool, runs: int):
    """Design and run experiments."""
    settings = ctx.obj["settings"]

    click.echo(f"Running experiments (mode: {settings.mode.value})...")

    async def run():
        from ..agents.base import AgentContext
        from ..agents.experiment_architect import ExperimentArchitect, ExperimentDesign
        from ..agents.experiment_executor import ExperimentExecutor
        from ..agents.hypothesis_engine import Hypothesis, HypothesisEngine
        from ..reasoning.adaptive_memory import AdaptiveMemory
        from ..reasoning.llm_backbone import LLMBackbone
        from ..taxonomy.failure_types import FailureClass

        model_client = get_model_client(settings)
        llm = LLMBackbone(model_client=model_client) if model_client else None

        db = get_db_session(settings)
        graph = None
        if db:
            from ..memory.graph import MemoryGraph

            with db.session() as session:
                graph = MemoryGraph(session)

        context = AgentContext(mode=settings.mode)

        # Generate hypotheses first
        hypothesis_engine = HypothesisEngine(
            graph=graph,
            llm_backbone=llm,
            adaptive_memory=AdaptiveMemory(),
        )
        h_result = await hypothesis_engine.run(context)

        if not h_result.success:
            click.echo(f"Failed to generate hypotheses: {h_result.error}", err=True)
            return

        hypotheses_data = h_result.data.get("hypotheses", [])
        if not hypotheses_data:
            click.echo("No hypotheses generated.")
            return

        click.echo(f"Generated {len(hypotheses_data)} hypotheses")

        # Convert to Hypothesis objects
        hypotheses = [
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
            for h in hypotheses_data[:5]
        ]

        # Design experiments
        architect = ExperimentArchitect(graph=graph, llm_backbone=llm)
        arch_result = await architect.run(context, hypotheses=hypotheses)

        if not arch_result.success:
            click.echo(f"Failed to design experiments: {arch_result.error}", err=True)
            return

        experiments_data = arch_result.data.get("experiments", [])
        click.echo(f"Designed {len(experiments_data)} experiments")

        # Convert to ExperimentDesign objects
        experiment_objects = [
            ExperimentDesign(
                id=e["id"],
                hypothesis_id=e["hypothesis_id"],
                name=e["name"],
                stress_type=e["stress_type"],
                mode=e["mode"],
                parameters=e["parameters"],
                estimated_runs=runs,
                test_cases=e.get("test_cases", []),
            )
            for e in experiments_data[:3]
        ]

        # Execute experiments
        executor = ExperimentExecutor(
            graph=graph,
            model_client=model_client,
            llm_backbone=llm,
        )
        exec_result = await executor.run(context, experiments=experiment_objects)

        if exec_result.success:
            click.echo(f"\n{'=' * 50}")
            click.echo("EXPERIMENT RESULTS")
            click.echo("=" * 50)
            click.echo(f"\nTotal runs: {exec_result.data.get('total_runs', 0)}")
            click.echo(f"Failures found: {exec_result.data.get('failures_found', 0)}")

            for r in exec_result.data.get("results", []):
                click.echo(f"\n  Experiment: {r['experiment_id'][:8]}...")
                click.echo(f"    Runs: {r['total_runs']}")
                click.echo(f"    Failures: {r['failures_triggered']}")
                click.echo(f"    Reproduction rate: {r['reproduction_rate']:.0%}")
                click.echo(f"    Hypothesis validated: {'✓' if r['hypothesis_validated'] else '✗'}")
        else:
            click.echo(f"Experiment execution failed: {exec_result.error}", err=True)

    asyncio.run(run())


@cli.command()
@click.option(
    "--severity",
    "-s",
    type=click.Choice(["S0", "S1", "S2", "S3", "S4"]),
    help="Minimum severity to show",
)
@click.option("--unresolved", "-u", is_flag=True, help="Show only unresolved failures")
@click.option("--limit", "-l", default=20, help="Maximum failures to show")
@click.pass_context
def failures(ctx, severity: str | None, unresolved: bool, limit: int):
    """List discovered failures."""
    settings = ctx.obj["settings"]

    click.echo("Listing failures...")

    db = get_db_session(settings)
    if not db:
        click.echo(
            "\nNo database configured. Use --config to specify a config with database URL.",
            err=True,
        )
        click.echo("Or run 'tinman init' to create a default configuration.")
        return

    from ..memory.graph import MemoryGraph

    with db.session() as session:
        graph = MemoryGraph(session)

        if severity:
            failures_list = graph.find_failures_by_severity(severity)
        elif unresolved:
            failures_list = graph.find_unresolved_failures()
        else:
            failures_list = graph.get_failures(valid_only=True, limit=limit)

        if not failures_list:
            click.echo("\nNo failures found in database.")
            click.echo("Run 'tinman research' or 'tinman experiment' to discover failures.")
            return

        click.echo(f"\nFound {len(failures_list)} failure(s):\n")

        for f in failures_list[:limit]:
            data = f.data
            click.echo(
                f"[{data.get('severity', 'S?')}] {f.id[:8]}... - {data.get('primary_class', 'unknown')}"
            )
            if data.get("secondary_class"):
                click.echo(f"     Secondary: {data['secondary_class']}")
            if data.get("description"):
                click.echo(f"     {data['description'][:80]}...")
            click.echo(f"     Reproducibility: {data.get('reproducibility', 0):.0%}")
            click.echo(f"     Resolved: {'✓' if data.get('is_resolved') else '✗'}")
            if data.get("trigger_signature"):
                click.echo(f"     Triggers: {', '.join(data['trigger_signature'][:3])}")
            click.echo()


@cli.command()
@click.argument("failure_id", required=False)
@click.option(
    "--all",
    "-a",
    "for_all",
    is_flag=True,
    help="Generate interventions for all unresolved failures",
)
@click.pass_context
def intervene(ctx, failure_id: str | None, for_all: bool):
    """Generate intervention recommendations."""
    settings = ctx.obj["settings"]

    click.echo(f"Generating interventions (mode: {settings.mode.value})...")

    async def run():
        from ..agents.base import AgentContext
        from ..agents.failure_discovery import DiscoveredFailure
        from ..agents.intervention_engine import InterventionEngine
        from ..reasoning.llm_backbone import LLMBackbone
        from ..taxonomy.failure_types import FailureClass, Severity

        model_client = get_model_client(settings)
        llm = LLMBackbone(model_client=model_client) if model_client else None

        db = get_db_session(settings)
        if not db:
            click.echo("\nNo database configured.", err=True)
            return

        from ..memory.graph import MemoryGraph

        with db.session() as session:
            graph = MemoryGraph(session)

            # Get failures to intervene on
            if failure_id:
                failure_node = graph.get_node(failure_id)
                if not failure_node:
                    click.echo(f"Failure {failure_id} not found.", err=True)
                    return
                failure_nodes = [failure_node]
            elif for_all:
                failure_nodes = graph.find_unresolved_failures()
            else:
                failure_nodes = graph.get_failures(valid_only=True, limit=5)

            if not failure_nodes:
                click.echo("\nNo failures found to intervene on.")
                click.echo("Run 'tinman research' or 'tinman experiment' first.")
                return

            click.echo(f"Found {len(failure_nodes)} failure(s) to address")

            # Convert to DiscoveredFailure objects
            failures = []
            for f in failure_nodes:
                data = f.data
                try:
                    failures.append(
                        DiscoveredFailure(
                            id=f.id,
                            primary_class=FailureClass(data.get("primary_class", "reasoning")),
                            severity=Severity[data.get("severity", "S2")],
                            description=data.get("description", ""),
                            trigger_signature=data.get("trigger_signature", []),
                            reproducibility=data.get("reproducibility", 0.0),
                        )
                    )
                except (ValueError, KeyError) as e:
                    logger.warning(f"Could not parse failure {f.id}: {e}")

            if not failures:
                click.echo("No valid failures to process.", err=True)
                return

            # Run intervention engine
            context = AgentContext(mode=settings.mode)
            engine = InterventionEngine(graph=graph, llm_backbone=llm)

            result = await engine.run(context, failures=failures)

            if result.success:
                interventions = result.data.get("interventions", [])
                used_llm = result.data.get("used_llm_design", False)

                click.echo(f"\n{'=' * 50}")
                click.echo("INTERVENTION RECOMMENDATIONS")
                click.echo(f"(LLM design: {'enabled' if used_llm else 'disabled'})")
                click.echo("=" * 50)

                by_risk = result.data.get("by_risk_tier", {})
                click.echo(
                    f"\nBy risk tier: Safe={by_risk.get('safe', 0)}, Review={by_risk.get('review', 0)}, Block={by_risk.get('block', 0)}"
                )

                for i in interventions:
                    click.echo(f"\n[{i['risk_tier'].upper()}] {i['name']}")
                    click.echo(f"  Type: {i['type']}")
                    click.echo(f"  For failure: {i['failure_id'][:8]}...")
                    if i.get("description"):
                        click.echo(f"  Description: {i['description'][:100]}...")
                    if i.get("rationale"):
                        click.echo(f"  Rationale: {i['rationale'][:100]}...")
                    if i.get("payload"):
                        click.echo(f"  Payload: {str(i['payload'])[:80]}...")
            else:
                click.echo(f"Failed to generate interventions: {result.error}", err=True)

    asyncio.run(run())


@cli.command()
@click.argument("message")
@click.pass_context
def discuss(ctx, message: str):
    """Have a conversation with Tinman about research findings."""
    settings = ctx.obj["settings"]

    async def run():
        from ..tinman import create_tinman

        model_client = get_model_client(settings)
        if not model_client:
            click.echo(
                "Discussion requires a model client. Configure openai or anthropic.", err=True
            )
            return

        db = get_db_session(settings)
        db_url = settings.database_url if db else None

        tinman = await create_tinman(
            model_client=model_client,
            db_url=db_url,
            mode=settings.mode,
        )

        try:
            response = await tinman.discuss(message)
            click.echo(f"\nTinman: {response}")
        finally:
            await tinman.close()

    asyncio.run(run())


@cli.command()
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "markdown", "json", "demo"]),
    default="text",
    help="Output format",
)
@click.option("--output", "-o", type=click.Path(), help="Output file")
@click.option("--days", "-d", default=7, help="Report period in days")
@click.option(
    "--exclude-demo-failures", is_flag=True, help="Exclude synthetic demo failures from reports"
)
@click.pass_context
def report(ctx, format: str, output: str | None, days: int, exclude_demo_failures: bool):
    """Generate a research report."""
    settings = ctx.obj["settings"]

    click.echo("Generating report...")

    async def run():
        db = get_db_session(settings)
        graph = None
        if db:
            from ..memory.graph import MemoryGraph

            with db.session() as session:
                graph = MemoryGraph(session)

        model_client = get_model_client(settings)

        if format == "demo":
            model_client = None

        # Use InsightSynthesizer for rich reports if LLM available
        if model_client:
            from ..reasoning.adaptive_memory import AdaptiveMemory
            from ..reasoning.insight_synthesizer import InsightSynthesizer
            from ..reasoning.llm_backbone import LLMBackbone

            llm = LLMBackbone(model_client=model_client)
            synthesizer = InsightSynthesizer(
                llm_backbone=llm,
                graph=graph,
                adaptive_memory=AdaptiveMemory(),
            )

            brief = await synthesizer.generate_brief(
                period_days=days,
                exclude_demo_failures=exclude_demo_failures,
            )

            if format == "markdown":
                content = f"""# {brief.title}

## Executive Summary

{brief.executive_summary}

## Key Insights

"""
                for insight in brief.key_insights:
                    content += f"### {insight.title}\n\n{insight.content}\n\n"

                content += "## Patterns Observed\n\n"
                for pattern in brief.patterns:
                    content += f"- {pattern}\n"

                content += "\n## Recommendations\n\n"
                for rec in brief.recommendations:
                    content += f"- **{rec.get('action', '')}** ({rec.get('priority', 'medium')}): {rec.get('rationale', '')}\n"

                content += "\n## Open Questions\n\n"
                for q in brief.open_questions:
                    content += f"- {q}\n"

                if brief.narrative:
                    content += f"\n## Research Narrative\n\n{brief.narrative}\n"

            elif format == "json":
                import json

                content = json.dumps(
                    {
                        "title": brief.title,
                        "executive_summary": brief.executive_summary,
                        "key_insights": [
                            {"title": i.title, "content": i.content} for i in brief.key_insights
                        ],
                        "patterns": brief.patterns,
                        "recommendations": brief.recommendations,
                        "open_questions": brief.open_questions,
                        "narrative": brief.narrative,
                        "period_start": brief.period_start.isoformat()
                        if brief.period_start
                        else None,
                        "period_end": brief.period_end.isoformat() if brief.period_end else None,
                    },
                    indent=2,
                )
            else:
                content = f"""
{brief.title}
{"=" * len(brief.title)}

Executive Summary:
{brief.executive_summary}

Key Insights:
"""
                for insight in brief.key_insights:
                    content += f"  - {insight.title}: {insight.content[:100]}...\n"

                content += "\nPatterns:\n"
                for pattern in brief.patterns:
                    content += f"  - {pattern}\n"

                content += "\nRecommendations:\n"
                for rec in brief.recommendations:
                    content += f"  - [{rec.get('priority', 'medium')}] {rec.get('action', '')}\n"

                content += "\nOpen Questions:\n"
                for q in brief.open_questions:
                    content += f"  - {q}\n"

        else:
            # Fallback to basic reporter
            from ..reporting.lab_reporter import LabReporter

            reporter = LabReporter(graph=graph)
            lab_report = reporter.generate(exclude_demo_failures=exclude_demo_failures)

            if format == "demo":
                content = reporter.to_demo_markdown(lab_report)
            elif format == "markdown":
                content = reporter.to_markdown(lab_report)
            elif format == "json":
                import json

                content = json.dumps(reporter.to_dict(lab_report), indent=2)
            else:
                content = f"""
Tinman Lab Report
=================

Generated: {lab_report.generated_at.isoformat()}

Summary:
  Hypotheses tested: {lab_report.hypotheses_tested}
  Experiments run: {lab_report.experiments_run}
  Failures discovered: {lab_report.failures_discovered}
  Novel failures: {lab_report.novel_failures}
  Interventions proposed: {lab_report.interventions_proposed}

Key Findings:
"""
                for finding in lab_report.key_findings:
                    content += f"  - {finding}\n"

                content += "\nRecommendations:\n"
                for rec in lab_report.recommendations:
                    content += f"  - {rec}\n"

        if output:
            Path(output).write_text(content)
            click.echo(f"Report written to {output}")
        else:
            click.echo(content)

    asyncio.run(run())


@cli.command()
@click.option(
    "--format",
    "-f",
    type=click.Choice(["json", "prometheus"]),
    default="json",
    help="Output format",
)
@click.pass_context
def health(ctx, format: str):
    """Check system health."""
    settings = ctx.obj["settings"]

    from ..reporting.ops_reporter import OpsReporter

    db = get_db_session(settings)
    graph = None
    if db:
        from ..memory.graph import MemoryGraph

        with db.session() as session:
            graph = MemoryGraph(session)

    reporter = OpsReporter(graph=graph, mode=settings.mode)
    ops_report = reporter.generate()

    if format == "prometheus":
        click.echo(reporter.to_prometheus(ops_report))
    else:
        import json

        click.echo(json.dumps(reporter.to_json(ops_report), indent=2))


@cli.command()
@click.pass_context
def status(ctx):
    """Show current Tinman status."""
    settings = ctx.obj["settings"]

    db = get_db_session(settings)
    db_status = "connected" if db else "not configured"

    model_client = get_model_client(settings)
    model_status = f"{settings.model_provider} configured" if model_client else "not configured"

    click.echo(f"""
Tinman Status
=============

Mode: {settings.mode.value}
Database: {db_status}
Model Provider: {model_status}

Configuration:
  Database URL: {settings.database_url or "(not set)"}
  Model Provider: {settings.model_provider}
  Max hypotheses per run: {settings.max_hypotheses_per_run}
  Max experiments per hypothesis: {settings.max_experiments_per_hypothesis}
  Default runs per experiment: {settings.default_runs_per_experiment}
""")

    if db:
        from ..memory.graph import MemoryGraph

        with db.session() as session:
            graph = MemoryGraph(session)
            stats = graph.get_stats()

            click.echo("Graph Statistics:")
            for node_type, count in stats.items():
                if count > 0:
                    click.echo(f"  {node_type}: {count}")


@cli.command("demo-reset-db")
@click.pass_context
def demo_reset_db(ctx):
    """Delete the local SQLite demo database (if configured)."""
    settings = ctx.obj["settings"]
    db_url = settings.database_url
    if not db_url or not db_url.startswith("sqlite"):
        click.echo("Demo reset only supports SQLite database URLs.")
        return


    parsed = make_url(db_url)
    db_path = parsed.database
    if not db_path:
        click.echo("SQLite database path is empty.")
        return

    path = Path(db_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.exists():
        click.echo(f"No demo database found at {path}")
        return

    path.unlink()
    click.echo(f"Deleted demo database: {path}")


@cli.command()
@click.pass_context
def tui(ctx):
    """
    Launch the interactive Terminal User Interface.

    A retro-style TUI for interactive research sessions with
    real-time status, approval dialogs, and chat interface.
    """
    settings = ctx.obj["settings"]

    click.echo("Launching Tinman TUI...")
    click.echo("Press F10 or Ctrl+C to exit.")

    from ..tui import run_tui

    run_tui(settings)


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
