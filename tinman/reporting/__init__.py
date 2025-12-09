"""Reporting - comprehensive reports for partners and stakeholders.

This module provides various report generators:
- Lab reports: Detailed research findings
- Ops reports: Operational health and monitoring
- Executive reports: High-level summaries for leadership
- Technical reports: Engineering-focused analysis
- Compliance reports: Audit and regulatory documentation
"""

from .lab_reporter import LabReporter, LabReport
from .ops_reporter import OpsReporter, OpsReport
from .base import (
    Report,
    ReportSection,
    ReportFormat,
    ReportType,
    ReportMetadata,
    ReportGenerator,
)
from .executive import ExecutiveSummaryReport
from .technical import TechnicalAnalysisReport
from .compliance import ComplianceReport
from .export import (
    export_report,
    export_to_json,
    export_to_markdown,
    export_to_html,
    export_to_pdf,
    export_to_csv,
    export_all_formats,
)

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
