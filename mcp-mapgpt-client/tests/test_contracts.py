"""Unit tests for service contracts (core/contracts/)."""

import pytest

from core.contracts import ILLMService, IMCPClient, IRAGService


class TestILLMServiceContract:
    """Verify LLMService satisfies ILLMService protocol."""

    def test_llm_service_satisfies_contract(self, mock_config):
        """LLMService is structurally compatible with ILLMService."""
        from core.llm_service import LLMService

        assert isinstance(LLMService(mock_config), ILLMService)

    def test_protocol_is_runtime_checkable(self):
        """ILLMService can be used with isinstance() at runtime."""
        assert hasattr(ILLMService, "__protocol_attrs__") or hasattr(
            ILLMService, "_is_runtime_protocol"
        )


class TestIMCPClientContract:
    """Verify MCPClient satisfies IMCPClient protocol."""

    def test_mcp_client_satisfies_contract(self):
        """MCPClient is structurally compatible with IMCPClient."""
        from core.mcp_client import MCPClient

        assert isinstance(MCPClient(), IMCPClient)

    def test_protocol_is_runtime_checkable(self):
        """IMCPClient can be used with isinstance() at runtime."""
        assert hasattr(IMCPClient, "__protocol_attrs__") or hasattr(
            IMCPClient, "_is_runtime_protocol"
        )


class TestIRAGServiceContract:
    """Verify RAGService satisfies IRAGService protocol."""

    def test_rag_service_satisfies_contract(self):
        """RAGService is structurally compatible with IRAGService."""
        from core.rag.service import RAGService

        assert isinstance(RAGService(), IRAGService)

    def test_protocol_is_runtime_checkable(self):
        """IRAGService can be used with isinstance() at runtime."""
        assert hasattr(IRAGService, "__protocol_attrs__") or hasattr(
            IRAGService, "_is_runtime_protocol"
        )

    def test_non_conforming_class_fails(self):
        """A class that doesn't implement the protocol is not an instance."""

        class NotARAGService:
            pass

        assert not isinstance(NotARAGService(), IRAGService)
