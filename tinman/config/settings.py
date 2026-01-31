"""Configuration management for Tinman FDRA."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .modes import Mode


@dataclass
class DatabaseSettings:
    url: str = "postgresql://localhost:5432/tinman"
    pool_size: int = 10


@dataclass
class ModelProviderSettings:
    api_key: str = ""
    model: str = ""
    base_url: str | None = None


@dataclass
class ModelsSettings:
    default: str = "openai"
    providers: dict[str, ModelProviderSettings] = field(default_factory=dict)


@dataclass
class PipelineSettings:
    adapter: str = "generic"
    endpoint: str = "http://localhost:8000/v1/complete"


@dataclass
class RiskSettings:
    detailed_mode: bool = False
    auto_approve_safe: bool = True
    block_on_destructive: bool = True


@dataclass
class ExperimentSettings:
    max_parallel: int = 5
    default_timeout_seconds: int = 300
    cost_limit_usd: float = 10.0


@dataclass
class ShadowSettings:
    traffic_sample_rate: float = 0.1
    replay_buffer_days: int = 7


@dataclass
class ReportingSettings:
    lab_output_dir: str = "./reports/lab"
    ops_output_dir: str = "./reports/ops"


@dataclass
class LoggingSettings:
    level: str = "INFO"
    format: str = "json"


@dataclass
class Settings:
    """Main configuration container for Tinman FDRA."""

    mode: Mode = Mode.LAB
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    models: ModelsSettings = field(default_factory=ModelsSettings)
    pipeline: PipelineSettings = field(default_factory=PipelineSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    experiments: ExperimentSettings = field(default_factory=ExperimentSettings)
    shadow: ShadowSettings = field(default_factory=ShadowSettings)
    reporting: ReportingSettings = field(default_factory=ReportingSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)

    # Convenience accessors
    @property
    def database_url(self) -> str:
        return self.database.url

    @property
    def model_temperature(self) -> float | None:
        return 0.7  # Default temperature

    @property
    def model_provider(self) -> str:
        return self.models.default

    @property
    def max_hypotheses_per_run(self) -> int:
        return 10

    @property
    def max_experiments_per_hypothesis(self) -> int:
        return 3

    @property
    def default_runs_per_experiment(self) -> int:
        return 5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """Create Settings from dictionary."""
        mode = Mode(data.get("mode", "lab"))

        db_data = data.get("database", {})
        database = DatabaseSettings(
            url=db_data.get("url", "postgresql://localhost:5432/tinman"),
            pool_size=db_data.get("pool_size", 10),
        )

        models_data = data.get("models", {})
        providers = {}
        for name, pdata in models_data.get("providers", {}).items():
            api_key = pdata.get("api_key", "")
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                api_key = os.environ.get(env_var, "")
            providers[name] = ModelProviderSettings(
                api_key=api_key,
                model=pdata.get("model", ""),
                base_url=pdata.get("base_url"),
            )
        models = ModelsSettings(
            default=models_data.get("default", "openai"),
            providers=providers,
        )

        pipeline_data = data.get("pipeline", {})
        pipeline = PipelineSettings(
            adapter=pipeline_data.get("adapter", "generic"),
            endpoint=pipeline_data.get("endpoint", "http://localhost:8000/v1/complete"),
        )

        risk_data = data.get("risk", {})
        risk = RiskSettings(
            detailed_mode=risk_data.get("detailed_mode", False),
            auto_approve_safe=risk_data.get("auto_approve_safe", True),
            block_on_destructive=risk_data.get("block_on_destructive", True),
        )

        exp_data = data.get("experiments", {})
        experiments = ExperimentSettings(
            max_parallel=exp_data.get("max_parallel", 5),
            default_timeout_seconds=exp_data.get("default_timeout_seconds", 300),
            cost_limit_usd=exp_data.get("cost_limit_usd", 10.0),
        )

        shadow_data = data.get("shadow", {})
        shadow = ShadowSettings(
            traffic_sample_rate=shadow_data.get("traffic_sample_rate", 0.1),
            replay_buffer_days=shadow_data.get("replay_buffer_days", 7),
        )

        report_data = data.get("reporting", {})
        reporting = ReportingSettings(
            lab_output_dir=report_data.get("lab_output_dir", "./reports/lab"),
            ops_output_dir=report_data.get("ops_output_dir", "./reports/ops"),
        )

        log_data = data.get("logging", {})
        logging_settings = LoggingSettings(
            level=log_data.get("level", "INFO"),
            format=log_data.get("format", "json"),
        )

        return cls(
            mode=mode,
            database=database,
            models=models,
            pipeline=pipeline,
            risk=risk,
            experiments=experiments,
            shadow=shadow,
            reporting=reporting,
            logging=logging_settings,
        )


def load_config(path: Path | None = None) -> Settings:
    """Load configuration from YAML file or defaults."""
    if path is None:
        default_path = Path(".tinman") / "config.yaml"
        if default_path.exists():
            path = default_path
        else:
            path = Path("tinman.yaml")

    # Load environment variables from .env if present
    candidates = [Path(".env"), Path(".env.local")]
    if path is not None:
        candidates.append(path.parent / ".env")
        candidates.append(path.parent / ".env.local")
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate, override=False)

    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f)
        return Settings.from_dict(data or {})

    return Settings()


# Alias for backwards compatibility
load_settings = load_config
