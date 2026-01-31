"""Token counting utilities for LLM API calls."""


import structlog

logger = structlog.get_logger(__name__)

# Model-specific characters-per-token ratios (approximate)
# These are rough estimates when tiktoken is not available
MODEL_CHAR_RATIOS: dict[str, float] = {
    # OpenAI models
    "gpt-4": 4.0,
    "gpt-4-turbo": 4.0,
    "gpt-4o": 4.0,
    "gpt-3.5-turbo": 4.0,
    # Anthropic models (tend to be slightly different)
    "claude-3": 3.5,
    "claude-2": 3.5,
    # Google models
    "gemini": 4.0,
    # Open source models (generally similar to GPT)
    "llama": 4.0,
    "mistral": 4.0,
    "mixtral": 4.0,
    # Default fallback
    "default": 4.0,
}


def estimate_tokens(text: str, model: str | None = None) -> int:
    """Estimate token count for text.

    Uses model-specific character ratios for estimation.
    This is approximate but better than the crude chars/4 heuristic.

    Args:
        text: The text to estimate tokens for
        model: Optional model name for model-specific ratios

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    # Find the best matching ratio
    ratio = MODEL_CHAR_RATIOS["default"]
    if model:
        model_lower = model.lower()
        for model_prefix, model_ratio in MODEL_CHAR_RATIOS.items():
            if model_prefix in model_lower:
                ratio = model_ratio
                break

    # Account for whitespace and punctuation (they often tokenize separately)
    char_count = len(text)
    whitespace_count = sum(1 for c in text if c.isspace())
    punctuation_count = sum(1 for c in text if not c.isalnum() and not c.isspace())

    # Adjust: whitespace and punctuation often become separate tokens
    adjusted_chars = char_count + (whitespace_count * 0.5) + (punctuation_count * 0.5)

    return max(1, int(adjusted_chars / ratio))


def estimate_messages_tokens(
    messages: list[dict],
    model: str | None = None,
) -> int:
    """Estimate tokens for a list of chat messages.

    Accounts for message formatting overhead.

    Args:
        messages: List of message dicts with 'role' and 'content'
        model: Optional model name

    Returns:
        Estimated total tokens
    """
    total = 0

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content, model)
        elif isinstance(content, list):
            # Handle multi-part content (e.g., with images)
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += estimate_tokens(part["text"], model)

        # Add overhead for role and message structure
        # Each message has ~4 tokens of overhead
        total += 4

    # Add ~3 tokens for the assistant's reply priming
    total += 3

    return total


def count_tokens_tiktoken(
    text: str,
    model: str = "gpt-4",
) -> int | None:
    """Count tokens using tiktoken if available.

    Args:
        text: Text to count tokens for
        model: Model name for encoding selection

    Returns:
        Token count, or None if tiktoken not available
    """
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fall back to cl100k_base for unknown models
            encoding = tiktoken.get_encoding("cl100k_base")

        return len(encoding.encode(text))
    except ImportError:
        logger.debug("tiktoken not installed, using estimation")
        return None


def count_tokens(
    text: str,
    model: str | None = None,
    use_tiktoken: bool = True,
) -> int:
    """Count tokens, using tiktoken if available, else estimate.

    Args:
        text: Text to count tokens for
        model: Optional model name
        use_tiktoken: Whether to try tiktoken first

    Returns:
        Token count (exact if tiktoken available, estimated otherwise)
    """
    if use_tiktoken and model:
        exact_count = count_tokens_tiktoken(text, model)
        if exact_count is not None:
            return exact_count

    return estimate_tokens(text, model)
