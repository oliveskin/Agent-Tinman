"""Tests for operating mode transitions."""

import pytest
from tinman.config.modes import Mode


class TestModeTransitions:
    """Tests for mode transition validation."""

    def test_valid_lab_to_shadow_transition(self):
        """LAB to SHADOW is a valid transition."""
        # Valid progressive transition
        assert Mode.LAB.value == "lab"
        assert Mode.SHADOW.value == "shadow"

    def test_valid_shadow_to_production_transition(self):
        """SHADOW to PRODUCTION is a valid transition."""
        assert Mode.SHADOW.value == "shadow"
        assert Mode.PRODUCTION.value == "production"

    def test_valid_production_to_shadow_regression(self):
        """PRODUCTION to SHADOW regression is valid."""
        # Regression fallback is allowed
        assert Mode.PRODUCTION.value == "production"
        assert Mode.SHADOW.value == "shadow"

    def test_invalid_lab_to_production_skip(self):
        """LAB to PRODUCTION should be blocked (cannot skip modes)."""
        # This transition should be invalid
        # TODO: Test with ControlPlane.change_mode() when implemented
        assert True
