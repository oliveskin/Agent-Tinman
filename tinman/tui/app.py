"""Tinman TUI - Main Application."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label,
    LoadingIndicator, ProgressBar, Static, TabbedContent, TabPane
)
from textual.screen import ModalScreen
from textual.reactive import reactive

from ..config.modes import OperatingMode
from ..config.settings import Settings, load_settings
from ..core.risk_evaluator import RiskTier
from ..core.approval_handler import ApprovalContext
from ..utils import generate_id

if TYPE_CHECKING:
    from ..tinman import Tinman


# ASCII Art Header
TINMAN_ASCII = """
████████╗██╗███╗   ██╗███╗   ███╗ █████╗ ███╗   ██╗
╚══██╔══╝██║████╗  ██║████╗ ████║██╔══██╗████╗  ██║
   ██║   ██║██╔██╗ ██║██╔████╔██║███████║██╔██╗ ██║
   ██║   ██║██║╚██╗██║██║╚██╔╝██║██╔══██║██║╚██╗██║
   ██║   ██║██║ ╚████║██║ ╚═╝ ██║██║  ██║██║ ╚████║
   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝"""

TINMAN_ASCII_SMALL = """▀█▀ █ █▄ █ █▀▄▀█ ▄▀█ █▄ █
 █  █ █ ▀█ █ ▀ █ █▀█ █ ▀█"""


class ApprovalModal(ModalScreen):
    """Modal for approval requests - integrates with ApprovalHandler."""

    BINDINGS = [
        Binding("y", "approve", "Approve"),
        Binding("n", "reject", "Reject"),
        Binding("d", "details", "Details"),
        Binding("escape", "dismiss", "Cancel"),
    ]

    def __init__(
        self,
        context: Optional[ApprovalContext] = None,
        # Legacy parameters for backwards compatibility
        action: Optional[str] = None,
        risk_tier: Optional[str] = None,
        details: Optional[str] = None,
        cost: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.context = context
        self.result: Optional[bool] = None

        # Support both ApprovalContext and legacy parameters
        if context:
            self.action = context.action_description
            self.risk_tier = f"{context.risk_tier.value.upper()} (Severity: {context.severity.value})"
            self.details = str(context.action_details) if context.action_details else ""
            self.cost = f"${context.estimated_cost_usd:.2f}" if context.estimated_cost_usd else None
            self.rollback = context.rollback_plan
            self.is_reversible = context.is_reversible
        else:
            self.action = action or "Unknown action"
            self.risk_tier = risk_tier or "UNKNOWN"
            self.details = details or ""
            self.cost = cost
            self.rollback = ""
            self.is_reversible = True

    def compose(self) -> ComposeResult:
        with Container(id="approval-modal"):
            yield Static("⚠ APPROVAL REQUIRED ⚠", classes="modal-title")
            yield Static(f"Action: {self.action}", classes="modal-content")
            yield Static(f"Risk: {self.risk_tier}", classes="modal-content")
            if self.cost:
                yield Static(f"Est. Cost: {self.cost}", classes="modal-content")
            if not self.is_reversible:
                yield Static("⚠ WARNING: This action is NOT reversible!", classes="modal-content")
            yield Static("─" * 50, classes="modal-content")
            yield Static(self.details[:300] if self.details else "No details provided", classes="modal-content")
            if self.rollback:
                yield Static(f"Rollback: {self.rollback[:100]}", classes="modal-content")
            with Horizontal(classes="modal-actions"):
                yield Button("[Y] Approve", id="approve-btn", variant="success")
                yield Button("[N] Reject", id="reject-btn", variant="error")
                yield Button("[D] Details", id="details-btn", variant="default")

    def action_approve(self) -> None:
        self.result = True
        if self.context:
            self.context.decision_reason = "Approved via TUI"
        self.dismiss(True)

    def action_reject(self) -> None:
        self.result = False
        if self.context:
            self.context.decision_reason = "Rejected via TUI"
        self.dismiss(False)

    def action_details(self) -> None:
        # Show full details in log
        if self.context:
            self.app.log_message(f"Full details: {self.context.action_details}", "info")
            if self.context.risk_assessment:
                self.app.log_message(f"Risk reasoning: {self.context.risk_assessment.reasoning}", "info")
        else:
            self.app.log_message(f"Details: {self.details}", "info")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve-btn":
            self.action_approve()
        elif event.button.id == "reject-btn":
            self.action_reject()
        elif event.button.id == "details-btn":
            self.action_details()


class TinmanApp(App):
    """Tinman Terminal User Interface."""

    TITLE = "TINMAN FDRA"
    SUB_TITLE = "Forward-Deployed Research Agent"

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("f1", "switch_tab('research')", "Research", show=True),
        Binding("f2", "switch_tab('hypotheses')", "Hypotheses", show=True),
        Binding("f3", "switch_tab('failures')", "Failures", show=True),
        Binding("f4", "switch_tab('intervene')", "Intervene", show=True),
        Binding("f5", "switch_tab('discuss')", "Discuss", show=True),
        Binding("f10", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_log", "Clear Log"),
    ]

    # Reactive state
    mode: reactive[str] = reactive("LAB")
    status: reactive[str] = reactive("IDLE")
    hypothesis_count: reactive[int] = reactive(0)
    experiment_count: reactive[int] = reactive(0)
    failure_count: reactive[int] = reactive(0)
    intervention_count: reactive[int] = reactive(0)

    def __init__(self, settings: Optional[Settings] = None, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings or load_settings()
        self.mode = self.settings.mode.value.upper()
        self.tinman = None  # Lazy load
        self._log_messages: list[tuple[str, str, datetime]] = []
        self._chat_history: list[tuple[str, str]] = []  # (role, message)
        self._pending_approvals: list[dict] = []

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        with Container(id="main-container"):
            # Header with ASCII art
            with Container(id="header"):
                with Horizontal():
                    yield Static(TINMAN_ASCII_SMALL, id="ascii-logo")
                    with Vertical(id="status-line"):
                        yield Static(f"FDRA v0.1.0", id="version")
                        yield Static(f"Mode: {self.mode}", id="mode-display")
                        yield Static(f"Status: {self.status}", id="status-display")

            # Navigation buttons
            with Horizontal(id="nav-bar"):
                yield Button("[F1] Research", id="nav-research", classes="-active")
                yield Button("[F2] Hypotheses", id="nav-hypotheses")
                yield Button("[F3] Failures", id="nav-failures")
                yield Button("[F4] Intervene", id="nav-intervene")
                yield Button("[F5] Discuss", id="nav-discuss")

            # Main content with tabs
            with TabbedContent(id="content"):
                with TabPane("Research", id="research"):
                    yield from self._create_research_panel()
                with TabPane("Hypotheses", id="hypotheses"):
                    yield from self._create_hypotheses_panel()
                with TabPane("Failures", id="failures"):
                    yield from self._create_failures_panel()
                with TabPane("Intervene", id="intervene"):
                    yield from self._create_intervention_panel()
                with TabPane("Discuss", id="discuss"):
                    yield from self._create_discuss_panel()

            # Footer with metrics
            with Horizontal(id="footer"):
                yield Static("Hypotheses: ", classes="metric-label")
                yield Static("0", id="hyp-count", classes="metric-value")
                yield Static(" │ Experiments: ", classes="metric-label")
                yield Static("0", id="exp-count", classes="metric-value")
                yield Static(" │ Failures: ", classes="metric-label")
                yield Static("0", id="fail-count", classes="metric-value")
                yield Static(" │ ", classes="metric-label")
                yield Static("", id="clock", classes="metric-value")

    def _create_research_panel(self):
        """Create the research control panel."""
        yield Static("═══ RESEARCH CONTROL ═══", classes="panel-title")
        yield Static("")
        yield Horizontal(
            Button("▶ Start Research", id="start-research", variant="success"),
            Button("⏸ Pause", id="pause-research", variant="warning"),
            Button("⏹ Stop", id="stop-research", variant="error"),
        )
        yield Static("")
        yield Static("Focus Area:", classes="progress-label")
        yield Input(placeholder="e.g., long_context, tool_use, reasoning", id="focus-input")
        yield Static("")
        yield Static("─── Activity Log ───", classes="panel-title")
        yield ScrollableContainer(
            Static("Ready. Press [F1] or click 'Start Research' to begin.", id="log-content"),
            id="activity-log"
        )

    def _create_hypotheses_panel(self):
        """Create the hypotheses browser panel."""
        yield Static("═══ HYPOTHESES ═══", classes="panel-title")
        table = DataTable(id="hypotheses-table")
        table.add_columns("ID", "Hypothesis", "Confidence", "Status")
        yield table
        yield Static("")
        yield Horizontal(
            Button("Generate New", id="gen-hypothesis", variant="primary"),
            Button("Test Selected", id="test-hypothesis", variant="success"),
            Button("Archive", id="archive-hypothesis", variant="default"),
        )

    def _create_failures_panel(self):
        """Create the failures list panel."""
        yield Static("═══ DISCOVERED FAILURES ═══", classes="panel-title")
        table = DataTable(id="failures-table")
        table.add_columns("Sev", "Class", "Description", "Repro%", "Status")
        yield table
        yield Static("")
        yield Horizontal(
            Button("Refresh", id="refresh-failures", variant="default"),
            Button("Investigate", id="investigate-failure", variant="primary"),
            Button("Mark Resolved", id="resolve-failure", variant="success"),
        )

    def _create_intervention_panel(self):
        """Create the intervention design panel."""
        yield Static("═══ INTERVENTIONS ═══", classes="panel-title")
        yield Static("")
        yield Static("Select a failure from [F3] Failures to design interventions.", classes="placeholder")
        yield Static("")
        table = DataTable(id="interventions-table")
        table.add_columns("ID", "Type", "Target Failure", "Est. Effect", "Status")
        yield table
        yield Static("")
        yield Horizontal(
            Button("Design New", id="design-intervention", variant="primary"),
            Button("Simulate", id="simulate-intervention", variant="warning"),
            Button("Deploy", id="deploy-intervention", variant="success"),
        )

    def _create_discuss_panel(self):
        """Create the chat/discuss panel."""
        yield Static("═══ RESEARCH DIALOGUE ═══", classes="panel-title")
        yield ScrollableContainer(
            Static("TINMAN: Hello! I'm your AI research assistant. Ask me about findings, failures, or research directions.", classes="assistant-message"),
            id="chat-log"
        )
        yield Input(placeholder="Type your message and press Enter...", id="chat-input")

    async def on_mount(self) -> None:
        """Initialize when app mounts."""
        self.log_message("Tinman TUI initialized", "success")
        self.log_message(f"Mode: {self.mode}", "info")
        self.log_message("Press F1-F5 to navigate, F10 to quit", "info")

        # Start clock update
        self.set_interval(1, self._update_clock)

        # Initialize Tinman in background
        self.run_worker(self._init_tinman())

    async def _init_tinman(self) -> None:
        """Initialize Tinman instance."""
        try:
            from ..tinman import create_tinman
            self.tinman = await create_tinman(
                mode=OperatingMode(self.mode.lower()),
                skip_db=True,  # Start without DB for now
            )

            # Register TUI as the approval UI
            self.tinman.register_approval_ui(self._tui_approval_callback)
            self.log_message("Tinman core initialized with HITL approval", "success")
        except Exception as e:
            self.log_message(f"Tinman init warning: {e}", "warning")

    async def _tui_approval_callback(self, context: ApprovalContext) -> bool:
        """
        TUI approval callback - shows modal and waits for user decision.

        This is registered with the ApprovalHandler and called whenever
        an agent needs human approval for a risky action.
        """
        self.log_message(f"Approval requested: {context.action_description}", "warning")

        # Show the approval modal and wait for result
        approved = await self.push_screen_wait(ApprovalModal(context=context))

        if approved:
            self.log_message(f"Approved: {context.action_description}", "success")
        else:
            self.log_message(f"Rejected: {context.action_description}", "warning")

        return approved

    def _update_clock(self) -> None:
        """Update the clock display."""
        clock = self.query_one("#clock", Static)
        clock.update(datetime.now().strftime("%H:%M:%S"))

    def log_message(self, message: str, level: str = "info") -> None:
        """Add a message to the activity log."""
        timestamp = datetime.now()
        self._log_messages.append((message, level, timestamp))

        # Update log display
        try:
            log_container = self.query_one("#activity-log")
            log_content = self.query_one("#log-content", Static)

            # Format recent messages
            recent = self._log_messages[-50:]  # Keep last 50
            lines = []
            for msg, lvl, ts in recent:
                prefix = {
                    "info": "│",
                    "success": "▶",
                    "warning": "⚠",
                    "error": "✖",
                }.get(lvl, "│")
                time_str = ts.strftime("%H:%M:%S")
                lines.append(f"{prefix} [{time_str}] {msg}")

            log_content.update("\n".join(lines))
        except Exception:
            pass  # UI not ready yet

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

        # Update nav button styles
        for btn in self.query("#nav-bar Button"):
            btn.remove_class("-active")
        try:
            active_btn = self.query_one(f"#nav-{tab_id}", Button)
            active_btn.add_class("-active")
        except Exception:
            pass

    def action_clear_log(self) -> None:
        """Clear the activity log."""
        self._log_messages.clear()
        try:
            log_content = self.query_one("#log-content", Static)
            log_content.update("Log cleared.")
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        # Navigation
        if button_id and button_id.startswith("nav-"):
            tab = button_id.replace("nav-", "")
            self.action_switch_tab(tab)
            return

        # Research controls
        if button_id == "start-research":
            await self._start_research()
        elif button_id == "pause-research":
            self.status = "PAUSED"
            self.query_one("#status-display", Static).update(f"Status: {self.status}")
            self.log_message("Research paused", "warning")
        elif button_id == "stop-research":
            self.status = "IDLE"
            self.query_one("#status-display", Static).update(f"Status: {self.status}")
            self.log_message("Research stopped", "info")

        # Hypothesis controls
        elif button_id == "gen-hypothesis":
            await self._generate_hypotheses()
        elif button_id == "test-hypothesis":
            self.log_message("Testing selected hypothesis...", "info")

        # Failure controls
        elif button_id == "refresh-failures":
            await self._refresh_failures()
        elif button_id == "investigate-failure":
            self.log_message("Opening failure investigation...", "info")

        # Intervention controls
        elif button_id == "design-intervention":
            await self._design_intervention()
        elif button_id == "simulate-intervention":
            await self._simulate_intervention()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submissions."""
        if event.input.id == "chat-input":
            await self._handle_chat(event.value)
            event.input.value = ""

    async def _start_research(self) -> None:
        """Start a research cycle."""
        self.status = "RUNNING"
        self.query_one("#status-display", Static).update(f"Status: {self.status}")

        focus_input = self.query_one("#focus-input", Input)
        focus = focus_input.value or None

        self.log_message("Starting research cycle...", "info")
        if focus:
            self.log_message(f"Focus area: {focus}", "info")

        # Simulate research with approval check
        await asyncio.sleep(0.5)
        self.log_message("Generating hypotheses...", "info")

        # Demo: trigger approval modal
        await asyncio.sleep(1)
        self.log_message("Found potential experiment requiring approval", "warning")

        approved = await self.push_screen_wait(ApprovalModal(
            action="Run context_overflow experiment",
            risk_tier="REVIEW (Tier 2)",
            details="This experiment will send prompts up to 95% of context window to test model behavior under memory pressure.",
            cost="~$2.40",
        ))

        if approved:
            self.log_message("Experiment approved - executing...", "success")
            await asyncio.sleep(1)
            self.log_message("Experiment complete: 3/5 runs triggered failure", "success")
            self.failure_count += 1
            self._update_metrics()
        else:
            self.log_message("Experiment rejected by user", "warning")

        self.status = "IDLE"
        self.query_one("#status-display", Static).update(f"Status: {self.status}")

    async def _generate_hypotheses(self) -> None:
        """Generate new hypotheses."""
        self.log_message("Generating hypotheses with LLM backbone...", "info")

        if not self.tinman or not self.tinman.llm:
            self.log_message("No LLM configured - using simulated hypotheses", "warning")
            await asyncio.sleep(1)

            # Add demo hypotheses to table
            table = self.query_one("#hypotheses-table", DataTable)
            demo_hypotheses = [
                ("H001", "Long context causes attention dilution", "0.72", "Testing"),
                ("H002", "Tool calls fail under recursive depth", "0.65", "New"),
                ("H003", "System prompts leak in multi-turn", "0.58", "New"),
            ]
            for h in demo_hypotheses:
                table.add_row(*h)

            self.hypothesis_count = 3
            self._update_metrics()
            self.log_message("Generated 3 hypotheses", "success")
        else:
            self.log_message("Calling hypothesis engine...", "info")
            # Real implementation would call self.tinman.generate_hypotheses()

    async def _refresh_failures(self) -> None:
        """Refresh the failures list."""
        self.log_message("Refreshing failures from memory graph...", "info")

        table = self.query_one("#failures-table", DataTable)
        table.clear()

        # Demo failures
        demo_failures = [
            ("S3", "LONG_CONTEXT", "Truncated response at 95% ctx", "60%", "Active"),
            ("S2", "TOOL_USE", "Recursive tool loop detected", "40%", "Active"),
            ("S2", "REASONING", "Logic chain break at step 7", "35%", "New"),
        ]
        for f in demo_failures:
            table.add_row(*f)

        self.failure_count = 3
        self._update_metrics()
        self.log_message("Loaded 3 failures", "success")

    async def _design_intervention(self) -> None:
        """Design an intervention for selected failure."""
        self.log_message("Designing intervention with LLM...", "info")
        await asyncio.sleep(1)

        table = self.query_one("#interventions-table", DataTable)
        table.add_row("I001", "Prompt Injection", "Long Context", "+25%", "Designed")

        self.intervention_count += 1
        self._update_metrics()
        self.log_message("Intervention designed: Context Window Guard", "success")

    async def _simulate_intervention(self) -> None:
        """Simulate an intervention."""
        self.log_message("Running counterfactual simulation...", "info")

        # Show approval for simulation
        approved = await self.push_screen_wait(ApprovalModal(
            action="Run intervention simulation",
            risk_tier="SAFE (Tier 1)",
            details="Replay 10 historical failure traces with intervention applied. No production impact.",
            cost="~$0.80",
        ))

        if approved:
            self.log_message("Simulating intervention on 10 traces...", "info")
            await asyncio.sleep(2)
            self.log_message("Simulation complete: 7/10 failures prevented", "success")
            self.log_message("Estimated effectiveness: 70%", "success")
        else:
            self.log_message("Simulation cancelled", "info")

    async def _handle_chat(self, message: str) -> None:
        """Handle chat message."""
        if not message.strip():
            return

        # Add user message
        self._chat_history.append(("user", message))
        self._update_chat_display()

        # Generate response
        if self.tinman and self.tinman.llm:
            self.log_message("Processing with LLM...", "info")
            try:
                response = await self.tinman.discuss(message)
                self._chat_history.append(("assistant", response))
            except Exception as e:
                self._chat_history.append(("assistant", f"Error: {e}"))
        else:
            # Demo response
            await asyncio.sleep(0.5)
            demo_responses = {
                "status": "Currently in LAB mode. I've analyzed 3 potential failure patterns and found 2 confirmed vulnerabilities.",
                "failures": "The most critical finding is context truncation at 95% window capacity, with 60% reproduction rate.",
                "help": "I can help you: generate hypotheses, run experiments, analyze failures, or design interventions. What would you like to explore?",
            }
            # Simple keyword matching for demo
            response = demo_responses.get("help")
            for key, val in demo_responses.items():
                if key in message.lower():
                    response = val
                    break
            self._chat_history.append(("assistant", response))

        self._update_chat_display()

    def _update_chat_display(self) -> None:
        """Update the chat log display."""
        try:
            chat_log = self.query_one("#chat-log", ScrollableContainer)
            # Clear and rebuild
            for child in list(chat_log.children):
                child.remove()

            for role, msg in self._chat_history[-20:]:  # Last 20 messages
                css_class = "user-message" if role == "user" else "assistant-message"
                prefix = "YOU: " if role == "user" else "TINMAN: "
                chat_log.mount(Static(f"{prefix}{msg}", classes=css_class))

            chat_log.scroll_end()
        except Exception:
            pass

    def _update_metrics(self) -> None:
        """Update footer metrics."""
        try:
            self.query_one("#hyp-count", Static).update(str(self.hypothesis_count))
            self.query_one("#exp-count", Static).update(str(self.experiment_count))
            self.query_one("#fail-count", Static).update(str(self.failure_count))
        except Exception:
            pass

    async def request_approval(
        self,
        action: str,
        risk_tier: RiskTier,
        details: str,
        cost: Optional[str] = None,
    ) -> bool:
        """Request user approval for an action."""
        tier_str = {
            RiskTier.SAFE: "SAFE (Tier 1)",
            RiskTier.REVIEW: "REVIEW (Tier 2)",
            RiskTier.BLOCK: "BLOCK (Tier 3)",
        }.get(risk_tier, str(risk_tier))

        return await self.push_screen_wait(ApprovalModal(
            action=action,
            risk_tier=tier_str,
            details=details,
            cost=cost,
        ))


def run_tui(settings: Optional[Settings] = None) -> None:
    """Run the Tinman TUI."""
    app = TinmanApp(settings=settings)
    app.run()


if __name__ == "__main__":
    run_tui()
