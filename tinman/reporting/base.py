"""Base types and abstract classes for reporting.

This module defines the foundation for all Tinman reports,
providing common structures, formats, and generation patterns.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TypeVar, Generic

from ..utils import get_logger, utc_now, generate_id

logger = get_logger("reporting.base")


class ReportFormat(str, Enum):
    """Supported report output formats."""
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    CSV = "csv"


class ReportType(str, Enum):
    """Types of reports available."""
    EXECUTIVE_SUMMARY = "executive_summary"
    TECHNICAL_ANALYSIS = "technical_analysis"
    COMPLIANCE = "compliance"
    TREND = "trend"
    INCIDENT = "incident"
    LAB = "lab"
    OPS = "ops"


@dataclass
class ReportMetadata:
    """Metadata for a report."""
    id: str = field(default_factory=generate_id)
    type: ReportType = ReportType.EXECUTIVE_SUMMARY
    title: str = ""
    description: str = ""
    generated_at: datetime = field(default_factory=utc_now)
    generated_by: str = "tinman"
    version: str = "1.0"
    confidentiality: str = "internal"  # internal, confidential, public
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ReportSection:
    """A section within a report."""
    id: str = field(default_factory=generate_id)
    title: str = ""
    content: str = ""
    order: int = 0
    level: int = 1  # Heading level (1-6)
    subsections: list["ReportSection"] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    charts: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReportChart:
    """Chart data for visualization."""
    id: str = field(default_factory=generate_id)
    type: str = "bar"  # bar, line, pie, scatter
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    data: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportTable:
    """Table data for structured display."""
    id: str = field(default_factory=generate_id)
    title: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    footer: Optional[list[Any]] = None
    sortable: bool = True


T = TypeVar("T")


@dataclass
class Report(Generic[T]):
    """Base report class."""
    metadata: ReportMetadata = field(default_factory=ReportMetadata)
    sections: list[ReportSection] = field(default_factory=list)
    summary: str = ""
    raw_data: Optional[T] = None
    attachments: list[dict[str, Any]] = field(default_factory=list)


class ReportGenerator(ABC):
    """Abstract base class for report generators.

    Each generator is responsible for creating a specific type of report
    from Tinman data sources.
    """

    @property
    @abstractmethod
    def report_type(self) -> ReportType:
        """The type of report this generator creates."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this generator."""
        pass

    @abstractmethod
    async def generate(
        self,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        **kwargs,
    ) -> Report:
        """Generate a report.

        Args:
            period_start: Start of reporting period
            period_end: End of reporting period
            **kwargs: Additional generator-specific parameters

        Returns:
            Generated Report object
        """
        pass

    def format(self, report: Report, output_format: ReportFormat) -> str | bytes:
        """Format a report for output.

        Args:
            report: Report to format
            output_format: Desired output format

        Returns:
            Formatted report content
        """
        formatters = {
            ReportFormat.JSON: self._to_json,
            ReportFormat.MARKDOWN: self._to_markdown,
            ReportFormat.HTML: self._to_html,
            ReportFormat.CSV: self._to_csv,
        }

        formatter = formatters.get(output_format)
        if not formatter:
            raise ValueError(f"Unsupported format: {output_format}")

        return formatter(report)

    def _to_json(self, report: Report) -> str:
        """Convert report to JSON."""
        import json

        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, "__dict__"):
                return {k: serialize(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [serialize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            return obj

        data = {
            "metadata": serialize(report.metadata),
            "summary": report.summary,
            "sections": [serialize(s) for s in report.sections],
        }

        return json.dumps(data, indent=2)

    def _to_markdown(self, report: Report) -> str:
        """Convert report to Markdown."""
        lines = []

        # Title
        lines.append(f"# {report.metadata.title or 'Report'}")
        lines.append("")

        # Metadata
        lines.append(f"**Generated:** {report.metadata.generated_at.isoformat()}")
        lines.append(f"**Type:** {report.metadata.type.value}")
        if report.metadata.period_start and report.metadata.period_end:
            lines.append(
                f"**Period:** {report.metadata.period_start.isoformat()} to "
                f"{report.metadata.period_end.isoformat()}"
            )
        lines.append("")

        # Summary
        if report.summary:
            lines.append("## Executive Summary")
            lines.append("")
            lines.append(report.summary)
            lines.append("")

        # Sections
        for section in sorted(report.sections, key=lambda s: s.order):
            self._render_section_markdown(section, lines)

        return "\n".join(lines)

    def _render_section_markdown(
        self,
        section: ReportSection,
        lines: list[str],
    ) -> None:
        """Render a section to markdown lines."""
        # Heading
        heading = "#" * (section.level + 1)  # +1 because title is #
        lines.append(f"{heading} {section.title}")
        lines.append("")

        # Content
        if section.content:
            lines.append(section.content)
            lines.append("")

        # Tables
        for table in section.tables:
            self._render_table_markdown(table, lines)

        # Subsections
        for subsection in sorted(section.subsections, key=lambda s: s.order):
            self._render_section_markdown(subsection, lines)

    def _render_table_markdown(
        self,
        table: dict[str, Any],
        lines: list[str],
    ) -> None:
        """Render a table to markdown."""
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        if not headers:
            return

        # Title
        if table.get("title"):
            lines.append(f"**{table['title']}**")
            lines.append("")

        # Header row
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")

        # Data rows
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")

        lines.append("")

    def _to_html(self, report: Report) -> str:
        """Convert report to HTML."""
        sections_html = ""
        for section in sorted(report.sections, key=lambda s: s.order):
            sections_html += self._render_section_html(section)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report.metadata.title or 'Report'}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        h3 {{ color: #7f8c8d; }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .metadata {{
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .summary {{
            background-color: #e8f6f3;
            padding: 20px;
            border-left: 4px solid #1abc9c;
            margin: 20px 0;
        }}
        .alert-critical {{ background-color: #fadbd8; border-left: 4px solid #e74c3c; }}
        .alert-warning {{ background-color: #fef9e7; border-left: 4px solid #f39c12; }}
        .alert-info {{ background-color: #ebf5fb; border-left: 4px solid #3498db; }}
    </style>
</head>
<body>
    <h1>{report.metadata.title or 'Report'}</h1>

    <div class="metadata">
        <strong>Generated:</strong> {report.metadata.generated_at.isoformat()}<br>
        <strong>Type:</strong> {report.metadata.type.value}<br>
        <strong>Confidentiality:</strong> {report.metadata.confidentiality}
    </div>

    {f'<div class="summary"><h2>Executive Summary</h2><p>{report.summary}</p></div>' if report.summary else ''}

    {sections_html}

    <footer style="margin-top: 40px; color: #7f8c8d; font-size: 0.9em;">
        Generated by Tinman FDRA v{report.metadata.version}
    </footer>
</body>
</html>"""

    def _render_section_html(self, section: ReportSection) -> str:
        """Render a section to HTML."""
        level = min(section.level + 1, 6)
        tables_html = ""

        for table in section.tables:
            tables_html += self._render_table_html(table)

        subsections_html = ""
        for subsection in sorted(section.subsections, key=lambda s: s.order):
            subsections_html += self._render_section_html(subsection)

        return f"""
    <h{level}>{section.title}</h{level}>
    {f'<p>{section.content}</p>' if section.content else ''}
    {tables_html}
    {subsections_html}
"""

    def _render_table_html(self, table: dict[str, Any]) -> str:
        """Render a table to HTML."""
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        if not headers:
            return ""

        headers_html = "".join(f"<th>{h}</th>" for h in headers)
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
            for row in rows
        )

        return f"""
    <table>
        {f'<caption>{table["title"]}</caption>' if table.get("title") else ''}
        <thead><tr>{headers_html}</tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
"""

    def _to_csv(self, report: Report) -> str:
        """Convert report to CSV (first table only)."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Find first table
        for section in report.sections:
            for table in section.tables:
                headers = table.get("headers", [])
                rows = table.get("rows", [])

                if headers:
                    writer.writerow(headers)
                    for row in rows:
                        writer.writerow(row)
                    return output.getvalue()

        return ""
