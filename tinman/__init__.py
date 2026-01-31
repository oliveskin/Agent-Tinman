"""
Tinman: Forward-Deployed Research Agent

An autonomous AI researcher that discovers and addresses failure modes
in AI systems through systematic experimentation and LLM-powered reasoning.

https://github.com/oliveskin/agent_tinman
"""

__version__ = "0.1.60"
__author__ = "Tinman Contributors"
__license__ = "Apache-2.0"

# Main interface
# Agents
from .agents.base import AgentContext, AgentResult, BaseAgent
from .agents.experiment_architect import ExperimentArchitect
from .agents.experiment_executor import ExperimentExecutor
from .agents.failure_discovery import DiscoveredFailure, FailureDiscoveryAgent
from .agents.hypothesis_engine import Hypothesis, HypothesisEngine
from .agents.intervention_engine import InterventionEngine
from .agents.simulation_engine import SimulationEngine

# Config
from .config.modes import OperatingMode
from .config.settings import Settings, load_settings
from .integrations.anthropic_client import AnthropicClient
from .integrations.google_client import GoogleClient
from .integrations.groq_client import GroqClient

# Integrations
from .integrations.model_client import ModelClient, ModelResponse
from .integrations.ollama_client import OllamaClient
from .integrations.openai_client import OpenAIClient
from .integrations.openrouter_client import OpenRouterClient
from .integrations.pipeline_adapter import PipelineAdapter
from .integrations.together_client import TogetherClient
from .memory.graph import MemoryGraph

# Memory
from .memory.models import Edge, EdgeRelation, Node, NodeType
from .reasoning.adaptive_memory import AdaptiveMemory
from .reasoning.insight_synthesizer import InsightSynthesizer

# Reasoning (the brain)
from .reasoning.llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode

# Reporting
from .reporting.lab_reporter import LabReport, LabReporter
from .reporting.ops_reporter import OpsReport, OpsReporter
from .taxonomy.classifiers import FailureClassifier

# Taxonomy
from .taxonomy.failure_types import FailureClass, Severity
from .tinman import Tinman, TinmanState, create_tinman

__all__ = [
    # Version
    "__version__",
    # Main interface
    "Tinman",
    "create_tinman",
    "TinmanState",
    # Config
    "OperatingMode",
    "Settings",
    "load_settings",
    # Memory
    "Node",
    "Edge",
    "NodeType",
    "EdgeRelation",
    "MemoryGraph",
    # Agents
    "BaseAgent",
    "AgentContext",
    "AgentResult",
    "HypothesisEngine",
    "Hypothesis",
    "ExperimentArchitect",
    "ExperimentExecutor",
    "FailureDiscoveryAgent",
    "DiscoveredFailure",
    "InterventionEngine",
    "SimulationEngine",
    # Reasoning
    "LLMBackbone",
    "ReasoningContext",
    "ReasoningMode",
    "AdaptiveMemory",
    "InsightSynthesizer",
    # Taxonomy
    "FailureClass",
    "Severity",
    "FailureClassifier",
    # Integrations - Proprietary
    "ModelClient",
    "ModelResponse",
    "OpenAIClient",
    "AnthropicClient",
    # Integrations - Open Models
    "OpenRouterClient",  # DeepSeek, Qwen, Llama, Mistral
    "GoogleClient",  # Gemini models
    "GroqClient",  # Fast inference, free tier
    "OllamaClient",  # Local models, free
    "TogetherClient",  # Open models, free credits
    "PipelineAdapter",
    # Reporting
    "LabReporter",
    "LabReport",
    "OpsReporter",
    "OpsReport",
]
