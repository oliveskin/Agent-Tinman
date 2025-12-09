"""Tests for configuration."""

import pytest
from tinman.config.modes import OperatingMode, ModeCapabilities, get_capabilities
from tinman.config.settings import Settings


def test_operating_modes():
    """Test all operating modes exist."""
    assert OperatingMode.LAB
    assert OperatingMode.SHADOW
    assert OperatingMode.PRODUCTION


def test_mode_capabilities():
    """Test mode capabilities differ appropriately."""
    lab = get_capabilities(OperatingMode.LAB)
    shadow = get_capabilities(OperatingMode.SHADOW)
    prod = get_capabilities(OperatingMode.PRODUCTION)

    # LAB has most capabilities
    assert lab.can_generate_hypotheses
    assert lab.can_run_experiments
    assert lab.can_execute_interventions
    assert not lab.requires_approval_for_interventions

    # SHADOW is observe-only
    assert shadow.can_generate_hypotheses
    assert not shadow.can_execute_interventions

    # PRODUCTION requires approval
    assert prod.requires_approval_for_interventions


def test_mode_transitions():
    """Test valid mode transitions."""
    from tinman.config.modes import can_transition, VALID_TRANSITIONS

    # LAB -> SHADOW allowed
    assert can_transition(OperatingMode.LAB, OperatingMode.SHADOW)

    # SHADOW -> PRODUCTION allowed
    assert can_transition(OperatingMode.SHADOW, OperatingMode.PRODUCTION)

    # PRODUCTION -> LAB not allowed (skip)
    assert not can_transition(OperatingMode.PRODUCTION, OperatingMode.LAB)


def test_settings_defaults():
    """Test settings have sensible defaults."""
    settings = Settings()

    assert settings.mode == OperatingMode.LAB
    assert settings.max_hypotheses_per_run > 0
    assert settings.max_experiments_per_hypothesis > 0
    assert settings.default_runs_per_experiment > 0


def test_settings_from_dict():
    """Test settings can be created from dict."""
    settings = Settings.from_dict({
        "mode": "shadow",
        "database_url": "postgresql://test",
        "model_provider": "anthropic",
    })

    assert settings.mode == OperatingMode.SHADOW
    assert settings.database_url == "postgresql://test"
    assert settings.model_provider == "anthropic"
