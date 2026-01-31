"""Tinman TUI - Modern Research Interface.

Designed for both beginners and power users:
- Dashboard with health checks and quick start guide
- Keyboard shortcuts prominently displayed
- Progressive disclosure of advanced features
- Clear visual hierarchy and status indicators
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Static,
    TabbedContent,
    TabPane,
)
from textual.worker import NoActiveWorker, get_current_worker

from .. import __version__
from ..agents.base import AgentContext
from ..config.modes import OperatingMode
from ..config.settings import Settings, load_settings
from ..core.approval_handler import ApprovalContext
from ..core.risk_evaluator import RiskTier

if TYPE_CHECKING:
    pass


# Compact ASCII Art Header
TINMAN_ASCII = r"""
 _   _
| |_|_|___ _____ ___ ___
|  _| |   |     | .'|   |
|_| |_|_|_|_|_|_|__,|_|_|"""


class ShortcutsModal(ModalScreen):
    """Modal showing all keyboard shortcuts."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="shortcuts-overlay"):
            yield Static("KEYBOARD SHORTCUTS", classes="shortcuts-title")

            yield Static("Navigation", classes="shortcut-section")
            with Horizontal(classes="shortcut-row"):
                yield Static("F1", classes="shortcut-key")
                yield Static("Dashboard - Overview & quick start", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("F2", classes="shortcut-key")
                yield Static("Research - Run discovery cycles", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("F3", classes="shortcut-key")
                yield Static("Analysis - Review findings", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("F4", classes="shortcut-key")
                yield Static("Deploy - Interventions & actions", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("F5", classes="shortcut-key")
                yield Static("Chat - Discuss with AI", classes="shortcut-desc")

            yield Static("Actions", classes="shortcut-section")
            with Horizontal(classes="shortcut-row"):
                yield Static("Ctrl+R", classes="shortcut-key")
                yield Static("Start/stop research cycle", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("Ctrl+M", classes="shortcut-key")
                yield Static("Configure model", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("Ctrl+L", classes="shortcut-key")
                yield Static("Clear activity log", classes="shortcut-desc")

            yield Static("General", classes="shortcut-section")
            with Horizontal(classes="shortcut-row"):
                yield Static("?", classes="shortcut-key")
                yield Static("Show this help", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("Tab", classes="shortcut-key")
                yield Static("Move focus to next element", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("Enter", classes="shortcut-key")
                yield Static("Activate focused button/row", classes="shortcut-desc")
            with Horizontal(classes="shortcut-row"):
                yield Static("F10/Ctrl+Q", classes="shortcut-key")
                yield Static("Quit application", classes="shortcut-desc")

            yield Static("Press ESC or ? to close", classes="empty-state")


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
        context: ApprovalContext | None = None,
        action: str | None = None,
        risk_tier: str | None = None,
        details: str | None = None,
        cost: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.context = context
        self.result: bool | None = None

        if context:
            self.action = context.action_description
            self.risk_tier = (
                f"{context.risk_tier.value.upper()} (Severity: {context.severity.value})"
            )
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
            yield Static("APPROVAL REQUIRED", classes="modal-title")
            yield Static(f"Action: {self.action}", classes="modal-content")
            yield Static(f"Risk Level: {self.risk_tier}", classes="modal-content")
            if self.cost:
                yield Static(f"Estimated Cost: {self.cost}", classes="modal-content")
            if not self.is_reversible:
                yield Static("This action is NOT reversible!", classes="modal-warning")
            yield Static("Details:", classes="modal-content")
            yield Static(
                self.details[:400] if self.details else "No details provided",
                classes="modal-content",
            )
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
        if self.context:
            self.app.log_message(f"Full details: {self.context.action_details}", "info")
            if self.context.risk_assessment:
                self.app.log_message(
                    f"Risk reasoning: {self.context.risk_assessment.reasoning}", "info"
                )
        else:
            self.app.log_message(f"Details: {self.details}", "info")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve-btn":
            self.action_approve()
        elif event.button.id == "reject-btn":
            self.action_reject()
        elif event.button.id == "details-btn":
            self.action_details()


class ModelConfigModal(ModalScreen):
    """Modal for configuring the default model provider/model."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
    ]

    def __init__(self, provider: str, model: str, **kwargs):
        super().__init__(**kwargs)
        self._provider = provider
        self._model = model

    def compose(self) -> ComposeResult:
        with Container(id="model-config-modal"):
            yield Static("MODEL CONFIGURATION", classes="shortcuts-title")
            yield Label("Provider (e.g., openai, anthropic, groq)")
            yield Input(value=self._provider, id="model-provider-input")
            yield Label("Model (e.g., gpt-4, claude-3-opus)")
            yield Input(value=self._model, id="model-name-input")
            with Horizontal(classes="modal-actions"):
                yield Button("Save", id="model-config-save", variant="success")
                yield Button("Cancel", id="model-config-cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "model-config-save":
            provider = self.query_one("#model-provider-input", Input).value.strip()
            model = self.query_one("#model-name-input", Input).value.strip()
            if not provider:
                provider = self._provider
            if not model:
                model = self._model
            self.dismiss({"provider": provider, "model": model})
        else:
            self.dismiss(None)


class TinmanApp(App):
    """Tinman Terminal User Interface - Modern Research Dashboard."""

    TITLE = "TINMAN"
    SUB_TITLE = "Forward-Deployed Research Agent"

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        # Navigation
        Binding("f1", "switch_tab('dashboard')", "Dashboard", show=True),
        Binding("f2", "switch_tab('research')", "Research", show=True),
        Binding("f3", "switch_tab('analysis')", "Analysis", show=True),
        Binding("f4", "switch_tab('deploy')", "Deploy", show=True),
        Binding("f5", "switch_tab('chat')", "Chat", show=True),
        # Actions
        Binding("ctrl+r", "toggle_research", "Run", show=False),
        Binding("ctrl+m", "config_model", "Model", show=False),
        Binding("ctrl+l", "clear_log", "Clear", show=False),
        # Help & Quit
        Binding("question_mark", "show_shortcuts", "Help", show=True),
        Binding("f10", "quit", "Quit", show=True),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    # Reactive state
    mode: reactive[str] = reactive("LAB")
    status: reactive[str] = reactive("IDLE")
    hypothesis_count: reactive[int] = reactive(0)
    experiment_count: reactive[int] = reactive(0)
    failure_count: reactive[int] = reactive(0)
    intervention_count: reactive[int] = reactive(0)

    DEMO_TEMPLATES = {
        "github": {"args": "--repo moltbot/moltbot", "env": ["GITHUB_TOKEN"]},
        "huggingface": {"args": "--model gpt2", "env": ["HUGGINGFACE_API_KEY"]},
        "replicate": {"args": "--version <MODEL_VERSION_ID>", "env": ["REPLICATE_API_TOKEN"]},
        "fal": {"args": "--endpoint https://fal.run/fal-ai/fast-sdxl", "env": ["FAL_API_KEY"]},
    }

    def __init__(self, settings: Settings | None = None, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings or load_settings()
        self.config_path = self._resolve_config_path()
        self.mode = self.settings.mode.value.upper()
        self.tinman = None
        self._log_messages: list[tuple[str, str, datetime]] = []
        self._chat_history: list[tuple[str, str]] = []
        self._pending_approvals: list[dict] = []
        self._last_results: dict = {}
        self._last_focus: str | None = None
        self._chat_inflight = False
        self._run_inflight = False
        self._run_worker = None
        self._setup_status: dict[str, str] = {}
        self._selected_failure_id: str | None = None
        self._selected_intervention_id: str | None = None

    def _resolve_config_path(self) -> Path:
        preferred = Path(".tinman") / "config.yaml"
        if preferred.exists():
            return preferred
        fallback = Path("tinman.yaml")
        return fallback if fallback.exists() else preferred

    def _update_config_model(self, provider: str, model: str) -> None:
        """Persist model provider/model to config."""
        updated = False
        lines: list[str] = []

        if self.config_path.exists():
            lines = self.config_path.read_text(encoding="utf-8").splitlines()

        in_models = False
        in_providers = False
        in_target_provider = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            if stripped.startswith("models:"):
                in_models = True
                in_providers = False
                in_target_provider = False
                continue

            if in_models and stripped.startswith("providers:"):
                in_providers = True
                in_target_provider = False
                continue

            if in_models and stripped.startswith("default:"):
                indent = line[: line.find("d")] if "d" in line else ""
                lines[i] = f"{indent}default: {provider}"
                updated = True
                continue

            if in_providers and stripped.endswith(":") and not stripped.startswith("#"):
                current_provider = stripped[:-1]
                in_target_provider = current_provider == provider
                continue

            if in_target_provider and stripped.startswith("model:"):
                indent = line[: line.find("m")] if "m" in line else "    "
                lines[i] = f"{indent}model: {model}"
                updated = True
                in_target_provider = False
                continue

            if in_models and stripped == "":
                in_models = False
                in_providers = False
                in_target_provider = False

        if not updated:
            data = {}
            if self.config_path.exists():
                data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}

            models = data.setdefault("models", {})
            models["default"] = provider
            providers = models.setdefault("providers", {})
            provider_block = providers.setdefault(provider, {})
            provider_block["model"] = model

            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False)
        else:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        self.settings.models.default = provider
        if provider not in self.settings.models.providers:
            from ..config.settings import ModelProviderSettings

            self.settings.models.providers[provider] = ModelProviderSettings()
        self.settings.models.providers[provider].model = model

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        with Container(id="main-container"):
            # Header - Compact status bar
            yield from self._create_header()

            # Navigation bar
            yield from self._create_nav_bar()

            # Main content area with tabs
            with TabbedContent(id="content"):
                with TabPane("Dashboard", id="dashboard"):
                    with ScrollableContainer(classes="tab-scroll"):
                        yield from self._create_dashboard_panel()
                with TabPane("Research", id="research"):
                    with ScrollableContainer(classes="tab-scroll"):
                        yield from self._create_research_panel()
                with TabPane("Analysis", id="analysis"):
                    with ScrollableContainer(classes="tab-scroll"):
                        yield from self._create_analysis_panel()
                with TabPane("Deploy", id="deploy"):
                    with ScrollableContainer(classes="tab-scroll"):
                        yield from self._create_deploy_panel()
                with TabPane("Chat", id="chat"):
                    yield from self._create_chat_panel()

            # Footer - Metrics and hints
            yield from self._create_footer()

    def _create_header(self):
        """Create compact header with status badges."""
        with Horizontal(id="header"):
            with Container(id="logo-section"):
                yield Static(TINMAN_ASCII, id="ascii-logo")
            with Vertical(id="title-section"):
                yield Static(f"TINMAN v{__version__}", id="app-title")
                yield Static("Forward-Deployed Research Agent", id="app-subtitle")
            with Horizontal(id="status-section"):
                yield Static(f"MODE: {self.mode}", id="mode-badge", classes="status-badge")
                yield Static("IDLE", id="status-badge", classes="status-badge")
                yield Static("--:--:--", id="clock")

    def _create_nav_bar(self):
        """Create navigation bar with keyboard hints."""
        with Horizontal(id="nav-bar"):
            with Horizontal(id="nav-left"):
                yield Button("F1 Dashboard", id="nav-dashboard", classes="-active")
                yield Button("F2 Research", id="nav-research")
                yield Button("F3 Analysis", id="nav-analysis")
                yield Button("F4 Deploy", id="nav-deploy")
                yield Button("F5 Chat", id="nav-chat")
            with Horizontal(id="nav-right"):
                yield Button("?", id="help-toggle")

    def _create_dashboard_panel(self):
        """Create dashboard with health checks and quick start."""
        # Welcome / Getting Started (for beginners)
        with Container(classes="getting-started"):
            yield Static("QUICK START GUIDE", classes="getting-started-title")
            with Horizontal(classes="step-row"):
                yield Static("1.", classes="step-number")
                yield Static("Configure your model provider", classes="step-text")
                yield Static("", id="step1-status", classes="step-status step-pending")
            with Horizontal(classes="step-row"):
                yield Static("2.", classes="step-number")
                yield Static("Set up API key in environment", classes="step-text")
                yield Static("", id="step2-status", classes="step-status step-pending")
            with Horizontal(classes="step-row"):
                yield Static("3.", classes="step-number")
                yield Static("Initialize database (optional)", classes="step-text")
                yield Static("", id="step3-status", classes="step-status step-pending")
            with Horizontal(classes="step-row"):
                yield Static("4.", classes="step-number")
                yield Static("Start a research cycle (F2)", classes="step-text")
                yield Static("", id="step4-status", classes="step-status step-pending")

        # System Health
        yield Static("SYSTEM HEALTH", classes="section-title")
        with Container(classes="section-body"):
            with Horizontal(classes="health-row"):
                yield Static("*", id="health-model-icon", classes="health-indicator health-unknown")
                yield Static("Model Provider", classes="health-label")
                yield Static("Checking...", id="health-model", classes="health-status")
            with Horizontal(classes="health-row"):
                yield Static("*", id="health-key-icon", classes="health-indicator health-unknown")
                yield Static("API Key", classes="health-label")
                yield Static("Checking...", id="health-key", classes="health-status")
            with Horizontal(classes="health-row"):
                yield Static("*", id="health-db-icon", classes="health-indicator health-unknown")
                yield Static("Database", classes="health-label")
                yield Static("Checking...", id="health-db", classes="health-status")

        # Quick Actions
        yield Static("QUICK ACTIONS", classes="section-title")
        with Horizontal(classes="quick-actions"):
            yield Button("Configure Model", id="dash-config-model", classes="action-btn action-btn-primary")
            yield Button("Init Database", id="dash-init-db", classes="action-btn")
            yield Button("Start Research", id="dash-start-run", classes="action-btn action-btn-success")
            yield Button("Reload Config", id="dash-reload", classes="action-btn")

        # Current Session Stats
        yield Static("SESSION STATISTICS", classes="section-title")
        with Container(classes="section-body"):
            yield Static(
                "Hypotheses: 0 | Experiments: 0 | Failures: 0 | Interventions: 0",
                id="session-stats",
            )

        # Activity Log
        yield Static("RECENT ACTIVITY", classes="section-title")
        with Container(id="dashboard-log", classes="log-panel log-panel-md"):
            yield Static("Welcome to Tinman! Press ? for keyboard shortcuts.", id="dashboard-log-content")

    def _create_research_panel(self):
        """Create research panel for running discovery cycles."""
        yield Static("RESEARCH CYCLE", classes="section-title")
        with Container(classes="section-body"):
            yield Static(
                "Run a research cycle to discover AI failure modes. "
                "Optionally specify a focus area to narrow the scope.",
                classes="empty-state",
            )

        # Focus area input
        with Container(classes="section-body"):
            with Horizontal(classes="form-row"):
                yield Static("Focus Area:", classes="form-label")
                yield Input(
                    placeholder="e.g., tool_use, long_context, reasoning, feedback_loop",
                    id="focus-input",
                )
            yield Static(
                "Leave blank for general discovery, or specify: tool_use, long_context, "
                "reasoning, feedback_loop, deployment",
                classes="input-hint",
            )

        # Run controls
        with Horizontal(classes="quick-actions"):
            yield Button("Start Research", id="start-run", classes="action-btn action-btn-success")
            yield Button("Stop", id="stop-run", classes="action-btn action-btn-danger")

        # Run Summary
        yield Static("RUN SUMMARY", classes="section-title")
        with Container(classes="detail-panel"):
            yield Static("No research cycles run yet.", id="run-summary")

        # Activity Log
        yield Static("ACTIVITY LOG", classes="section-title")
        yield ScrollableContainer(
            Static("Ready to start research.", id="log-content"),
            id="activity-log",
            classes="log-panel log-panel-lg",
        )

    def _create_analysis_panel(self):
        """Create analysis panel for reviewing findings."""
        yield Static("ANALYSIS & FINDINGS", classes="section-title")
        with Container(classes="section-body"):
            yield Static("Research cycle summary will appear here.", id="analysis-summary")

        with Horizontal(classes="button-row"):
            yield Button("Generate Report", id="analysis-report", classes="action-btn")
            yield Button("Open Report", id="analysis-open", classes="action-btn")
            yield Button("Refresh from DB", id="analysis-refresh", classes="action-btn")

        # Hypotheses Table
        yield Static("HYPOTHESES", classes="section-title")
        table = DataTable(id="analysis-hypotheses-table", classes="table-compact")
        table.add_columns("ID", "Hypothesis", "Confidence", "Status")
        yield table

        # Failures Table
        yield Static("DISCOVERED FAILURES", classes="section-title")
        table = DataTable(id="analysis-failures-table", classes="table-compact")
        table.add_columns("Sev", "Class", "Description", "Repro%", "Status")
        yield table

        # Interventions Table
        yield Static("PROPOSED INTERVENTIONS", classes="section-title")
        table = DataTable(id="analysis-interventions-table", classes="table-compact")
        table.add_columns("ID", "Type", "Target", "Effect", "Status")
        yield table

        # Detail view
        yield Static("SELECTED ITEM DETAILS", classes="section-title")
        with Container(classes="detail-panel"):
            yield Static("Select an item above to view details.", id="analysis-detail")

    def _create_deploy_panel(self):
        """Create deploy panel for interventions."""
        yield Static("INTERVENTION DEPLOYMENT", classes="section-title")
        with Container(classes="section-body"):
            yield Static(
                "Design, simulate, and deploy interventions to address discovered failures.",
                classes="empty-state",
            )

        # Failures to address
        yield Static("FAILURES TO ADDRESS", classes="section-title")
        table = DataTable(id="deploy-failures-table", classes="table-compact")
        table.add_columns("ID", "Class", "Description", "Severity")
        yield table

        # Interventions
        yield Static("INTERVENTIONS", classes="section-title")
        table = DataTable(id="deploy-interventions-table", classes="table-compact")
        table.add_columns("ID", "Type", "Target", "Risk", "Status")
        yield table

        # Action buttons
        with Horizontal(classes="quick-actions"):
            yield Button("Design Intervention", id="deploy-design", classes="action-btn action-btn-primary")
            yield Button("Simulate", id="deploy-simulate", classes="action-btn")
            yield Button("Deploy", id="deploy-execute", classes="action-btn action-btn-success")

        # Log
        yield Static("DEPLOYMENT LOG", classes="section-title")
        with Container(id="deploy-log", classes="log-panel log-panel-sm"):
            yield Static("No deployment activity yet.", id="deploy-log-content")

    def _create_chat_panel(self):
        """Create chat panel for AI dialogue."""
        yield Static("RESEARCH DIALOGUE", classes="section-title")
        with Container(id="chat-container"):
            yield ScrollableContainer(
                Static(
                    "Ask questions about your research findings, request analysis, "
                    "or discuss intervention strategies.",
                    id="chat-empty",
                    classes="empty-state",
                ),
                id="chat-log",
            )
            with Horizontal(id="chat-input-row"):
                yield Input(placeholder="Type your message and press Enter...", id="chat-input")
                yield Button("Send", id="chat-send")

    def _create_footer(self):
        """Create footer with metrics and keyboard hints."""
        with Horizontal(id="footer"):
            with Horizontal(id="footer-left"):
                with Horizontal(classes="metric-group"):
                    yield Static("Hyp:", classes="metric-label")
                    yield Static("0", id="hyp-count", classes="metric-value")
                with Horizontal(classes="metric-group"):
                    yield Static("Exp:", classes="metric-label")
                    yield Static("0", id="exp-count", classes="metric-value")
                with Horizontal(classes="metric-group"):
                    yield Static("Fail:", classes="metric-label")
                    yield Static("0", id="fail-count", classes="metric-value")
                with Horizontal(classes="metric-group"):
                    yield Static("Int:", classes="metric-label")
                    yield Static("0", id="int-count", classes="metric-value")
            with Horizontal(id="footer-right"):
                yield Static("Press ? for shortcuts | F10 to quit", classes="footer-hint")

    async def on_mount(self) -> None:
        """Initialize when app mounts."""
        self.log_message("Tinman TUI initialized", "success")
        self.log_message(f"Operating mode: {self.mode}", "info")
        self.log_message("Press ? to view keyboard shortcuts", "info")

        # Start clock update
        self.set_interval(1, self._update_clock)

        # Initialize Tinman in background
        self.run_worker(self._init_tinman())
        self.run_worker(self._refresh_health_status())

    async def _init_tinman(self) -> None:
        """Initialize Tinman instance."""
        try:
            from ..cli.main import get_model_client
            from ..tinman import create_tinman

            model_client = get_model_client(self.settings)
            db_url = self.settings.database_url

            try:
                self.tinman = await create_tinman(
                    model_client=model_client,
                    db_url=db_url,
                    mode=OperatingMode(self.mode.lower()),
                    skip_db=False,
                )
            except Exception as e:
                self.log_message(f"DB init failed, continuing without: {e}", "warning")
                self.tinman = await create_tinman(
                    model_client=model_client,
                    mode=OperatingMode(self.mode.lower()),
                    skip_db=True,
                )

            self.tinman.register_approval_ui(self._tui_approval_callback)
            self.log_message("Core initialized with HITL approval", "success")
        except Exception as e:
            self.log_message(f"Init warning: {e}", "warning")

    async def _refresh_health_status(self) -> None:
        """Refresh health check status."""
        model_provider = self.settings.models.default
        provider_settings = self.settings.models.providers.get(model_provider)
        model_name = provider_settings.model if provider_settings else ""
        api_key = provider_settings.api_key if provider_settings else ""

        model_ok = bool(model_provider and model_name)
        key_ok = bool(api_key)

        db_ok = False
        try:
            from sqlalchemy import create_engine

            engine = create_engine(self.settings.database_url)
            with engine.connect():
                db_ok = True
        except Exception:
            db_ok = False

        self._setup_status = {
            "model": "OK" if model_ok else "Not configured",
            "key": "OK" if key_ok else "Missing",
            "db": "Connected" if db_ok else "Not connected",
        }

        # Update health indicators
        self._update_health_display("model", model_ok, self._setup_status["model"])
        self._update_health_display("key", key_ok, self._setup_status["key"])
        self._update_health_display("db", db_ok, self._setup_status["db"])

        # Update quick start steps
        self._update_step_status(1, model_ok)
        self._update_step_status(2, key_ok)
        self._update_step_status(3, db_ok)

    def _update_health_display(self, item: str, ok: bool, status_text: str) -> None:
        """Update a health indicator."""
        try:
            icon = self.query_one(f"#health-{item}-icon", Static)
            icon.remove_class("health-ok", "health-error", "health-unknown")
            icon.add_class("health-ok" if ok else "health-error")
            icon.update("*" if ok else "!")

            status = self.query_one(f"#health-{item}", Static)
            status.update(status_text)
        except Exception:
            pass

    def _update_step_status(self, step: int, done: bool) -> None:
        """Update a quick start step status."""
        try:
            status = self.query_one(f"#step{step}-status", Static)
            status.remove_class("step-done", "step-pending", "step-current")
            if done:
                status.update("[done]")
                status.add_class("step-done")
            else:
                status.update("[pending]")
                status.add_class("step-pending")
        except Exception:
            pass

    async def _init_db(self) -> None:
        """Initialize database."""
        try:
            from ..db.connection import ensure_database

            info = await asyncio.to_thread(ensure_database, self.settings.database_url)
            created = "created" if info.get("created") else "already exists"
            self.log_message(f"{info['backend']} database {created}: {info['database']}", "success")
        except Exception as e:
            self.log_message(f"Database init failed: {e}", "error")
        await self._refresh_health_status()

    async def _tui_approval_callback(self, context: ApprovalContext) -> bool:
        """TUI approval callback - shows modal and waits for user decision."""
        self.log_message(f"Approval requested: {context.action_description}", "warning")
        approved = await self.push_screen_wait(ApprovalModal(context=context))

        if approved:
            self.log_message(f"Approved: {context.action_description}", "success")
        else:
            self.log_message(f"Rejected: {context.action_description}", "warning")

        return approved

    def _update_clock(self) -> None:
        """Update the clock display."""
        try:
            clock = self.query_one("#clock", Static)
            clock.update(datetime.now().strftime("%H:%M:%S"))
        except Exception:
            pass

    def log_message(self, message: str, level: str = "info") -> None:
        """Add a message to the activity log."""
        timestamp = datetime.now()
        self._log_messages.append((message, level, timestamp))

        recent = self._log_messages[-50:]
        lines = []
        for msg, lvl, ts in recent:
            prefix = {"info": "-", "success": "+", "warning": "!", "error": "X"}.get(lvl, "-")
            time_str = ts.strftime("%H:%M:%S")
            lines.append(f"{prefix} [{time_str}] {msg}")

        rendered = "\n".join(lines)

        for widget_id in (
            "#log-content",
            "#dashboard-log-content",
            "#deploy-log-content",
        ):
            try:
                self.query_one(widget_id, Static).update(rendered)
            except Exception:
                pass

    def action_show_shortcuts(self) -> None:
        """Show keyboard shortcuts modal."""
        self.push_screen(ShortcutsModal())

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

        # Update nav button styles
        for btn in self.query("#nav-bar Button"):
            if btn.id != "help-toggle":
                btn.remove_class("-active")
        try:
            active_btn = self.query_one(f"#nav-{tab_id}", Button)
            active_btn.add_class("-active")
        except Exception:
            pass

    def action_toggle_research(self) -> None:
        """Toggle research cycle on/off."""
        if self._run_inflight:
            if self._run_worker:
                self._run_worker.cancel()
                self._run_worker = None
            self.status = "IDLE"
            self._run_inflight = False
            self._update_status_badge("IDLE")
            self.log_message("Research stopped", "warning")
        else:
            self._run_worker = self.run_worker(self._start_research(), exclusive=True)

    def action_clear_log(self) -> None:
        """Clear the activity log."""
        self._log_messages.clear()
        for widget_id in ("#log-content", "#dashboard-log-content", "#deploy-log-content"):
            try:
                self.query_one(widget_id, Static).update("Log cleared.")
            except Exception:
                pass

    def action_config_model(self) -> None:
        """Open the model configuration modal."""
        self.run_worker(self._config_model_worker(), exclusive=True)

    async def _config_model_worker(self) -> None:
        provider = self.settings.models.default
        provider_settings = self.settings.models.providers.get(provider)
        model = provider_settings.model if provider_settings else ""

        result = await self.push_screen_wait(ModelConfigModal(provider, model))
        if not result:
            return

        self._update_config_model(result["provider"], result["model"])
        self.log_message(f"Model updated: {result['provider']}/{result['model']}", "success")
        await self._refresh_health_status()

    def _update_status_badge(self, status: str) -> None:
        """Update the status badge."""
        try:
            badge = self.query_one("#status-badge", Static)
            badge.remove_class("status-badge-ok", "status-badge-warn", "status-badge-running")

            if status == "RUNNING":
                badge.add_class("status-badge-running")
            elif status == "IDLE":
                badge.add_class("status-badge-ok")
            else:
                badge.add_class("status-badge-warn")

            badge.update(status)
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        # Navigation
        if button_id and button_id.startswith("nav-"):
            if button_id == "help-toggle":
                self.action_show_shortcuts()
                return
            tab = button_id.replace("nav-", "")
            self.action_switch_tab(tab)
            return

        # Dashboard actions
        if button_id == "dash-config-model":
            self.action_config_model()
        elif button_id == "dash-init-db":
            self.run_worker(self._init_db())
        elif button_id == "dash-start-run":
            self.action_switch_tab("research")
            self._run_worker = self.run_worker(self._start_research(), exclusive=True)
        elif button_id == "dash-reload":
            self.settings = load_settings()
            self.run_worker(self._refresh_health_status())
            self.log_message("Settings reloaded", "success")

        # Research actions
        elif button_id == "start-run":
            if not self._run_inflight:
                self._run_worker = self.run_worker(self._start_research(), exclusive=True)
        elif button_id == "stop-run":
            if self._run_worker:
                self._run_worker.cancel()
                self._run_worker = None
            self.status = "IDLE"
            self._update_status_badge("IDLE")
            self._run_inflight = False
            self.log_message("Research stopped", "warning")

        # Analysis actions
        elif button_id == "analysis-report":
            self.run_worker(self._generate_report(), exclusive=True)
        elif button_id == "analysis-open":
            self.run_worker(self._open_latest_report(), exclusive=True)
        elif button_id == "analysis-refresh":
            self.run_worker(self._refresh_from_db(), exclusive=True)

        # Deploy actions
        elif button_id == "deploy-design":
            self.run_worker(self._design_intervention(), exclusive=True)
        elif button_id == "deploy-simulate":
            self.run_worker(self._simulate_intervention(), exclusive=True)
        elif button_id == "deploy-execute":
            self.run_worker(self._deploy_intervention(), exclusive=True)

        # Chat
        elif button_id == "chat-send":
            try:
                chat_input = self.query_one("#chat-input", Input)
                if chat_input.value.strip():
                    self.run_worker(self._handle_chat(chat_input.value), exclusive=True)
                    chat_input.value = ""
            except Exception:
                pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submissions."""
        if event.input.id == "chat-input":
            self.run_worker(self._handle_chat(event.value), exclusive=True)
            event.input.value = ""

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        row = event.data_table.get_row(event.row_key)

        if not row:
            return

        # Update detail view
        try:
            if "hypotheses" in str(table_id):
                detail = f"Hypothesis: {row[1]}\nConfidence: {row[2]}\nStatus: {row[3]}"
            elif "failures" in str(table_id):
                detail = f"Severity: {row[0]}\nClass: {row[1]}\n{row[2]}"
                if "deploy" in str(table_id):
                    self._selected_failure_id = row[0] if len(row) > 0 else None
            elif "interventions" in str(table_id):
                detail = f"Type: {row[1]}\nTarget: {row[2]}\nStatus: {row[-1]}"
                if "deploy" in str(table_id):
                    self._selected_intervention_id = row[0] if len(row) > 0 else None
            else:
                detail = " | ".join(str(c) for c in row)

            self.query_one("#analysis-detail", Static).update(detail)
        except Exception:
            pass

    async def _start_research(self) -> None:
        """Start a research cycle."""
        self._run_inflight = True
        self.status = "RUNNING"
        self._update_status_badge("RUNNING")

        focus_input = self.query_one("#focus-input", Input)
        focus = focus_input.value or None

        self.log_message("Starting research cycle...", "info")
        if focus:
            self.log_message(f"Focus area: {focus}", "info")

        if not self.tinman or not self.tinman.llm:
            self.log_message("No LLM configured. Configure a model first.", "warning")
            self.status = "IDLE"
            self._update_status_badge("IDLE")
            self._run_inflight = False
            return

        try:
            results = await self.tinman.research_cycle(focus=focus)
        except Exception as e:
            self.log_message(f"Research failed: {e}", "error")
            self.status = "IDLE"
            self._update_status_badge("IDLE")
            self._run_inflight = False
            return

        self._last_results = results
        self._last_focus = focus
        self._populate_tables(results)
        self._update_metrics(results)
        self._update_run_summary(results)
        self.log_message("Research cycle complete", "success")

        self.status = "IDLE"
        self._update_status_badge("IDLE")
        self._run_inflight = False
        self._run_worker = None

    def _populate_tables(self, results: dict) -> None:
        """Populate analysis and deploy tables with results."""
        hypotheses = results.get("hypotheses", [])
        failures = results.get("failures", [])
        interventions = results.get("interventions", [])

        # Analysis tables
        try:
            h_table = self.query_one("#analysis-hypotheses-table", DataTable)
            h_table.clear()
            for h in hypotheses:
                h_table.add_row(
                    h.get("id", "")[:8],
                    h.get("expected_failure", "")[:50],
                    f"{h.get('confidence', 0):.2f}",
                    h.get("priority", "new"),
                )
        except Exception:
            pass

        try:
            f_table = self.query_one("#analysis-failures-table", DataTable)
            f_table.clear()
            for f in failures:
                f_table.add_row(
                    f.get("severity", "S2"),
                    f.get("primary_class", ""),
                    f.get("description", "")[:60],
                    f"{int((f.get('reproducibility', 0) or 0) * 100)}%",
                    "new" if f.get("is_novel") else "known",
                )
        except Exception:
            pass

        try:
            i_table = self.query_one("#analysis-interventions-table", DataTable)
            i_table.clear()
            for i in interventions:
                i_table.add_row(
                    i.get("id", "")[:8],
                    i.get("intervention_type", ""),
                    i.get("target_failure_id", "")[:8],
                    i.get("expected_improvement", ""),
                    i.get("status", "proposed"),
                )
        except Exception:
            pass

        # Deploy tables
        try:
            df_table = self.query_one("#deploy-failures-table", DataTable)
            df_table.clear()
            for f in failures:
                df_table.add_row(
                    f.get("id", "")[:8],
                    f.get("primary_class", ""),
                    f.get("description", "")[:50],
                    f.get("severity", "S2"),
                )
        except Exception:
            pass

        try:
            di_table = self.query_one("#deploy-interventions-table", DataTable)
            di_table.clear()
            for i in interventions:
                di_table.add_row(
                    i.get("id", "")[:8],
                    i.get("intervention_type", ""),
                    i.get("target_failure_id", "")[:8],
                    i.get("risk_tier", "REVIEW"),
                    i.get("status", "proposed"),
                )
        except Exception:
            pass

        # Update summary
        try:
            summary = (
                f"Hypotheses: {len(hypotheses)} | Experiments: {len(results.get('experiments', []))} | "
                f"Failures: {len(failures)} | Interventions: {len(interventions)}"
            )
            self.query_one("#analysis-summary", Static).update(summary)
        except Exception:
            pass

    def _update_metrics(self, results: dict) -> None:
        """Update footer metrics."""
        self.hypothesis_count = len(results.get("hypotheses", []))
        self.experiment_count = len(results.get("experiments", []))
        self.failure_count = len(results.get("failures", []))
        self.intervention_count = len(results.get("interventions", []))

        try:
            self.query_one("#hyp-count", Static).update(str(self.hypothesis_count))
            self.query_one("#exp-count", Static).update(str(self.experiment_count))
            self.query_one("#fail-count", Static).update(str(self.failure_count))
            self.query_one("#int-count", Static).update(str(self.intervention_count))

            # Session stats on dashboard
            stats = (
                f"Hypotheses: {self.hypothesis_count} | Experiments: {self.experiment_count} | "
                f"Failures: {self.failure_count} | Interventions: {self.intervention_count}"
            )
            self.query_one("#session-stats", Static).update(stats)
        except Exception:
            pass

    def _update_run_summary(self, results: dict) -> None:
        """Update the run summary."""
        focus = self._last_focus or "General discovery"
        summary = (
            f"Focus: {focus}\n"
            f"Hypotheses: {len(results.get('hypotheses', []))} | "
            f"Experiments: {len(results.get('experiments', []))} | "
            f"Failures: {len(results.get('failures', []))} | "
            f"Interventions: {len(results.get('interventions', []))}"
        )
        try:
            self.query_one("#run-summary", Static).update(summary)
        except Exception:
            pass

    async def _design_intervention(self) -> None:
        """Design interventions for selected failure."""
        if not self.tinman or not self.tinman.intervention_engine:
            self.log_message("Intervention engine not initialized", "warning")
            return
        if not self._selected_failure_id:
            self.log_message("Select a failure first", "warning")
            return

        self.log_message("Designing intervention...", "info")

        # Get failure from graph
        if not self.tinman.graph:
            self.log_message("No graph available", "warning")
            return

        from ..agents.failure_discovery import DiscoveredFailure
        from ..taxonomy.failure_types import FailureClass, Severity

        node = self.tinman.graph.get_node(self._selected_failure_id)
        if not node:
            self.log_message("Failure not found", "warning")
            return

        data = {"id": node.id, **(node.data or {})}
        try:
            primary = FailureClass(data.get("primary_class", "reasoning"))
        except Exception:
            primary = FailureClass.REASONING
        try:
            sev_enum = Severity[data.get("severity", "S2")]
        except Exception:
            sev_enum = Severity.S2

        failure = DiscoveredFailure(
            id=node.id,
            primary_class=primary,
            secondary_class=data.get("secondary_class"),
            severity=sev_enum,
            description=data.get("description", ""),
            trigger_signature=data.get("trigger_signature", []),
            reproducibility=data.get("reproducibility", 0.0),
            experiment_id=data.get("experiment_id", ""),
            run_ids=data.get("run_ids", []),
            llm_analysis=data.get("llm_analysis", ""),
            contributing_factors=data.get("contributing_factors", []),
            key_insight=data.get("key_insight", ""),
            causal_analysis=data.get("causal_analysis"),
            is_novel=data.get("is_novel", False),
            parent_failure_id=data.get("parent_failure_id"),
        )

        context = AgentContext(mode=OperatingMode(self.mode.lower()))
        try:
            result = await self.tinman.intervention_engine.run(context, failures=[failure])
            if result.success:
                self._populate_tables(
                    {"failures": [data], "interventions": result.data.get("interventions", [])}
                )
                self.log_message("Intervention designed", "success")
            else:
                self.log_message(f"Design failed: {result.error}", "error")
        except Exception as e:
            self.log_message(f"Design failed: {e}", "error")

    async def _simulate_intervention(self) -> None:
        """Simulate selected intervention."""
        if not self.tinman or not self.tinman.simulation_engine:
            self.log_message("Simulation engine not initialized", "warning")
            return
        if not self._selected_intervention_id:
            self.log_message("Select an intervention first", "warning")
            return

        self.log_message("Running simulation...", "info")

        if not self.tinman.graph:
            self.log_message("No graph available", "warning")
            return

        from ..agents.intervention_engine import Intervention, InterventionType

        node = self.tinman.graph.get_node(self._selected_intervention_id)
        if not node:
            self.log_message("Intervention not found", "warning")
            return

        data = node.data or {}
        try:
            itype = InterventionType(data.get("intervention_type", "prompt_patch"))
        except Exception:
            itype = InterventionType.PROMPT_PATCH
        try:
            risk = RiskTier(data.get("risk_tier", "review"))
        except Exception:
            risk = RiskTier.REVIEW

        intervention = Intervention(
            id=node.id,
            failure_id=data.get("failure_id", ""),
            intervention_type=itype,
            name=data.get("name", "intervention"),
            description=data.get("description", ""),
            payload=data.get("payload", {}),
            expected_gains=data.get("expected_gains", {}),
            expected_regressions=data.get("expected_regressions", {}),
            risk_tier=risk,
            rationale=data.get("rationale", ""),
            requires_approval=data.get("requires_approval", True),
            reversible=data.get("reversible", True),
        )

        context = AgentContext(mode=OperatingMode(self.mode.lower()))
        try:
            result = await self.tinman.simulation_engine.run(context, interventions=[intervention])
            if result.success:
                self.log_message("Simulation complete", "success")
            else:
                self.log_message(f"Simulation failed: {result.error}", "error")
        except Exception as e:
            self.log_message(f"Simulation failed: {e}", "error")

    async def _deploy_intervention(self) -> None:
        """Deploy selected intervention."""
        if not self.tinman or not self.tinman.graph:
            self.log_message("No graph available", "warning")
            return
        if not self._selected_intervention_id:
            self.log_message("Select an intervention first", "warning")
            return

        try:
            self.tinman.graph.record_deployment(
                intervention_id=self._selected_intervention_id,
                mode=self.mode.lower(),
            )
            self.log_message("Deployment recorded", "success")
        except Exception as e:
            self.log_message(f"Deployment failed: {e}", "error")

    async def _generate_report(self) -> None:
        """Generate a report."""
        if not self.tinman or not self.tinman.graph:
            self.log_message("No data to report", "warning")
            return

        try:
            from ..reporting.lab_reporter import LabReporter

            output_dir = Path(self.settings.reporting.lab_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "report.md"

            reporter = LabReporter(graph=self.tinman.graph)
            report = reporter.generate()
            output_path.write_text(reporter.to_demo_markdown(report), encoding="utf-8")
            self.log_message(f"Report saved: {output_path}", "success")
        except Exception as e:
            self.log_message(f"Report failed: {e}", "error")

    async def _open_latest_report(self) -> None:
        """Open the latest report file."""
        output_dir = Path(self.settings.reporting.lab_output_dir)
        if not output_dir.exists():
            self.log_message("No reports folder", "warning")
            return

        candidates = sorted(output_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            self.log_message("No reports found", "warning")
            return

        report_path = candidates[0]
        try:
            if os.name == "nt":
                os.startfile(report_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                await asyncio.create_subprocess_exec("open", str(report_path))
            else:
                await asyncio.create_subprocess_exec("xdg-open", str(report_path))
            self.log_message(f"Opened: {report_path.name}", "success")
        except Exception as e:
            self.log_message(f"Could not open: {e}", "warning")

    async def _refresh_from_db(self) -> None:
        """Refresh tables from database."""
        if not self.tinman or not self.tinman.graph:
            self.log_message("No database connected", "warning")
            return

        try:
            graph = self.tinman.graph
            hypotheses = graph.get_hypotheses(valid_only=False, limit=50)
            experiments = graph.get_experiments(valid_only=False, limit=50)
            failures = graph.get_failures(valid_only=False, limit=50)
            interventions = graph.get_interventions(valid_only=False, limit=50)

            results = {
                "hypotheses": [
                    {
                        "id": h.id,
                        "expected_failure": h.data.get("expected_failure", ""),
                        "confidence": h.data.get("confidence", 0.0),
                        "status": "active",
                    }
                    for h in hypotheses
                ],
                "experiments": [{"id": e.id} for e in experiments],
                "failures": [
                    {
                        "id": f.id,
                        "primary_class": f.data.get("primary_class", ""),
                        "description": f.data.get("description", ""),
                        "reproducibility": f.data.get("reproducibility", 0.0),
                        "severity": f.data.get("severity", "S2"),
                        "is_novel": f.data.get("is_novel", False),
                    }
                    for f in failures
                ],
                "interventions": [
                    {
                        "id": i.id,
                        "intervention_type": i.data.get("intervention_type", ""),
                        "target_failure_id": i.data.get("failure_id", ""),
                        "risk_tier": i.data.get("risk_tier", "REVIEW"),
                        "status": "proposed",
                    }
                    for i in interventions
                ],
            }

            self._populate_tables(results)
            self._update_metrics(results)
            self.log_message("Refreshed from database", "success")
        except Exception as e:
            self.log_message(f"Refresh failed: {e}", "error")

    async def _handle_chat(self, message: str) -> None:
        """Handle chat message."""
        if not message.strip() or self._chat_inflight:
            return
        self._chat_inflight = True

        self._chat_history.append(("user", message))
        self._update_chat_display()

        if self.tinman and self.tinman.llm:
            try:
                prompt = message
                context = self._build_chat_context()
                if context:
                    prompt = f"{message}\n\nContext:\n{context}"
                response = await self.tinman.discuss(prompt)
                self._chat_history.append(("assistant", response))
            except Exception as e:
                self._chat_history.append(("assistant", f"Error: {e}"))
        else:
            self._chat_history.append(
                ("assistant", "No LLM configured. Configure a model first.")
            )

        self._update_chat_display()
        self._chat_inflight = False

    def _update_chat_display(self) -> None:
        """Update the chat log display."""
        try:
            chat_log = self.query_one("#chat-log", ScrollableContainer)
            for child in list(chat_log.children):
                child.remove()

            if not self._chat_history:
                chat_log.mount(
                    Static(
                        "Ask questions about your research findings.",
                        id="chat-empty",
                        classes="empty-state",
                    )
                )
            else:
                for role, msg in self._chat_history[-20:]:
                    css_class = "user-message" if role == "user" else "assistant-message"
                    prefix = "You: " if role == "user" else "Tinman: "
                    chat_log.mount(Static(f"{prefix}{msg}", classes=css_class))

            chat_log.scroll_end()
        except Exception:
            pass

    def _build_chat_context(self) -> str:
        """Build context for chat."""
        if not self._last_results:
            return ""

        lines = []
        if self._last_focus:
            lines.append(f"Focus: {self._last_focus}")
        lines.append(f"Hypotheses: {len(self._last_results.get('hypotheses', []))}")
        lines.append(f"Experiments: {len(self._last_results.get('experiments', []))}")
        lines.append(f"Failures: {len(self._last_results.get('failures', []))}")

        failures = self._last_results.get("failures", [])
        if failures:
            top = failures[0]
            lines.append(f"Top failure: {top.get('primary_class', '')} - {top.get('description', '')[:60]}")

        return "\n".join(lines)

    async def request_approval(
        self,
        action: str,
        risk_tier: RiskTier,
        details: str,
        cost: str | None = None,
    ) -> bool:
        """Request user approval for an action."""
        tier_str = {
            RiskTier.SAFE: "SAFE",
            RiskTier.REVIEW: "REVIEW",
            RiskTier.BLOCK: "BLOCK",
        }.get(risk_tier, str(risk_tier))

        try:
            get_current_worker()
            return await self.push_screen_wait(
                ApprovalModal(action=action, risk_tier=tier_str, details=details, cost=cost)
            )
        except NoActiveWorker:
            worker = self.run_worker(
                self.push_screen_wait(
                    ApprovalModal(action=action, risk_tier=tier_str, details=details, cost=cost)
                ),
                exclusive=True,
            )
            return await worker.wait()


def run_tui(settings: Settings | None = None) -> None:
    """Run the Tinman TUI."""
    app = TinmanApp(settings=settings)
    app.run()


if __name__ == "__main__":
    run_tui()
