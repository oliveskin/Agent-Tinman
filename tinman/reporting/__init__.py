"""Reporting - comprehensive reports for partners and stakeholders.

This module provides various report generators:
- Lab reports: Detailed research findings
- Ops reports: Operational health and monitoring
- Executive reports: High-level summaries for leadership
- Technical reports: Engineering-focused analysis
- Compliance reports: Audit and regulatory documentation
"""

from .base import (
    Report,
    ReportFormat,
    ReportGenerator,
    ReportMetadata,
    ReportSection,
    ReportType,
)
from .compliance import ComplianceReport
from .executive import ExecutiveSummaryReport
from .export import (
    export_all_formats,
    export_report,
    export_to_csv,
    export_to_html,
    export_to_json,
    export_to_markdown,
    export_to_pdf,
)
from .lab_reporter import LabReport, LabReporter
from .ops_reporter import OpsReport, OpsReporter
from .technical import TechnicalAnalysisReport

__all__ = [
    # Base types
    "Report",
    "ReportSection",
    "ReportFormat",
    "ReportType",
    "ReportMetadata",
    "ReportGenerator",
    # Lab reporting
    "LabReporter",
    "LabReport",
    # Ops reporting
    "OpsReporter",
    "OpsReport",
    # Partner-facing reports
    "ExecutiveSummaryReport",
    "TechnicalAnalysisReport",
    "ComplianceReport",
    # Export functions
    "export_report",
    "export_to_json",
    "export_to_markdown",
    "export_to_html",
    "export_to_pdf",
    "export_to_csv",
    "export_all_formats",
]
