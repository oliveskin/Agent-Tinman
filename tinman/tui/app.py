"""Tinman TUI - Main Application."""

import asyncio
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
from ..utils import generate_id
from .. import __version__

if TYPE_CHECKING:
    from ..tinman import Tinman


# ASCII Art Header
TINMAN_ASCII = r"""
 _____ _ _   _ __  __    _    _   _
|_   _| | \ | |  \/  |  / \  | \ | |
  | | | |  \| | |\/| | / _ \ |  \| |
  | | | | |\  | |  | |/ ___ \| |\  |
  |_| |_|_| \_|_|  |_/_/   \_\_| \_|
"""

TINMAN_ASCII_SMALL = r"""
 _______ _ _   _ __  __   _   _
|_   _ _| | \ | |  \/  | | \ | |
  | | | | |  \| | |\/| | |  \| |
  |_| |_|_| |\  |_|  |_| |_| \_|
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
            yield Static("!! APPROVAL REQUIRED !!", classes="modal-title")
            yield Static(f"Action: {self.action}", classes="modal-content")
            yield Static(f"Risk: {self.risk_tier}", classes="modal-content")
            if self.cost:
                yield Static(f"Est. Cost: {self.cost}", classes="modal-content")
            if not self.is_reversible:
                yield Static("!! WARNING: This action is NOT reversible!", classes="modal-content")
            yield Static("-" * 50, classes="modal-content")
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
            with Container(id="terminal-frame"):
                with Horizontal(id="window-bar"):
                    yield Static("ooo", id="window-controls")
                    yield Static("tinman@fdra - research console", id="window-title")
                    yield Static(f"v{__version__}", id="window-version")

                # Header with ASCII art
                with Container(id="header"):
                    with Horizontal():
                        yield Static(TINMAN_ASCII_SMALL, id="ascii-logo")
                        with Vertical(id="status-line"):
                            yield Static("Forward-Deployed Research Agent", id="tagline")
                            yield Static(f"Mode: {self.mode}", id="mode-display")
                            yield Static(f"Status: {self.status}", id="status-display")

                # Navigation buttons
                with Horizontal(id="nav-bar"):
                    yield Button("[F1] Setup", id="nav-setup", classes="-active")
                    yield Button("[F2] Run", id="nav-run")
                    yield Button("[F3] Review", id="nav-review")
                    yield Button("[F4] Actions", id="nav-actions")
                    yield Button("[F5] Discuss", id="nav-discuss")
                    yield Button("[F6] Model", id="nav-model")

                # Main content with tabs
                with TabbedContent(id="content"):
                    with TabPane("Setup", id="setup"):
                        yield from self._create_setup_panel()
                    with TabPane("Run", id="run"):
                        yield from self._create_run_panel()
                    with TabPane("Review", id="review"):
                        yield from self._create_review_panel()
                    with TabPane("Actions", id="actions"):
                        yield from self._create_actions_panel()
                    with TabPane("Discuss", id="discuss"):
                        yield from self._create_discuss_panel()

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
        yield Static("=== SETUP CHECKLIST ===", classes="panel-title")
        yield Static("")
        yield Static("Model configured:", classes="progress-label")
        yield Static("Unknown", id="setup-model-status", classes="status-muted")
        yield Static("API key detected:", classes="progress-label")
        yield Static("Unknown", id="setup-key-status", classes="status-muted")
        yield Static("Database connected:", classes="progress-label")
        yield Static("Unknown", id="setup-db-status", classes="status-muted")
        yield Static("")
        yield Horizontal(
            Button("Configure Model", id="setup-configure-model", variant="primary"),
            Button("Reload Settings", id="setup-reload", variant="default"),
            Button("Check DB", id="setup-check-db", variant="warning"),
        )
        yield Static("")
        yield Static("Tip: Use F6 to open the model picker anytime.", classes="empty-state")

    def _create_run_panel(self):
        """Create the run panel."""
        yield Static("=== RUN RESEARCH ===", classes="panel-title")
        yield Static("")
        yield Static("Focus Area:", classes="progress-label")
        yield Input(placeholder="e.g., tool_use, long_context, reasoning", id="focus-input")
        yield Static("")
        yield Static("Run Controls:", classes="progress-label")
        yield Horizontal(
            Button("Start Run", id="start-run", variant="success"),
            Button("Stop", id="stop-run", variant="error"),
            classes="cta-row",
        )
        yield Static("")
        yield Static("--- Activity Log ---", classes="panel-title")
        yield ScrollableContainer(
            Static("Configure a model, then start a run.", id="log-content"),
            id="activity-log"
        )

    def _create_review_panel(self):
        """Create the review panel."""
        yield Static("=== REVIEW RESULTS ===", classes="panel-title")
        yield Static("")
        yield Static("Summary", classes="progress-label")
        yield Static("Run not started yet.", id="review-summary", classes="empty-state")
        yield Static("")
        yield Static("Hypotheses", classes="panel-title")
        table = DataTable(id="review-hypotheses-table")
        table.add_columns("ID", "Hypothesis", "Confidence", "Status")
        yield table
        yield Static("No hypotheses yet.", id="review-hypotheses-empty", classes="empty-state")
        yield Static("")
        yield Static("Failures", classes="panel-title")
        table = DataTable(id="review-failures-table")
        table.add_columns("Sev", "Class", "Description", "Repro%", "Status")
        yield table
        yield Static("No failures yet.", id="review-failures-empty", classes="empty-state")
        yield Static("")
        yield Static("Interventions", classes="panel-title")
        table = DataTable(id="review-interventions-table")
        table.add_columns("ID", "Type", "Target Failure", "Est. Effect", "Status")
        yield table
        yield Static("No interventions yet.", id="review-interventions-empty", classes="empty-state")

    def _create_actions_panel(self):
        """Create the actions panel."""
        yield Static("=== ACTIONS ===", classes="panel-title")
        yield Static("")
        yield Static("Select a failure to design interventions.", classes="empty-state")
        table = DataTable(id="actions-failures-table")
        table.add_columns("ID", "Class", "Description")
        yield table
        yield Static("")
        yield Static("Interventions", classes="panel-title")
        table = DataTable(id="actions-interventions-table")
        table.add_columns("ID", "Type", "Target", "Status")
        yield table
        yield Static("")
        yield Horizontal(
            Button("Design Intervention", id="action-design", variant="primary"),
            Button("Simulate", id="action-simulate", variant="warning"),
            Button("Deploy", id="action-deploy", variant="success"),
        )

    def _create_discuss_panel(self):
        """Create the chat/discuss panel."""
        yield Static("=== DISCUSS ===", classes="panel-title")
        yield ScrollableContainer(
            Static("No messages yet. Ask a question to start a conversation.", id="chat-empty",
                   classes="empty-state"),
            id="chat-log"
        )
        yield Input(placeholder="Type your message and press Enter...", id="chat-input")

    async def on_mount(self) -> None:
        """Initialize when app mounts."""
        self.log_message("Tinman TUI initialized", "success")
        self.log_message(f"Mode: {self.mode}", "info")
        self.log_message("Press F1-F6 to navigate, F10 to quit", "info")

        # Start clock update
        self.set_interval(1, self._update_clock)

        # Initialize Tinman in background
        self.run_worker(self._init_tinman())
        self.run_worker(self._refresh_setup_status())

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

        def _apply_status(widget_id: str, ok: bool, text: str) -> None:
            try:
                widget = self.query_one(f"#{widget_id}", Static)
                widget.update(text)
                widget.remove_class("status-ok", "status-warn", "status-muted")
                widget.add_class("status-ok" if ok else "status-warn")
            except Exception:
                pass

        _apply_status("setup-model-status", model_ok, self._setup_status["model"])
        _apply_status("setup-key-status", key_ok, self._setup_status["key"])
        _apply_status("setup-db-status", db_ok, self._setup_status["db"])

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
                    "info": "|",
                    "success": ">",
                    "warning": "!",
                    "error": "x",
                }.get(lvl, "|")
                time_str = ts.strftime("%H:%M:%S")
                lines.append(f"{prefix} [{time_str}] {msg}")

            log_content.update("\n".join(lines))
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
        try:
            log_content = self.query_one("#log-content", Static)
            log_content.update("Log cleared.")
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

        # Run controls
        elif button_id == "start-run":
            if not self._run_inflight:
                self.run_worker(self._start_research(), exclusive=True)
        elif button_id == "stop-run":
            self.status = "IDLE"
            self.query_one("#status-display", Static).update(f"Status: {self.status}")
            self.log_message("Run stopped", "warning")

        # Actions controls
        elif button_id == "action-design":
            self.log_message("Design requires a selected failure and LLM support.", "warning")
        elif button_id == "action-simulate":
            self.log_message("Simulation requires a selected intervention.", "warning")
        elif button_id == "action-deploy":
            self.log_message("Deploy requires production approvals.", "warning")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submissions."""
        if event.input.id == "chat-input":
            self.run_worker(self._handle_chat(event.value), exclusive=True)
            event.input.value = ""

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        if table_id == "actions-failures-table":
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
        self.log_message("Research cycle complete", "success")

        self.status = "IDLE"
        self.query_one("#status-display", Static).update(f"Status: {self.status}")
        self._run_inflight = False

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
            f"Hypotheses: {len(hypotheses)} | "
            f"Experiments: {len(results.get('experiments', []))} | "
            f"Failures: {len(failures)} | "
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
