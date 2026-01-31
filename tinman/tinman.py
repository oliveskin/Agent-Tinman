"""
Tinman - The AI Forward Deployed Researcher

This is the main interface for Tinman - an autonomous AI researcher
that discovers and addresses failure modes in AI systems.

Tinman can:
- Generate hypotheses about potential failures
- Design and run experiments to test those hypotheses
- Analyze failures with deep understanding
- Propose and simulate interventions
- Communicate findings in natural language
- Learn from its discoveries over time
- Collaborate with human researchers
"""

from dataclasses import dataclass, field
from typing import Any

from .agents.base import AgentContext
from .agents.experiment_architect import ExperimentArchitect, ExperimentDesign
from .agents.experiment_executor import ExperimentExecutor
from .agents.failure_discovery import FailureDiscoveryAgent
from .agents.hypothesis_engine import Hypothesis, HypothesisEngine
from .agents.intervention_engine import InterventionEngine
from .agents.simulation_engine import SimulationEngine
from .config.modes import Mode, OperatingMode
from .config.settings import Settings
from .core.approval_handler import ApprovalHandler, ApprovalMode, cli_approval_callback
from .core.event_bus import EventBus
from .db.connection import DatabaseConnection
from .integrations.model_client import ModelClient
from .memory.graph import MemoryGraph
from .reasoning.adaptive_memory import AdaptiveMemory
from .reasoning.insight_synthesizer import InsightSynthesizer
from .reasoning.llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode
from .reporting.lab_reporter import LabReporter
from .reporting.ops_reporter import OpsReporter
from .utils import get_logger, utc_now

logger = get_logger("tinman")


@dataclass
class TinmanState:
    """Current state of the Tinman researcher."""

    mode: OperatingMode = OperatingMode.LAB
    session_id: str = ""
    started_at: Any = field(default_factory=utc_now)

    # Counts for this session
    hypotheses_generated: int = 0
    experiments_run: int = 0
    failures_discovered: int = 0
    interventions_proposed: int = 0

    # Current focus
    current_focus: str | None = None


class Tinman:
    """
    The AI Forward Deployed Researcher.

    Tinman is an autonomous researcher that embeds with AI teams
    to discover and address failure modes in AI systems.

    Usage:

        # Initialize
        tinman = Tinman(model_client=my_client)
        await tinman.initialize()

        # Run a research cycle
        result = await tinman.research_cycle()

        # Or have a conversation
        response = await tinman.discuss("What failures have you found?")

        # Generate a report
        report = await tinman.generate_report()
    """

    def __init__(
        self,
        model_client: ModelClient | None = None,
        settings: Settings | None = None,
        mode: OperatingMode = OperatingMode.LAB,
        approval_mode: ApprovalMode = ApprovalMode.INTERACTIVE,
        auto_approve_in_lab: bool = True,
    ):
        self.settings = settings or Settings()
        self.settings.mode = mode

        # State
        self.state = TinmanState(mode=mode)

        # Database and memory
        self.db: DatabaseConnection | None = None
        self.graph: MemoryGraph | None = None

        # Event bus for cross-component communication
        self.event_bus = EventBus()

        # LLM backbone (the brain)
        self.model_client = model_client
        self.llm: LLMBackbone | None = None
        self.adaptive_memory = AdaptiveMemory()

        # Approval handler (HITL interface)
        self.approval_handler = ApprovalHandler(
            mode=Mode(mode.value),
            approval_mode=approval_mode,
            event_bus=self.event_bus,
            auto_approve_in_lab=auto_approve_in_lab,
        )

        # Agents
        self.hypothesis_engine: HypothesisEngine | None = None
        self.experiment_architect: ExperimentArchitect | None = None
        self.experiment_executor: ExperimentExecutor | None = None
        self.failure_discovery: FailureDiscoveryAgent | None = None
        self.intervention_engine: InterventionEngine | None = None
        self.simulation_engine: SimulationEngine | None = None

        # Synthesis
        self.insight_synthesizer: InsightSynthesizer | None = None

        # Reporters
        self.lab_reporter: LabReporter | None = None
        self.ops_reporter: OpsReporter | None = None

        # Conversation history for dialogue
        self._conversation_history: list[dict[str, str]] = []

    async def initialize(self, db_url: str | None = None, skip_db: bool = False) -> None:
        """Initialize Tinman with all components."""
        logger.info(f"Initializing Tinman in {self.state.mode.value} mode")

        # Initialize database if URL provided and not skipping
        if not skip_db and (db_url or self.settings.database_url):
            url = db_url or self.settings.database_url
            self.db = DatabaseConnection(url)
            self.db.create_tables()
            with self.db.session() as session:
                self.graph = MemoryGraph(session)

        # Initialize LLM backbone if model client provided
        if self.model_client:
            self.llm = LLMBackbone(
                model_client=self.model_client,
                temperature=self.settings.model_temperature or 0.7,
            )

        # Initialize agents - all with LLM backbone and approval handler
        self.hypothesis_engine = HypothesisEngine(
            graph=self.graph,
            llm_backbone=self.llm,
            adaptive_memory=self.adaptive_memory,
            event_bus=self.event_bus,
        )

        self.experiment_architect = ExperimentArchitect(
            graph=self.graph,
            llm_backbone=self.llm,
            event_bus=self.event_bus,
        )

        self.experiment_executor = ExperimentExecutor(
            graph=self.graph,
            model_client=self.model_client,
            llm_backbone=self.llm,
            approval_handler=self.approval_handler,  # HITL integration
            event_bus=self.event_bus,
        )

        self.failure_discovery = FailureDiscoveryAgent(
            graph=self.graph,
            llm_backbone=self.llm,
            adaptive_memory=self.adaptive_memory,
            event_bus=self.event_bus,
        )

        self.intervention_engine = InterventionEngine(
            graph=self.graph,
            llm_backbone=self.llm,
            approval_handler=self.approval_handler,  # HITL integration
            event_bus=self.event_bus,
        )

        self.simulation_engine = SimulationEngine(
            graph=self.graph,
            model_client=self.model_client,
            llm_backbone=self.llm,
            approval_handler=self.approval_handler,  # HITL integration
            event_bus=self.event_bus,
        )

        # Initialize insight synthesizer
        if self.llm:
            self.insight_synthesizer = InsightSynthesizer(
                llm_backbone=self.llm,
                graph=self.graph,
                adaptive_memory=self.adaptive_memory,
            )

        # Initialize reporters
        self.lab_reporter = LabReporter(graph=self.graph)
        self.ops_reporter = OpsReporter(
            graph=self.graph,
            mode=self.state.mode,
        )

        # Register CLI fallback for approvals
        self.approval_handler.register_fallback(cli_approval_callback)

        logger.info("Tinman initialized successfully")

    def register_approval_ui(self, callback) -> None:
        """
        Register a UI callback for human approvals.

        The callback should be an async function that:
        - Receives an ApprovalContext
        - Presents it to the user
        - Returns True (approved) or False (rejected)

        For TUI: This is called from the TUI app on startup
        For CLI: The default cli_approval_callback is used
        """
        self.approval_handler.register_ui(callback)
        logger.info("Approval UI callback registered")

    def get_approval_stats(self) -> dict[str, Any]:
        """Get statistics about approval requests."""
        return self.approval_handler.get_stats()

    def get_pending_approvals(self) -> list:
        """Get list of pending approval requests."""
        return self.approval_handler.get_pending()

    async def research_cycle(
        self,
        focus: str | None = None,
        max_hypotheses: int = 5,
        max_experiments: int = 3,
        runs_per_experiment: int = 5,
    ) -> dict[str, Any]:
        """
        Run a complete research cycle.

        This is the core loop:
        1. Generate hypotheses
        2. Design experiments
        3. Execute experiments
        4. Discover failures
        5. Propose interventions
        6. Simulate interventions

        Returns a summary of findings.
        """
        self.state.current_focus = focus
        context = AgentContext(mode=self.state.mode)

        results = {
            "hypotheses": [],
            "experiments": [],
            "failures": [],
            "interventions": [],
            "simulations": [],
        }

        # 1. Generate hypotheses
        logger.info("Generating hypotheses...")
        h_result = await self.hypothesis_engine.run(context)

        if h_result.success:
            hypotheses_data = h_result.data.get("hypotheses", [])[:max_hypotheses]
            results["hypotheses"] = hypotheses_data
            self.state.hypotheses_generated += len(hypotheses_data)

            # Convert to Hypothesis objects for next step
            from .taxonomy.failure_types import FailureClass

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
                for h in hypotheses_data
            ]
        else:
            logger.warning(f"Hypothesis generation failed: {h_result.error}")
            return results

        # 2. Design experiments
        logger.info("Designing experiments...")
        arch_result = await self.experiment_architect.run(context, hypotheses=hypotheses)

        if arch_result.success:
            experiments_data = arch_result.data.get("experiments", [])[:max_experiments]
            results["experiments"] = experiments_data

            # Convert to ExperimentDesign objects
            experiments = [
                ExperimentDesign(
                    id=e["id"],
                    hypothesis_id=e["hypothesis_id"],
                    name=e["name"],
                    stress_type=e["stress_type"],
                    mode=e["mode"],
                    parameters=e["parameters"],
                    estimated_runs=runs_per_experiment,
                )
                for e in experiments_data
            ]
        else:
            logger.warning(f"Experiment design failed: {arch_result.error}")
            return results

        # 3. Execute experiments
        logger.info("Running experiments...")
        exec_result = await self.experiment_executor.run(context, experiments=experiments)

        if exec_result.success:
            self.state.experiments_run += exec_result.data.get("total_runs", 0)

            # Get experiment results for failure discovery
            from .agents.experiment_executor import ExperimentResult

            experiment_results = []
            for r in exec_result.data.get("results", []):
                exp_result = ExperimentResult(
                    experiment_id=r["experiment_id"],
                    hypothesis_id=r["hypothesis_id"],
                    total_runs=r["total_runs"],
                    failures_triggered=r["failures_triggered"],
                    reproduction_rate=r["reproduction_rate"],
                    hypothesis_validated=r["hypothesis_validated"],
                )
                experiment_results.append(exp_result)
        else:
            logger.warning(f"Experiment execution failed: {exec_result.error}")
            return results

        # 4. Discover failures
        if any(r.failures_triggered > 0 for r in experiment_results):
            logger.info("Analyzing failures...")
            disc_result = await self.failure_discovery.run(context, results=experiment_results)

            if disc_result.success:
                failures_data = disc_result.data.get("failures", [])
                results["failures"] = failures_data
                self.state.failures_discovered += len(failures_data)

                # Record outcomes to adaptive memory
                for h in hypotheses:
                    validated = any(
                        r.hypothesis_validated and r.hypothesis_id == h.id
                        for r in experiment_results
                    )
                    self.adaptive_memory.record_hypothesis_outcome(
                        h.failure_class.value,
                        h.target_surface,
                        validated,
                        h.confidence,
                    )

                # 5. Propose interventions
                if failures_data:
                    logger.info("Proposing interventions...")
                    from .agents.failure_discovery import DiscoveredFailure
                    from .taxonomy.failure_types import FailureClass, Severity

                    failures = [
                        DiscoveredFailure(
                            id=f["id"],
                            primary_class=FailureClass(f["primary_class"]),
                            severity=Severity[f["severity"]],
                            description=f["description"],
                            reproducibility=f["reproducibility"],
                        )
                        for f in failures_data
                    ]

                    int_result = await self.intervention_engine.run(context, failures=failures)

                    if int_result.success:
                        interventions_data = int_result.data.get("interventions", [])
                        results["interventions"] = interventions_data
                        self.state.interventions_proposed += len(interventions_data)

                        # 6. Simulate interventions
                        if interventions_data and self.state.mode == OperatingMode.LAB:
                            logger.info("Simulating interventions...")
                            from .agents.intervention_engine import Intervention, InterventionType
                            from .core.risk_evaluator import RiskTier

                            interventions = [
                                Intervention(
                                    id=i["id"],
                                    failure_id=i["failure_id"],
                                    intervention_type=InterventionType(i["type"]),
                                    name=i["name"],
                                    risk_tier=RiskTier(i["risk_tier"]),
                                )
                                for i in interventions_data
                            ]

                            sim_result = await self.simulation_engine.run(
                                context, interventions=interventions
                            )

                            if sim_result.success:
                                results["simulations"] = sim_result.data.get("results", [])

        logger.info(f"Research cycle complete: {len(results['failures'])} failures discovered")

        return results

    async def discuss(self, message: str) -> str:
        """
        Have a conversation with Tinman about research findings.

        Tinman can:
        - Answer questions about discoveries
        - Explain its reasoning
        - Discuss strategic directions
        - Provide recommendations

        Args:
            message: The human's message

        Returns:
            Tinman's response
        """
        if not self.llm:
            return "I need an LLM backbone to have conversations. Please initialize with a model client."

        # Add to conversation history
        self._conversation_history.append({"role": "user", "content": message})

        # Build context with recent observations
        observations = []
        if self.graph:
            failures = self.graph.get_failures(limit=5)
            for f in failures:
                observations.append(
                    f"Recent failure: {f.data.get('primary_class')} - {f.data.get('description', '')[:100]}"
                )

        # Add adaptive memory context
        memory_context = self.adaptive_memory.get_context_for_reasoning()

        context = ReasoningContext(
            mode=ReasoningMode.DIALOGUE,
            observations=observations,
            prior_knowledge=memory_context.get("research_suggestions", []),
            task_description=message,
            history=self._conversation_history[:-1],  # Previous messages
        )

        result = await self.llm.reason(context)

        # Add response to history
        self._conversation_history.append(
            {
                "role": "assistant",
                "content": result.content,
            }
        )

        return result.content

    async def explain_failure(self, failure_id: str) -> str:
        """Get a detailed explanation of a specific failure."""
        if self.insight_synthesizer:
            return await self.insight_synthesizer.explain_failure(failure_id)
        return f"Cannot explain failure {failure_id}: insight synthesizer not available"

    async def suggest_next_steps(self) -> list[str]:
        """Get suggestions for what to research next."""
        suggestions = self.adaptive_memory.get_research_suggestions()

        if self.insight_synthesizer:
            suggestions.extend(await self.insight_synthesizer.suggest_next_steps())

        return suggestions

    async def generate_report(self, format: str = "markdown") -> str:
        """Generate a research report."""
        if not self.lab_reporter:
            return "Reporter not initialized"

        report = self.lab_reporter.generate()

        if format == "markdown":
            return self.lab_reporter.to_markdown(report)
        else:
            import json

            return json.dumps(self.lab_reporter.to_dict(report), indent=2)

    async def health_check(self) -> dict[str, Any]:
        """Check Tinman's health status."""
        if not self.ops_reporter:
            return {"status": "unknown", "error": "Reporter not initialized"}

        report = self.ops_reporter.generate()
        return self.ops_reporter.to_json(report)

    def get_state(self) -> dict[str, Any]:
        """Get current Tinman state."""
        return {
            "mode": self.state.mode.value,
            "session_id": self.state.session_id,
            "started_at": self.state.started_at.isoformat(),
            "hypotheses_generated": self.state.hypotheses_generated,
            "experiments_run": self.state.experiments_run,
            "failures_discovered": self.state.failures_discovered,
            "interventions_proposed": self.state.interventions_proposed,
            "current_focus": self.state.current_focus,
            "has_llm": self.llm is not None,
            "has_graph": self.graph is not None,
        }

    def reset_conversation(self) -> None:
        """Reset conversation history."""
        self._conversation_history = []

    async def close(self) -> None:
        """Clean up resources."""
        if self.db and hasattr(self.db, "disconnect"):
            self.db.disconnect()

        # Save adaptive memory state
        memory_state = self.adaptive_memory.export()
        logger.info(f"Closing Tinman. Learned {len(memory_state['patterns'])} patterns.")


# Convenience function for quick start
async def create_tinman(
    mode: OperatingMode = OperatingMode.LAB,
    model_client: ModelClient | None = None,
    db_url: str | None = None,
    skip_db: bool = False,
) -> Tinman:
    """
    Create and initialize a Tinman instance.

    Args:
        mode: Operating mode (LAB, SHADOW, PRODUCTION)
        model_client: LLM client for reasoning
        db_url: PostgreSQL connection URL (None to skip database)
        skip_db: If True, don't connect to database even if URL in settings

    Returns:
        Initialized Tinman instance
    """
    tinman = Tinman(model_client=model_client, mode=mode)
    actual_url = None if skip_db else db_url
    await tinman.initialize(db_url=actual_url, skip_db=skip_db)
    return tinman
