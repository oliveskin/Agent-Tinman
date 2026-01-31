"""
Tinman: Forward-Deployed Research Agent

An autonomous AI researcher that discovers and addresses failure modes
in AI systems through systematic experimentation and LLM-powered reasoning.

https://github.com/oliveskin/agent_tinman
"""

__version__ = "0.1.59"
__author__ = "Tinman Contributors"
__license__ = "Apache-2.0"

# Main interface
from .tinman import Tinman, create_tinman, TinmanState

# Config
from .config.modes import OperatingMode
from .config.settings import Settings, load_settings

# Memory
from .memory.models import Node, Edge, NodeType, EdgeRelation
from .memory.graph import MemoryGraph

# Agents
from .agents.base import BaseAgent, AgentContext, AgentResult
from .agents.hypothesis_engine import HypothesisEngine, Hypothesis
from .agents.experiment_architect import ExperimentArchitect
from .agents.experiment_executor import ExperimentExecutor
from .agents.failure_discovery import FailureDiscoveryAgent, DiscoveredFailure
from .agents.intervention_engine import InterventionEngine
from .agents.simulation_engine import SimulationEngine

# Reasoning (the brain)
from .reasoning.llm_backbone import LLMBackbone, ReasoningContext, ReasoningMode
from .reasoning.adaptive_memory import AdaptiveMemory
from .reasoning.insight_synthesizer import InsightSynthesizer

# Taxonomy
from .taxonomy.failure_types import FailureClass, Severity
from .taxonomy.classifiers import FailureClassifier

# Integrations
from .integrations.model_client import ModelClient, ModelResponse
from .integrations.openai_client import OpenAIClient
from .integrations.anthropic_client import AnthropicClient
from .integrations.openrouter_client import OpenRouterClient
from .integrations.google_client import GoogleClient
from .integrations.groq_client import GroqClient
from .integrations.ollama_client import OllamaClient
from .integrations.together_client import TogetherClient
from .integrations.pipeline_adapter import PipelineAdapter

# Reporting
from .reporting.lab_reporter import LabReporter, LabReport
from .reporting.ops_reporter import OpsReporter, OpsReport

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
    "GoogleClient",      # Gemini models
    "GroqClient",        # Fast inference, free tier
    "OllamaClient",      # Local models, free
    "TogetherClient",    # Open models, free credits
    "PipelineAdapter",
    # Reporting
    "LabReporter",
    "LabReport",
    "OpsReporter",
    "OpsReport",
]
