"""Tinman TUI - Main Application."""

import asyncio
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import yaml
from textual.worker import NoActiveWorker, get_current_worker

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
from ..agents.base import AgentContext
from ..utils import generate_id
from .. import __version__

if TYPE_CHECKING:
    from ..tinman import Tinman


# ASCII Art Header
TINMAN_ASCII = r"""
_   _                   
| |_|_|___ _____ ___ ___ 
|  _| |   |     | .'|   |
|_| |_|_|_|_|_|_|__,|_|_|
"""


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


class ModelConfigModal(ModalScreen):
    """Modal for configuring the default model provider/model."""

    def __init__(self, provider: str, model: str, **kwargs):
        super().__init__(**kwargs)
        self._provider = provider
        self._model = model

    def compose(self) -> ComposeResult:
        with Container(id="model-config-modal"):
            yield Label("Default Provider", id="model-provider-label")
            yield Input(value=self._provider, id="model-provider-input")
            yield Label("Default Model", id="model-name-label")
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
    """Tinman Terminal User Interface."""

    TITLE = "TINMAN FDRA"
    SUB_TITLE = "Forward-Deployed Research Agent"

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("f1", "switch_tab('setup')", "Setup", show=True),
        Binding("f2", "switch_tab('run')", "Run", show=True),
        Binding("f3", "switch_tab('review')", "Review", show=True),
        Binding("f4", "switch_tab('actions')", "Actions", show=True),
        Binding("f5", "switch_tab('discuss')", "Discuss", show=True),
        Binding("f6", "config_model", "Model", show=True),
        Binding("f7", "switch_tab('demos')", "Demos", show=True),
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
    DEMO_TEMPLATES = {
        "github": {
            "args": "--repo moltbot/moltbot",
            "env": ["GITHUB_TOKEN"],
        },
        "huggingface": {
            "args": "--model gpt2",
            "env": ["HUGGINGFACE_API_KEY"],
        },
        "replicate": {
            "args": "--version <MODEL_VERSION_ID>",
            "env": ["REPLICATE_API_TOKEN"],
        },
        "fal": {
            "args": "--endpoint https://fal.run/fal-ai/fast-sdxl",
            "env": ["FAL_API_KEY"],
        },
    }

    def __init__(self, settings: Optional[Settings] = None, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings or load_settings()
        self.config_path = self._resolve_config_path()
        self.mode = self.settings.mode.value.upper()
        self.tinman = None  # Lazy load
        self._log_messages: list[tuple[str, str, datetime]] = []
        self._chat_history: list[tuple[str, str]] = []  # (role, message)
        self._pending_approvals: list[dict] = []
        self._last_results: dict = {}
        self._last_focus: Optional[str] = None
        self._chat_inflight = False
        self._run_inflight = False
        self._run_worker = None
        self._setup_status: dict[str, str] = {}
        self._selected_failure_id: Optional[str] = None
        self._selected_intervention_id: Optional[str] = None

    def _resolve_config_path(self) -> Path:
        """Pick the config path Tinman should read/write."""
        preferred = Path(".tinman") / "config.yaml"
        if preferred.exists():
            return preferred
        fallback = Path("tinman.yaml")
        return fallback if fallback.exists() else preferred

    def _update_config_model(self, provider: str, model: str) -> None:
        """Persist model provider/model to config without overwriting comments."""
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
                indent = line[:line.find("d")] if "d" in line else ""
                lines[i] = f"{indent}default: {provider}"
                updated = True
                continue

            if in_providers and stripped.endswith(":") and not stripped.startswith("#"):
                current_provider = stripped[:-1]
                in_target_provider = current_provider == provider
                continue

            if in_target_provider and stripped.startswith("model:"):
                indent = line[:line.find("m")] if "m" in line else "    "
                lines[i] = f"{indent}model: {model}"
                updated = True
                in_target_provider = False
                continue

            if in_models and stripped == "":
                in_models = False
                in_providers = False
                in_target_provider = False

        if not updated:
            # Fallback to YAML update if we can't safely edit in place.
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

        # Update in-memory settings too.
        self.settings.models.default = provider
        if provider not in self.settings.models.providers:
            from ..config.settings import ModelProviderSettings
            self.settings.models.providers[provider] = ModelProviderSettings()
        self.settings.models.providers[provider].model = model

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        with Container(id="main-container"):
            # Header with ASCII art
            with Container(id="header"):
                with Horizontal():
                    yield Static(TINMAN_ASCII, id="ascii-logo")
                    with Vertical(id="header-info"):
                        yield Static("Forward-Deployed Research Agent", classes="header-subtitle")
                        yield Static("GitHub: oliveskin/Agent-Tinman", classes="header-meta")
                        yield Static("Twitter: @cantshutup_", classes="header-meta")
                    with Vertical(id="status-line"):
                        yield Static(f"FDRA v{__version__}", id="version")
                        yield Static(f"Mode: {self.mode}", id="mode-display")
                        yield Static(f"Status: {self.status}", id="status-display")
                        yield Static("Last: —", id="last-event")

            # Navigation buttons
            with Horizontal(id="nav-bar"):
                yield Button("[F1] Setup", id="nav-setup", classes="-active")
                yield Button("[F2] Run", id="nav-run")
                yield Button("[F3] Review", id="nav-review")
                yield Button("[F4] Actions", id="nav-actions")
                yield Button("[F5] Discuss", id="nav-discuss")
                yield Button("[F6] Model", id="nav-model")
                yield Button("[F7] Demos", id="nav-demos")
            # Main content with tabs
            with TabbedContent(id="content"):
                with TabPane("Setup", id="setup"):
                    with ScrollableContainer(id="setup-scroll", classes="tab-scroll"):
                        yield from self._create_setup_panel()
                with TabPane("Run", id="run"):
                    yield from self._create_run_panel()
                with TabPane("Review", id="review"):
                    with ScrollableContainer(id="review-scroll", classes="tab-scroll"):
                        yield from self._create_review_panel()
                with TabPane("Actions", id="actions"):
                    with ScrollableContainer(id="actions-scroll", classes="tab-scroll"):
                        yield from self._create_actions_panel()
                with TabPane("Discuss", id="discuss"):
                    yield from self._create_discuss_panel()
                with TabPane("Model", id="model"):
                    with ScrollableContainer(id="model-scroll", classes="tab-scroll"):
                        yield from self._create_model_panel()
                with TabPane("Demos", id="demos"):
                    with ScrollableContainer(id="demos-scroll", classes="tab-scroll"):
                        yield from self._create_demos_panel()

            # Footer with metrics
            with Horizontal(id="footer"):
                yield Static("Hypotheses: ", classes="metric-label")
                yield Static("0", id="hyp-count", classes="metric-value")
                yield Static(" | Experiments: ", classes="metric-label")
                yield Static("0", id="exp-count", classes="metric-value")
                yield Static(" | Failures: ", classes="metric-label")
                yield Static("0", id="fail-count", classes="metric-value")
                yield Static(" | ", classes="metric-label")
                yield Static("", id="clock", classes="metric-value")

    def _create_setup_panel(self):
        """Create the setup panel."""
        yield Static("═══ SETUP CHECKLIST ═══", classes="panel-title")
        with Container(classes="panel-body"):
            yield Static(
                "Model configured: Unknown\n"
                "API key detected: Unknown\n"
                "Database connected: Unknown",
                id="setup-checklist",
                classes="progress-label",
            )

        yield Static("Actions", classes="panel-title")
        with Container(classes="panel-body"):
            with Horizontal(classes="button-row"):
                yield Button("Configure Model", id="setup-configure-model", variant="primary")
                yield Button("Reload Settings", id="setup-reload", variant="default")
            with Horizontal(classes="button-row"):
                yield Button("Init DB", id="setup-init-db", variant="success")
                yield Button("Check DB", id="setup-check-db", variant="warning")
            yield Static("Tip: Use F6 to open the model picker anytime.", classes="empty-state")

        yield Static("─── Setup Log ───", classes="panel-title")
        with Container(id="setup-log", classes="log-panel"):
            yield Static("No setup activity yet.", id="setup-log-content")

    def _create_run_panel(self):
        """Create the run panel."""
        yield Static("═══ RUN RESEARCH ═══", classes="panel-title")
        with Container(classes="panel-body"):
            with Horizontal(classes="inline-row"):
                yield Static("Focus Area:", id="focus-label", classes="progress-label")
                yield Input(placeholder="e.g., tool_use, long_context, reasoning", id="focus-input")
            with Horizontal(classes="button-row"):
                yield Static("Run Controls:", id="run-controls-label", classes="progress-label")
                yield Button("Start Run", id="start-run", variant="success")
                yield Button("Stop", id="stop-run", variant="error")

        yield Static("─── Activity Log ───", classes="panel-title")
        yield ScrollableContainer(
            Static("Configure a model, then start a run.", id="log-content"),
            id="activity-log",
            classes="log-panel",
        )
        yield Static("Run Summary", classes="panel-title")
        with Container(classes="panel-body"):
            yield Static("No runs yet.", id="run-summary", classes="detail-panel")

    def _create_review_panel(self):
        """Create the review panel."""
        yield Static("═══ REVIEW RESULTS ═══", classes="panel-title")
        with Container(classes="panel-body"):
            yield Static("Summary", classes="progress-label")
            yield Static("Run not started yet.", id="review-summary", classes="empty-state")
            with Horizontal(classes="button-row"):
                yield Button("Generate Demo Report", id="review-demo-report", variant="primary")
                yield Button("Open Latest Report", id="review-open-report", variant="default")
                yield Button("Refresh from DB", id="review-refresh-db", variant="default")

        yield Static("Hypotheses", classes="panel-title")
        table = DataTable(id="review-hypotheses-table")
        table.add_columns("ID", "Hypothesis", "Confidence", "Status")
        yield table
        yield Static("Selected Hypothesis", classes="panel-title")
        yield Static("Select a hypothesis to view details.", id="review-hypothesis-detail",
                     classes="detail-panel")
        yield Static("No hypotheses yet.", id="review-hypotheses-empty", classes="empty-state")
        yield Static("Failures", classes="panel-title")
        table = DataTable(id="review-failures-table")
        table.add_columns("Sev", "Class", "Description", "Repro%", "Status")
        yield table
        yield Static("No failures yet.", id="review-failures-empty", classes="empty-state")
        yield Static("Interventions", classes="panel-title")
        table = DataTable(id="review-interventions-table")
        table.add_columns("ID", "Type", "Target Failure", "Est. Effect", "Status")
        yield table
        yield Static("No interventions yet.", id="review-interventions-empty", classes="empty-state")
        yield Static("─── Review Log ───", classes="panel-title")
        with Container(id="review-log", classes="log-panel"):
            yield Static("No review activity yet.", id="review-log-content")

    def _create_actions_panel(self):
        """Create the actions panel."""
        yield Static("═══ ACTIONS ═══", classes="panel-title")
        with Container(classes="panel-body"):
            yield Static("Select a failure to design interventions.", classes="empty-state")
        yield Static("Failures", classes="panel-title")
        table = DataTable(id="actions-failures-table")
        table.add_columns("ID", "Class", "Description")
        yield table
        yield Static("Interventions", classes="panel-title")
        table = DataTable(id="actions-interventions-table")
        table.add_columns("ID", "Type", "Target", "Status")
        yield table
        with Container(classes="panel-body"):
            with Horizontal(classes="button-row"):
                yield Button("Design Intervention", id="action-design", variant="primary")
                yield Button("Simulate", id="action-simulate", variant="warning")
                yield Button("Deploy", id="action-deploy", variant="success")
        yield Static("─── Actions Log ───", classes="panel-title")
        with Container(id="actions-log", classes="log-panel"):
            yield Static("No action activity yet.", id="actions-log-content")

    def _create_demos_panel(self):
        """Create the demos panel."""
        yield Static("═══ DEMO RUNNER ═══", classes="panel-title")
        with Container(classes="panel-body"):
            yield Static("Run built-in provider demos with editable arguments.", classes="empty-state")
            yield Static("Required keys: GITHUB_TOKEN, HUGGINGFACE_API_KEY, REPLICATE_API_TOKEN, FAL_API_KEY", classes="demo-warning")
            yield Static("Select Demo", classes="progress-label")
            with Horizontal(classes="button-row"):
                yield Button("GitHub", id="demo-select-github", variant="primary")
                yield Button("HuggingFace", id="demo-select-huggingface", variant="default")
                yield Button("Replicate", id="demo-select-replicate", variant="default")
                yield Button("fal.ai", id="demo-select-fal", variant="default")
            with Horizontal(classes="inline-row demo-field-row"):
                yield Static("Demo:", id="demo-name-label", classes="progress-label")
                yield Input(value="github", id="demo-name-input")
            with Horizontal(classes="inline-row demo-field-row"):
                yield Static("Args:", id="demo-args-label", classes="progress-label")
                yield Input(
                    placeholder="e.g., --repo moltbot/moltbot",
                    id="demo-args-input",
                )
            yield Static("Env Status: unknown", id="demo-env-status", classes="demo-status")
            with Horizontal(classes="button-row"):
                yield Button("Use Defaults", id="demo-defaults", variant="default")
                yield Button("Check Env", id="demo-check-env", variant="default")
                yield Button("Run Demo", id="demo-run", variant="success")
            yield Static("Tip: Set provider keys in your shell before running demos.", classes="empty-state")

        yield Static("─── Demo Output ───", classes="panel-title")
        with Container(id="demos-log", classes="log-panel"):
            yield Static("No demo output yet.", id="demos-log-content")

    def _create_discuss_panel(self):
        """Create the chat/discuss panel."""
        yield Static("═══ RESEARCH DIALOGUE ═══", classes="panel-title")
        with Container(classes="panel-body"):
            yield ScrollableContainer(
                Static("No messages yet. Ask a question to start a conversation.", id="chat-empty",
                       classes="empty-state"),
                id="chat-log"
            )
            yield Input(placeholder="Type your message and press Enter...", id="chat-input")

    def _create_model_panel(self):
        """Create the model panel."""
        provider = self.settings.models.default
        provider_settings = self.settings.models.providers.get(provider)
        model = provider_settings.model if provider_settings else ""
        api_key = provider_settings.api_key if provider_settings else ""
        key_status = "OK" if api_key else "Missing"

        yield Static("═══ MODEL CONFIG ═══", classes="panel-title")
        with Container(classes="panel-body"):
            yield Static(f"Default Provider: {provider}", classes="progress-label")
            yield Static(f"Default Model: {model or 'Unknown'}", classes="progress-label")
            yield Static(f"API Key: {key_status}", classes="progress-label")
            with Horizontal(classes="button-row"):
                yield Button("Edit Default Model", id="model-edit", variant="primary")
        yield Static("Providers in config:", classes="panel-title")
        with Container(classes="panel-body"):
            for name in sorted(self.settings.models.providers.keys()):
                yield Static(f"- {name}", classes="empty-state")
        yield Static("─── Model Log ───", classes="panel-title")
        with Container(id="model-log", classes="log-panel"):
            yield Static("No model changes yet.", id="model-log-content")

    async def on_mount(self) -> None:
        """Initialize when app mounts."""
        self.log_message("Tinman TUI initialized", "success")
        self.log_message(f"Mode: {self.mode}", "info")
        self.log_message("Press F1-F7 to navigate, F10 to quit", "info")

        # Start clock update
        self.set_interval(1, self._update_clock)

        # Initialize Tinman in background
        self.run_worker(self._init_tinman())
        self.run_worker(self._refresh_setup_status())
        self._set_demo_defaults("github")

    async def _init_tinman(self) -> None:
        """Initialize Tinman instance."""
        try:
            from ..tinman import create_tinman
            from ..cli.main import get_model_client

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
                self.log_message(f"DB init failed, continuing without DB: {e}", "warning")
                self.tinman = await create_tinman(
                    model_client=model_client,
                    mode=OperatingMode(self.mode.lower()),
                    skip_db=True,
                )

            # Register TUI as the approval UI
            self.tinman.register_approval_ui(self._tui_approval_callback)
            self.log_message("Tinman core initialized with HITL approval", "success")
        except Exception as e:
            self.log_message(f"Tinman init warning: {e}", "warning")

    async def _refresh_setup_status(self) -> None:
        """Refresh setup checklist status."""
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
            "model": ("OK" if model_ok else "Missing"),
            "key": ("OK" if key_ok else "Missing"),
            "db": ("OK" if db_ok else "Not connected"),
        }

        try:
            checklist = self.query_one("#setup-checklist", Static)
            checklist.update(
                "Model configured: "
                f"{self._setup_status['model']}\n"
                "API key detected: "
                f"{self._setup_status['key']}\n"
                "Database connected: "
                f"{self._setup_status['db']}"
            )
        except Exception:
            pass

    async def _init_db(self) -> None:
        """Initialize database and create tables."""
        try:
            from ..db.connection import ensure_database
            info = await asyncio.to_thread(ensure_database, self.settings.database_url)
            created = "created" if info.get("created") else "already exists"
            self.log_message(f"{info['backend']} database {created}: {info['database']}", "success")
        except Exception as e:
            self.log_message(f"Database init failed: {e}", "error")
        await self._refresh_setup_status()

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

        rendered = "\n".join(lines)
        for widget_id in (
            "#log-content",
            "#setup-log-content",
            "#review-log-content",
            "#actions-log-content",
            "#demos-log-content",
            "#model-log-content",
        ):
            try:
                self.query_one(widget_id, Static).update(rendered)
            except Exception:
                pass
        try:
            self.query_one("#last-event", Static).update(
                f"Last: {message[:28]}{'…' if len(message) > 28 else ''}"
            )
        except Exception:
            pass  # UI not ready yet

    def _toggle_empty(self, widget_id: str, show: bool) -> None:
        """Show/hide empty-state helpers."""
        try:
            widget = self.query_one(f"#{widget_id}", Static)
            widget.display = show
        except Exception:
            pass

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
        for widget_id in (
            "#log-content",
            "#setup-log-content",
            "#review-log-content",
            "#actions-log-content",
            "#demos-log-content",
            "#model-log-content",
        ):
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
        self.log_message(
            f"Model config updated: {result['provider']} / {result['model']}.",
            "success",
        )
        if self.tinman:
            self.log_message("Restart TUI to apply changes to a running session.", "warning")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        self._flash_button(event.button)

        # Navigation
        if button_id and button_id.startswith("nav-"):
            if button_id == "nav-model":
                self.action_config_model()
                return
            tab = button_id.replace("nav-", "")
            self.action_switch_tab(tab)
            return

        # Setup controls
        if button_id == "setup-configure-model":
            self.action_config_model()
        elif button_id == "setup-reload":
            self.settings = load_settings()
            self.run_worker(self._refresh_setup_status())
            self.log_message("Settings reloaded", "success")
        elif button_id == "setup-check-db":
            self.run_worker(self._refresh_setup_status())
            self.log_message("Database check complete", "info")
        elif button_id == "setup-init-db":
            self.run_worker(self._init_db())
            self.log_message("Database init requested", "info")

        # Run controls
        elif button_id == "start-run":
            if not self._run_inflight:
                self._run_worker = self.run_worker(self._start_research(), exclusive=True)
        elif button_id == "stop-run":
            if self._run_worker:
                self._run_worker.cancel()
                self._run_worker = None
            self.status = "IDLE"
            self.query_one("#status-display", Static).update(f"Status: {self.status}")
            self._run_inflight = False
            self.log_message("Run cancelled", "warning")

        # Actions controls
        elif button_id == "action-design":
            self.run_worker(self._design_intervention(), exclusive=True)
        elif button_id == "action-simulate":
            self.run_worker(self._simulate_intervention(), exclusive=True)
        elif button_id == "action-deploy":
            self.run_worker(self._deploy_intervention(), exclusive=True)
        elif button_id == "review-demo-report":
            self.run_worker(self._generate_demo_report(), exclusive=True)
        elif button_id == "review-open-report":
            self.run_worker(self._open_latest_report(), exclusive=True)
        elif button_id == "review-refresh-db":
            self.run_worker(self._refresh_review_from_db(), exclusive=True)
        # Demo controls
        elif button_id == "demo-select-github":
            self._set_demo_defaults("github")
        elif button_id == "demo-select-huggingface":
            self._set_demo_defaults("huggingface")
        elif button_id == "demo-select-replicate":
            self._set_demo_defaults("replicate")
        elif button_id == "demo-select-fal":
            self._set_demo_defaults("fal")
        elif button_id == "model-edit":
            self.action_config_model()
        elif button_id == "demo-defaults":
            self._set_demo_defaults(self._current_demo_name())
        elif button_id == "demo-check-env":
            self.run_worker(self._run_demo(check_only=True), exclusive=True)
        elif button_id == "demo-run":
            self.run_worker(self._run_demo(check_only=False), exclusive=True)

    def _flash_button(self, button: Button) -> None:
        """Briefly highlight a pressed button for visual feedback."""
        try:
            button.add_class("pressed")
            self.set_timer(0.2, lambda: button.remove_class("pressed"))
        except Exception:
            pass

    def _current_demo_name(self) -> str:
        try:
            return self.query_one("#demo-name-input", Input).value.strip()
        except Exception:
            return ""

    def _set_demo_defaults(self, demo: str, args: Optional[str] = None) -> None:
        template = self.DEMO_TEMPLATES.get(demo, {})
        default_args = args if args is not None else template.get("args", "")
        try:
            self.query_one("#demo-name-input", Input).value = demo
            self.query_one("#demo-args-input", Input).value = default_args
        except Exception:
            pass
        self._update_demo_env_status(demo)

    def _update_demo_env_status(self, demo: str) -> None:
        template = self.DEMO_TEMPLATES.get(demo, {})
        required = template.get("env", [])
        missing = [name for name in required if not os.environ.get(name)]
        status = "OK" if not missing else f"Missing: {', '.join(missing)}"
        try:
            widget = self.query_one("#demo-env-status", Static)
            widget.update(f"Env Status: {status}")
            widget.remove_class("demo-status-ok", "demo-status-missing")
            widget.add_class("demo-status-ok" if not missing else "demo-status-missing")
        except Exception:
            pass

    async def _run_demo(self, check_only: bool) -> None:
        """Run demo scripts via subprocess and stream output to log."""
        try:
            demo = self.query_one("#demo-name-input", Input).value.strip()
            args = self.query_one("#demo-args-input", Input).value.strip()
        except Exception:
            self.log_message("Demo inputs not available.", "error")
            return

        if not demo:
            self.log_message("Select a demo first.", "warning")
            return

        extra_args = []
        if args:
            try:
                extra_args = shlex.split(args, posix=False)
            except Exception:
                self.log_message("Unable to parse args. Check quoting.", "error")
                return

        if check_only:
            cmd = [sys.executable, "-m", "tinman.demo.env_check", demo]
        else:
            cmd = [sys.executable, "-m", "tinman.demo.runner", demo] + extra_args
        self._update_demo_env_status(demo)

        self.log_message(f"Running: {' '.join(cmd)}", "info")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            self.log_message(f"Failed to start demo: {e}", "error")
            return

        # Show missing env warnings based on exit code
        if proc.stdout:
            async for line in proc.stdout:
                try:
                    self.log_message(line.decode(errors="ignore").rstrip(), "info")
                except Exception:
                    pass

        exit_code = await proc.wait()
        if exit_code == 0:
            self.log_message("Demo completed.", "success")
        else:
            if check_only:
                self.log_message("Missing required keys. See log for details.", "warning")
            self.log_message(f"Demo exited with code {exit_code}.", "warning")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submissions."""
        if event.input.id == "chat-input":
            self.run_worker(self._handle_chat(event.value), exclusive=True)
            event.input.value = ""

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        if table_id == "review-hypotheses-table":
            row = event.data_table.get_row(event.row_key)
            if row:
                detail = (
                    f"ID: {row[0]} | Confidence: {row[2]} | Status: {row[3]}\n"
                    f"{row[1]}"
                )
                self._toggle_empty("review-hypotheses-empty", False)
            else:
                detail = "Select a hypothesis to view details."
            try:
                self.query_one("#review-hypothesis-detail", Static).update(detail)
            except Exception:
                pass
        elif table_id == "actions-failures-table":
            row = event.data_table.get_row(event.row_key)
            self._selected_failure_id = row[0] if row else None
            self.log_message(f"Selected failure: {self._selected_failure_id}", "info")
        elif table_id == "actions-interventions-table":
            row = event.data_table.get_row(event.row_key)
            self._selected_intervention_id = row[0] if row else None
            self.log_message(f"Selected intervention: {self._selected_intervention_id}", "info")

    async def _start_research(self) -> None:
        """Start a research cycle."""
        self._run_inflight = True
        self.status = "RUNNING"
        self.query_one("#status-display", Static).update(f"Status: {self.status}")

        focus_input = self.query_one("#focus-input", Input)
        focus = focus_input.value or None

        self.log_message("Starting research cycle...", "info")
        if focus:
            self.log_message(f"Focus area: {focus}", "info")

        if not self.tinman or not self.tinman.llm:
            self.log_message("No LLM configured. Update models in config to run research.", "warning")
            self.status = "IDLE"
            self.query_one("#status-display", Static).update(f"Status: {self.status}")
            self._run_inflight = False
            return

        try:
            self.log_message("Running research cycle...", "info")
            results = await self.tinman.research_cycle(focus=focus)
        except Exception as e:
            self.log_message(f"Research failed: {e}", "error")
            self.status = "IDLE"
            self.query_one("#status-display", Static).update(f"Status: {self.status}")
            self._run_inflight = False
            return

        self._last_results = results
        self._last_focus = focus
        self._populate_review(results)
        self._populate_actions(results)
        self.experiment_count = len(results.get("experiments", []))
        self._update_metrics()
        self._update_run_summary(results)
        self.log_message("Research cycle complete", "success")

        self.status = "IDLE"
        self.query_one("#status-display", Static).update(f"Status: {self.status}")
        self._run_inflight = False
        self._run_worker = None

    async def _design_intervention(self) -> None:
        """Design interventions for the selected failure."""
        if not self.tinman or not self.tinman.intervention_engine:
            self.log_message("Intervention engine not initialized.", "warning")
            return
        if not self._selected_failure_id:
            self.log_message("Select a failure in Actions to design interventions.", "warning")
            return
        if not self.tinman.graph:
            self.log_message("No graph available for failure details.", "warning")
            return

        from ..agents.failure_discovery import DiscoveredFailure
        from ..taxonomy.failure_types import FailureClass, Severity
        node = self.tinman.graph.get_node(self._selected_failure_id)
        if not node:
            self.log_message("Selected failure not found in graph.", "warning")
            return

        data = {"id": node.id, **(node.data or {})}
        try:
            primary = FailureClass(data.get("primary_class", "reasoning"))
        except Exception:
            primary = FailureClass.REASONING
        severity = data.get("severity", "S2")
        try:
            sev_enum = Severity[severity]
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
            result = await self.tinman.intervention_engine.run(
                context, failures=[failure]
            )
        except Exception as e:
            self.log_message(f"Intervention design failed: {e}", "error")
            return

        if result.success:
            self._populate_actions({
                "failures": [data],
                "interventions": result.data.get("interventions", []),
            })
            self.log_message("Intervention design complete.", "success")
        else:
            self.log_message(f"Intervention design failed: {result.error}", "error")

    async def _simulate_intervention(self) -> None:
        """Simulate the selected intervention."""
        if not self.tinman or not self.tinman.simulation_engine:
            self.log_message("Simulation engine not initialized.", "warning")
            return
        if not self._selected_intervention_id:
            self.log_message("Select an intervention in Actions to simulate.", "warning")
            return
        if not self.tinman.graph:
            self.log_message("No graph available for intervention details.", "warning")
            return

        from ..agents.intervention_engine import Intervention, InterventionType
        from ..core.risk_evaluator import RiskTier

        node = self.tinman.graph.get_node(self._selected_intervention_id)
        if not node:
            self.log_message("Selected intervention not found in graph.", "warning")
            return

        data = node.data or {}
        type_raw = data.get("intervention_type", "prompt_patch")
        try:
            itype = InterventionType(type_raw)
        except Exception:
            itype = InterventionType.PROMPT_PATCH
        risk_raw = data.get("risk_tier", "review")
        try:
            risk = RiskTier(risk_raw)
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
        if not intervention.failure_id:
            self.log_message("Selected intervention is missing a failure_id.", "warning")
            return

        context = AgentContext(mode=OperatingMode(self.mode.lower()))
        try:
            result = await self.tinman.simulation_engine.run(
                context, interventions=[intervention]
            )
        except Exception as e:
            self.log_message(f"Simulation failed: {e}", "error")
            return

        if result.success:
            self.log_message("Simulation complete.", "success")
        else:
            self.log_message(f"Simulation failed: {result.error}", "error")

    async def _deploy_intervention(self) -> None:
        """Record a deployment for the selected intervention."""
        if not self.tinman or not self.tinman.graph:
            self.log_message("No graph available for deployment.", "warning")
            return
        if not self._selected_intervention_id:
            self.log_message("Select an intervention in Actions to deploy.", "warning")
            return

        try:
            self.tinman.graph.record_deployment(
                intervention_id=self._selected_intervention_id,
                mode=self.mode.lower(),
            )
            self.log_message("Deployment recorded.", "success")
        except Exception as e:
            self.log_message(f"Deployment failed: {e}", "error")

    async def _generate_demo_report(self) -> None:
        """Generate a demo report to the lab output directory."""
        if not self.tinman or not self.tinman.graph:
            self.log_message("No database configured. Demo report requires a DB.", "warning")
            return

        try:
            from ..reporting.lab_reporter import LabReporter
            output_dir = Path(self.settings.reporting.lab_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "demo-report.md"

            reporter = LabReporter(graph=self.tinman.graph)
            report = reporter.generate()
            output_path.write_text(reporter.to_demo_markdown(report), encoding="utf-8")
            self.log_message(f"Demo report written to {output_path}", "success")
        except Exception as e:
            self.log_message(f"Demo report failed: {e}", "error")

    async def _refresh_review_from_db(self) -> None:
        """Refresh review tables directly from the memory graph."""
        if not self.tinman or not self.tinman.graph:
            self.log_message("No database configured. Refresh requires a DB.", "warning")
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
                    } for h in hypotheses
                ],
                "experiments": [
                    {
                        "id": e.id,
                        "stress_type": e.data.get("stress_type", ""),
                        "hypothesis_id": e.data.get("hypothesis_id", ""),
                    } for e in experiments
                ],
                "failures": [
                    {
                        "id": f.id,
                        "primary_class": f.data.get("primary_class", ""),
                        "description": f.data.get("description", ""),
                        "reproducibility": f.data.get("reproducibility", 0.0),
                        "severity": f.data.get("severity", "S2"),
                        "is_novel": f.data.get("is_novel", False),
                    } for f in failures
                ],
                "interventions": [
                    {
                        "id": i.id,
                        "intervention_type": i.data.get("intervention_type", ""),
                        "target_failure_id": i.data.get("failure_id", ""),
                        "expected_improvement": i.data.get("expected_gains", {}).get(
                            "failure_reduction", ""
                        ),
                        "status": "proposed",
                    } for i in interventions
                ],
            }

            self._populate_review(results)
            self._populate_actions(results)
            self.hypothesis_count = len(hypotheses)
            self.experiment_count = len(experiments)
            self.failure_count = len(failures)
            self.intervention_count = len(interventions)
            self._update_metrics()
            self.log_message("Review refreshed from DB.", "success")
        except Exception as e:
            self.log_message(f"Refresh failed: {e}", "error")

    async def _open_latest_report(self) -> None:
        """Open the latest report file if present."""
        output_dir = Path(self.settings.reporting.lab_output_dir)
        if not output_dir.exists():
            self.log_message("Report folder not found.", "warning")
            return

        candidates = sorted(output_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            self.log_message("No reports found.", "warning")
            return

        report_path = candidates[0]
        try:
            if os.name == "nt":
                os.startfile(report_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                await asyncio.create_subprocess_exec("open", str(report_path))
            else:
                await asyncio.create_subprocess_exec("xdg-open", str(report_path))
            self.log_message(f"Opened {report_path}", "success")
        except Exception as e:
            self.log_message(f"Could not open report: {e}", "warning")

    async def _handle_chat(self, message: str) -> None:
        """Handle chat message."""
        if not message.strip() or self._chat_inflight:
            return
        self._chat_inflight = True

        # Add user message
        self._chat_history.append(("user", message))
        self._update_chat_display()

        # Generate response
        if self.tinman and self.tinman.llm:
            self.log_message("Processing with LLM...", "info")
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
                ("assistant", "No LLM configured. Set models.default and API key in config.")
            )

        self._update_chat_display()
        self._chat_inflight = False

    def _update_chat_display(self) -> None:
        """Update the chat log display."""
        try:
            chat_log = self.query_one("#chat-log", ScrollableContainer)
            # Clear and rebuild
            for child in list(chat_log.children):
                child.remove()
            if not self._chat_history:
                chat_log.mount(
                    Static("No messages yet. Ask a question to start a conversation.",
                           id="chat-empty", classes="empty-state")
                )
            else:
                for role, msg in self._chat_history[-20:]:  # Last 20 messages
                    css_class = "user-message" if role == "user" else "assistant-message"
                    prefix = "YOU: " if role == "user" else "TINMAN: "
                    chat_log.mount(Static(f"{prefix}{msg}", classes=css_class))

            chat_log.scroll_end()
        except Exception:
            pass

    def _populate_review(self, results: dict) -> None:
        hypotheses = results.get("hypotheses", [])
        failures = results.get("failures", [])
        interventions = results.get("interventions", [])

        summary = (
            f"Hypotheses: {len(hypotheses)} • "
            f"Experiments: {len(results.get('experiments', []))} • "
            f"Failures: {len(failures)} • "
            f"Interventions: {len(interventions)}"
        )
        try:
            self.query_one("#review-summary", Static).update(summary)
        except Exception:
            pass

        h_table = self.query_one("#review-hypotheses-table", DataTable)
        h_table.clear()
        for h in hypotheses:
            h_table.add_row(
                h.get("id", ""),
                h.get("expected_failure", ""),
                f"{h.get('confidence', 0):.2f}",
                h.get("priority", "new"),
            )
        self._toggle_empty("review-hypotheses-empty", len(hypotheses) == 0)
        if len(hypotheses) == 0:
            try:
                self.query_one("#review-hypothesis-detail", Static).update(
                    "Select a hypothesis to view details."
                )
            except Exception:
                pass
        if len(hypotheses) == 0:
            try:
                self.query_one("#review-hypothesis-detail", Static).update(
                    "Select a hypothesis to view details."
                )
            except Exception:
                pass

        f_table = self.query_one("#review-failures-table", DataTable)
        f_table.clear()
        for f in failures:
            f_table.add_row(
                f.get("severity", ""),
                f.get("primary_class", ""),
                f.get("description", "")[:80],
                f"{int((f.get('reproducibility', 0) or 0) * 100)}%",
                "new" if f.get("is_novel") else "active",
            )
        self._toggle_empty("review-failures-empty", len(failures) == 0)

        i_table = self.query_one("#review-interventions-table", DataTable)
        i_table.clear()
        for i in interventions:
            i_table.add_row(
                i.get("id", ""),
                i.get("intervention_type", ""),
                i.get("target_failure_id", ""),
                i.get("expected_improvement", ""),
                i.get("status", "proposed"),
            )
        self._toggle_empty("review-interventions-empty", len(interventions) == 0)

    def _populate_actions(self, results: dict) -> None:
        failures = results.get("failures", [])
        interventions = results.get("interventions", [])

        f_table = self.query_one("#actions-failures-table", DataTable)
        f_table.clear()
        for f in failures:
            f_table.add_row(
                f.get("id", ""),
                f.get("primary_class", ""),
                f.get("description", "")[:80],
            )

        i_table = self.query_one("#actions-interventions-table", DataTable)
        i_table.clear()
        for i in interventions:
            i_table.add_row(
                i.get("id", ""),
                i.get("intervention_type", ""),
                i.get("target_failure_id", ""),
                i.get("status", "proposed"),
            )

    def _build_chat_context(self) -> str:
        """Build a compact context summary for discuss."""
        if not self._last_results:
            return ""

        hypotheses = self._last_results.get("hypotheses", [])
        failures = self._last_results.get("failures", [])
        interventions = self._last_results.get("interventions", [])
        experiments = self._last_results.get("experiments", [])

        lines = []
        if self._last_focus:
            lines.append(f"Focus: {self._last_focus}")
        lines.append(f"Hypotheses: {len(hypotheses)}")
        lines.append(f"Experiments: {len(experiments)}")
        lines.append(f"Failures: {len(failures)}")
        lines.append(f"Interventions: {len(interventions)}")

        if failures:
            top_fail = failures[0]
            lines.append(
                f"Top failure: {top_fail.get('primary_class', '')} - "
                f"{top_fail.get('description', '')[:80]}"
            )
        if hypotheses:
            top_h = hypotheses[0]
            lines.append(
                f"Top hypothesis: {top_h.get('expected_failure', '')[:80]}"
            )
        return "\n".join(lines)

    def _update_metrics(self) -> None:
        """Update footer metrics."""
        try:
            self.query_one("#hyp-count", Static).update(str(self.hypothesis_count))
            self.query_one("#exp-count", Static).update(str(self.experiment_count))
            self.query_one("#fail-count", Static).update(str(self.failure_count))
        except Exception:
            pass

    def _update_run_summary(self, results: dict) -> None:
        """Update the run summary panel."""
        hypotheses = len(results.get("hypotheses", []))
        experiments = len(results.get("experiments", []))
        failures = len(results.get("failures", []))
        interventions = len(results.get("interventions", []))
        focus = self._last_focus or "General"
        summary = (
            f"Focus: {focus}\n"
            f"Hypotheses: {hypotheses} | Experiments: {experiments} | "
            f"Failures: {failures} | Interventions: {interventions}"
        )
        try:
            self.query_one("#run-summary", Static).update(summary)
        except Exception:
            pass

    async def _request_approval_modal(
        self,
        action: str,
        risk_tier: RiskTier,
        details: str,
        cost: Optional[str] = None,
    ) -> bool:
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

    async def request_approval(
        self,
        action: str,
        risk_tier: RiskTier,
        details: str,
        cost: Optional[str] = None,
    ) -> bool:
        """Request user approval for an action."""
        try:
            get_current_worker()
            return await self._request_approval_modal(action, risk_tier, details, cost)
        except NoActiveWorker:
            worker = self.run_worker(
                self._request_approval_modal(action, risk_tier, details, cost),
                exclusive=True,
            )
            return await worker.wait()


def run_tui(settings: Optional[Settings] = None) -> None:
    """Run the Tinman TUI."""
    app = TinmanApp(settings=settings)
    app.run()


if __name__ == "__main__":
    run_tui()
