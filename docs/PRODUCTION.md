# Production Deployment Guide

This document covers deploying Tinman in a production environment with full safety controls, observability, and operational tooling.

## Prerequisites

- Python 3.10+
- PostgreSQL 13+ (for persistence)
- Docker (optional, for containerized deployment)

## Quick Production Setup

```bash
# Install with all dependencies
pip install AgentTinman[all]

# Set required environment variables
export ANTHROPIC_API_KEY=your-key
export TINMAN_DATABASE_URL=postgresql://user:pass@localhost/tinman
export TINMAN_MODE=shadow

# Initialize database
alembic upgrade head

# Start service
tinman serve --host 0.0.0.0 --port 8000
```

## Database Setup

### Alembic Migrations

Tinman uses Alembic for database migrations:

```bash
# Run all migrations
alembic upgrade head

# Check current version
alembic current

# Generate new migration
alembic revision --autogenerate -m "description"

# Rollback one version
alembic downgrade -1
```

### Required Tables

The initial migration creates:

- `hypotheses` - Generated research hypotheses
- `experiments` - Experiment definitions and results
- `failures` - Discovered failure modes
- `interventions` - Proposed interventions
- `simulations` - Simulation results
- `memory_nodes` - Knowledge graph nodes
- `memory_edges` - Knowledge graph relationships
- `audit_logs` - Immutable audit trail
- `approval_decisions` - Human approval records
- `mode_transitions` - Mode change history
- `tool_executions` - Tool call records

## Service Mode

### FastAPI Endpoints

Start the HTTP service:

```bash
tinman serve --host 0.0.0.0 --port 8000
```

**Available endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with component status |
| `/ready` | GET | Kubernetes readiness probe |
| `/live` | GET | Kubernetes liveness probe |
| `/status` | GET | Current Tinman state |
| `/research/cycle` | POST | Run a research cycle |
| `/approvals/pending` | GET | List pending approvals |
| `/approvals/{id}/decide` | POST | Decide on approval |
| `/discuss` | POST | Interactive discussion |
| `/report` | GET | Generate report |
| `/mode` | GET | Current mode |
| `/mode/transition` | POST | Transition modes |
| `/metrics` | GET | Prometheus metrics |

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .[all]

ENV TINMAN_MODE=shadow
EXPOSE 8000

CMD ["uvicorn", "tinman.service.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  tinman:
    build: .
    ports:
      - "8000:8000"
      - "9090:9090"  # Prometheus metrics
    environment:
      - TINMAN_MODE=shadow
      - TINMAN_DATABASE_URL=postgresql://postgres:postgres@db/tinman
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=tinman
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tinman
spec:
  replicas: 1
  selector:
    matchLabels:
      app: tinman
  template:
    metadata:
      labels:
        app: tinman
    spec:
      containers:
        - name: tinman
          image: tinman:latest
          ports:
            - containerPort: 8000
            - containerPort: 9090
          env:
            - name: TINMAN_MODE
              value: "shadow"
            - name: TINMAN_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: tinman-secrets
                  key: database-url
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 10
          livenessProbe:
            httpGet:
              path: /live
              port: 8000
            initialDelaySeconds: 30
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
```

## Cost Controls

### Budget Configuration

```python
from tinman.core.cost_tracker import CostTracker, BudgetConfig, BudgetPeriod

# Configure budget
config = BudgetConfig(
    limit_usd=100.0,           # Max spend
    period=BudgetPeriod.DAILY,  # Reset daily
    warn_threshold=0.8,         # Warn at 80%
    hard_limit=True,            # Block when exceeded
)

tracker = CostTracker(budget_config=config)
```

### Budget Enforcement

```python
from tinman.core.cost_tracker import BudgetExceededError

try:
    # Check before operation
    tracker.enforce_budget(estimated_cost=5.0)

    # Perform operation
    result = await expensive_operation()

    # Record actual cost
    tracker.record_cost(
        amount_usd=4.50,
        source="llm_call",
        model="claude-3-opus",
        operation="research",
    )
except BudgetExceededError as e:
    print(f"Budget exceeded: ${e.current:.2f} / ${e.limit:.2f}")
```

### Cost Monitoring

```python
# Get cost summary
summary = tracker.get_summary()
print(f"Current period: ${summary['current_period_cost_usd']:.2f}")
print(f"Remaining: ${summary['remaining_budget_usd']:.2f}")
print(f"By model: {summary['by_model']}")
```

## Observability

### Prometheus Metrics

Start the metrics server:

```python
from tinman.core.metrics import start_metrics_server

start_metrics_server(port=9090)
```

**Key metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `tinman_research_cycles_total` | Counter | Total research cycles |
| `tinman_failures_discovered_total` | Counter | Failures by severity/class |
| `tinman_approval_decisions_total` | Counter | Approvals by decision/tier |
| `tinman_cost_usd_total` | Counter | Costs by source/model |
| `tinman_llm_requests_total` | Counter | LLM requests by model/status |
| `tinman_llm_latency_seconds` | Histogram | LLM request latency |
| `tinman_tool_executions_total` | Counter | Tool calls by status |
| `tinman_pending_approvals` | Gauge | Current pending approvals |
| `tinman_current_mode` | Gauge | Active operating mode |

### Grafana Dashboard

Example dashboard JSON available at `examples/grafana-dashboard.json`.

### Structured Logging

```python
from tinman.utils import get_logger

logger = get_logger("my_component")
logger.info("Operation completed", extra={
    "operation": "research_cycle",
    "duration_ms": 1500,
    "failures_found": 3,
})
```

## Security

### Audit Trail

All consequential actions are logged:

```python
from tinman.db.audit import AuditLogger

audit = AuditLogger(session)

# Query recent activity
logs = audit.query(
    event_types=["approval_decision", "mode_transition"],
    since=datetime.now() - timedelta(hours=24),
)
```

### Risk Policy

Configure risk evaluation via YAML:

```yaml
# risk_policy.yaml
base_matrix:
  lab:
    S0: safe
    S1: safe
    S2: review
    S3: review
    S4: block
  shadow:
    S0: safe
    S1: review
    S2: review
    S3: block
    S4: block
  production:
    S0: review
    S1: review
    S2: block
    S3: block
    S4: block

action_overrides:
  DEPLOY_INTERVENTION:
    production: block
  DESTRUCTIVE_TEST:
    shadow: block
    production: block

cost_thresholds:
  low_cost_max: 1.0
  high_cost_min: 10.0
```

### Guarded Tool Execution

All tool calls go through the safety pipeline:

```python
from tinman.core.tools import guarded_call, ToolRegistry

@ToolRegistry.register(
    name="search",
    risk_level=ToolRiskLevel.LOW,
)
async def search_tool(query: str) -> list[str]:
    return await do_search(query)

# Execution is automatically guarded
result = await guarded_call(
    search_tool,
    action_type=ActionType.TOOL_CALL,
    description="Search for relevant documents",
    approval_handler=handler,
    mode=Mode.PRODUCTION,
    query="AI safety",
)
```

## Trace Ingestion

### Supported Formats

- OpenTelemetry (OTLP)
- Datadog APM
- AWS X-Ray
- Generic JSON

### Example: OTLP Integration

```python
from tinman.ingest import OTLPAdapter, parse_traces

# From OTLP collector
adapter = OTLPAdapter()
traces = list(adapter.parse(otlp_data))

# Analyze for failures
for trace in traces:
    for span in trace.error_spans:
        print(f"Error: {span.name} - {span.status_message}")
```

### Auto-Detection

```python
from tinman.ingest import parse_traces

# Automatically detects format
traces = parse_traces(unknown_data)
```

## Reporting

### Generate Reports

```python
from tinman.reporting import (
    ExecutiveSummaryReport,
    TechnicalAnalysisReport,
    ComplianceReport,
    export_report,
    ReportFormat,
)

# Executive summary
exec_gen = ExecutiveSummaryReport(graph=tinman.graph)
exec_report = await exec_gen.generate(
    period_start=week_ago,
    period_end=now,
)

# Export
export_report(exec_report, "report.html", ReportFormat.HTML)
```

### Report Types

| Type | Audience | Content |
|------|----------|---------|
| Executive | Leadership | KPIs, trends, risk score |
| Technical | Engineering | Failure details, triggers, patterns |
| Compliance | Audit | Approvals, transitions, violations |

## Operational Runbook

### Health Check

```bash
curl http://localhost:8000/health
```

Expected response when healthy:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "mode": "shadow",
  "database_connected": true,
  "llm_available": true,
  "uptime_seconds": 3600,
  "checks": {
    "tinman_initialized": true,
    "database_connected": true,
    "llm_available": true
  }
}
```

### Mode Transition

```bash
# Transition to production
curl -X POST http://localhost:8000/mode/transition \
  -H "Content-Type: application/json" \
  -d '{"target_mode": "production"}'
```

### Emergency Rollback

```bash
# Force return to shadow mode
export TINMAN_MODE=shadow
kill -HUP $(pidof tinman)
```

### Database Backup

```bash
pg_dump -h localhost -U tinman tinman > backup.sql
```

## Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check database connection
alembic current

# Verify environment
env | grep TINMAN
```

**High latency:**
```bash
# Check metrics
curl http://localhost:9090/metrics | grep latency
```

**Budget exceeded:**
```python
# Reset budget period
tracker.reset_period()
```

**Approval queue growing:**
```bash
# Check pending approvals
curl http://localhost:8000/approvals/pending
```

## Support

- GitHub Issues: https://github.com/tinman/tinman/issues
- Documentation: https://tinman.dev/docs
