"""Alert dispatching for gateway monitor findings.

This module provides alerters that dispatch findings to various
destinations: console, files, webhooks, channels, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ...utils import get_logger, utc_now

logger = get_logger("gateway_alerter")


@dataclass
class Finding:
    """A security or failure finding from trace analysis."""

    finding_id: str
    trace_id: str
    severity: str  # S0-S4
    category: str  # prompt_injection, tool_exfil, etc.
    title: str
    description: str
    evidence: list[str] = field(default_factory=list)
    mitigation: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def severity_int(self) -> int:
        """Convert severity to integer (0-4)."""
        try:
            return int(self.severity[1]) if self.severity.startswith("S") else 0
        except (ValueError, IndexError):
            return 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "finding_id": self.finding_id,
            "trace_id": self.trace_id,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "mitigation": self.mitigation,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [
            f"### [{self.severity}] {self.title}",
            f"**Category:** {self.category}",
            f"**Trace:** {self.trace_id}",
            f"**Time:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            self.description,
        ]

        if self.evidence:
            lines.extend(["", "**Evidence:**"])
            for ev in self.evidence:
                lines.append(f"- `{ev}`")

        if self.mitigation:
            lines.extend(["", f"**Mitigation:** {self.mitigation}"])

        return "\n".join(lines)


class Alerter(ABC):
    """Abstract base class for alert dispatchers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Alerter name for identification."""
        pass

    @abstractmethod
    async def send(self, findings: list[Finding]) -> bool:
        """Send findings to the alert destination.

        Args:
            findings: List of findings to send

        Returns:
            True if all findings were sent successfully
        """
        pass

    def filter_findings(
        self,
        findings: list[Finding],
        min_severity: str = "S0",
        categories: list[str] | None = None,
    ) -> list[Finding]:
        """Filter findings by severity and category.

        Args:
            findings: Findings to filter
            min_severity: Minimum severity level (S0-S4)
            categories: Categories to include (None = all)

        Returns:
            Filtered findings
        """
        min_sev = int(min_severity[1]) if min_severity.startswith("S") else 0

        result = []
        for f in findings:
            if f.severity_int < min_sev:
                continue
            if categories and f.category not in categories:
                continue
            result.append(f)

        return result


class ConsoleAlerter(Alerter):
    """Print findings to console."""

    @property
    def name(self) -> str:
        return "console"

    async def send(self, findings: list[Finding]) -> bool:
        """Print findings to console."""
        for finding in findings:
            severity_colors = {
                "S4": "\033[91m",  # Red
                "S3": "\033[93m",  # Yellow
                "S2": "\033[94m",  # Blue
                "S1": "\033[90m",  # Gray
                "S0": "\033[90m",  # Gray
            }
            reset = "\033[0m"
            color = severity_colors.get(finding.severity, "")

            print(f"{color}[{finding.severity}]{reset} {finding.title}")
            print(f"  Category: {finding.category}")
            print(f"  {finding.description}")
            if finding.mitigation:
                print(f"  Mitigation: {finding.mitigation}")
            print()

        return True


class FileAlerter(Alerter):
    """Write findings to a markdown file."""

    def __init__(self, output_path: str | Path, append: bool = True):
        """Initialize file alerter.

        Args:
            output_path: Path to output file
            append: Whether to append or overwrite
        """
        self.output_path = Path(output_path)
        self.append = append

    @property
    def name(self) -> str:
        return "file"

    async def send(self, findings: list[Finding]) -> bool:
        """Write findings to file."""
        try:
            # Ensure parent directory exists
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if self.append else "w"
            with open(self.output_path, mode, encoding="utf-8") as f:
                if not self.append or not self.output_path.exists():
                    f.write(f"# Gateway Monitor Findings\n\n")
                    f.write(f"Generated: {utc_now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                for finding in findings:
                    f.write(finding.to_markdown())
                    f.write("\n\n---\n\n")

            logger.info(f"Wrote {len(findings)} findings to {self.output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to write findings: {e}")
            return False


class CallbackAlerter(Alerter):
    """Call a custom callback with findings."""

    def __init__(self, callback: Any, alerter_name: str = "callback"):
        """Initialize callback alerter.

        Args:
            callback: Async function to call with findings
            alerter_name: Name for this alerter
        """
        self.callback = callback
        self._name = alerter_name

    @property
    def name(self) -> str:
        return self._name

    async def send(self, findings: list[Finding]) -> bool:
        """Call the callback with findings."""
        try:
            result = self.callback(findings)
            # Handle async callbacks
            if hasattr(result, "__await__"):
                await result
            return True
        except Exception as e:
            logger.error(f"Callback alerter error: {e}")
            return False


class WebhookAlerter(Alerter):
    """Send findings to a webhook URL."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        min_severity: str = "S2",
    ):
        """Initialize webhook alerter.

        Args:
            url: Webhook URL
            headers: Optional HTTP headers
            min_severity: Minimum severity to send
        """
        self.url = url
        self.headers = headers or {}
        self.min_severity = min_severity

    @property
    def name(self) -> str:
        return "webhook"

    async def send(self, findings: list[Finding]) -> bool:
        """Send findings to webhook."""
        filtered = self.filter_findings(findings, min_severity=self.min_severity)
        if not filtered:
            return True

        try:
            import httpx

            payload = {
                "findings": [f.to_dict() for f in filtered],
                "count": len(filtered),
                "timestamp": utc_now().isoformat(),
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    json=payload,
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()

            logger.info(f"Sent {len(filtered)} findings to webhook")
            return True

        except ImportError:
            logger.error("httpx required for webhook alerter: pip install httpx")
            return False
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False


class AlertDispatcher:
    """Manages multiple alerters and dispatches findings."""

    def __init__(self):
        self._alerters: list[Alerter] = []

    def add_alerter(self, alerter: Alerter) -> None:
        """Add an alerter."""
        self._alerters.append(alerter)
        logger.debug(f"Added alerter: {alerter.name}")

    def remove_alerter(self, name: str) -> bool:
        """Remove an alerter by name."""
        for i, alerter in enumerate(self._alerters):
            if alerter.name == name:
                self._alerters.pop(i)
                return True
        return False

    async def dispatch(self, findings: list[Finding]) -> dict[str, bool]:
        """Dispatch findings to all alerters.

        Args:
            findings: Findings to dispatch

        Returns:
            Dict mapping alerter names to success status
        """
        if not findings:
            return {}

        results: dict[str, bool] = {}
        for alerter in self._alerters:
            try:
                results[alerter.name] = await alerter.send(findings)
            except Exception as e:
                logger.error(f"Alerter {alerter.name} failed: {e}")
                results[alerter.name] = False

        return results

    @property
    def alerter_names(self) -> list[str]:
        """Get names of all registered alerters."""
        return [a.name for a in self._alerters]
