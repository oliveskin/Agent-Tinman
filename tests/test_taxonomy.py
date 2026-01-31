"""Tests for failure taxonomy."""

import pytest
from tinman.taxonomy.failure_types import (
    FailureClass,
    Severity,
    FAILURE_TAXONOMY,
)
from tinman.taxonomy.classifiers import FailureClassifier


def test_failure_taxonomy_complete():
    """Test that taxonomy covers all failure classes."""
    for fc in FailureClass:
        assert fc in FAILURE_TAXONOMY
        info = FAILURE_TAXONOMY[fc]
        assert info.description
        assert info.typical_triggers
        assert isinstance(info.base_severity, Severity)


def test_classifier_basic_classification():
    """Test basic failure classification."""
    classifier = FailureClassifier()

    result = classifier.classify(description="Model failed to use the search tool correctly")

    assert result.primary_class == FailureClass.TOOL_USE
    assert result.confidence > 0


def test_classifier_with_context():
    """Test classification with additional context."""
    classifier = FailureClassifier()

    result = classifier.classify(
        description="Response was truncated",
        context={"context_length": 150000},
    )

    # High context length should influence classification
    assert result.primary_class in [FailureClass.LONG_CONTEXT, FailureClass.REASONING]


def test_classifier_reasoning_patterns():
    """Test that reasoning patterns are detected."""
    classifier = FailureClassifier()

    result = classifier.classify(description="Model provided inconsistent logical conclusions")

    assert result.primary_class == FailureClass.REASONING


def test_severity_ordering():
    """Test severity level ordering."""
    assert Severity.S0.value < Severity.S1.value
    assert Severity.S1.value < Severity.S2.value
    assert Severity.S2.value < Severity.S3.value
    assert Severity.S3.value < Severity.S4.value
