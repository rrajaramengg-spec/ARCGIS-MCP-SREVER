"""Unit tests for handler auto-discovery (core/orchestrator/__init__.py)."""

import importlib
import pkgutil

import pytest
from unittest.mock import patch, MagicMock, call

import core.orchestrator as orch_pkg
from core.orchestrator import _auto_import_handler_modules
from core.orchestrator.base import _HANDLER_REGISTRY


class TestAutoDiscovery:
    """Tests for _auto_import_handler_modules."""

    def test_discovery_function_exists(self):
        """_auto_import_handler_modules is callable."""
        assert callable(_auto_import_handler_modules)

    def test_actions_directory_skipped(self):
        """Modules in _actions/ are not imported by auto-discovery."""
        # _actions modules should NOT register anything — they don't use @register_handler
        for name in _HANDLER_REGISTRY:
            assert "action" not in name, (
                f"Action module registered as handler: {name}"
            )

    def test_import_error_does_not_crash(self):
        """Import errors are logged as warnings, not raised."""
        mock_logger = MagicMock()
        with patch.object(orch_pkg, "logger", mock_logger), \
             patch.object(pkgutil, "walk_packages", return_value=[
                 (None, "core.orchestrator.broken_handler", False),
             ]), \
             patch.object(importlib, "import_module", side_effect=ImportError("test error")):
            # Should not raise
            _auto_import_handler_modules()
            mock_logger.warning.assert_called_once()

    def test_underscore_prefixed_modules_skipped(self):
        """Modules starting with _ are skipped entirely."""
        mock_import = MagicMock()
        with patch.object(pkgutil, "walk_packages", return_value=[
            (None, "core.orchestrator._private", False),
            (None, "core.orchestrator._actions.query_action", False),
        ]), patch.object(importlib, "import_module", mock_import):
            _auto_import_handler_modules()
            mock_import.assert_not_called()

    def test_public_modules_imported(self):
        """Non-underscore modules are imported."""
        mock_import = MagicMock()
        with patch.object(pkgutil, "walk_packages", return_value=[
            (None, "core.orchestrator.some_handler", False),
        ]), patch.object(importlib, "import_module", mock_import):
            _auto_import_handler_modules()
            mock_import.assert_called_once_with("core.orchestrator.some_handler")
