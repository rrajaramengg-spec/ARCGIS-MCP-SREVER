"""Dependency provider module for FastAPI Depends() injection.

Holds references set during app lifespan. Routes use get_orchestrator()
and get_rag_service() with FastAPI's Depends() instead of lazy global imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import ClientConfig
    from core.orchestrator import MapGPTOrchestrator
    from core.rag.service import RAGService

_config: "ClientConfig | None" = None
_orchestrator: "MapGPTOrchestrator | None" = None
_rag_service: "RAGService | None" = None


def set_config(cfg: "ClientConfig") -> None:
    """Set the config instance during app lifespan startup.

    Args:
        cfg: Validated ClientConfig instance.
    """
    global _config
    _config = cfg


def get_config() -> "ClientConfig":
    """FastAPI dependency — returns the ClientConfig instance.

    Returns:
        The validated ClientConfig.

    Raises:
        RuntimeError: If called before lifespan startup completes.
    """
    if _config is None:
        raise RuntimeError("ClientConfig not initialized")
    return _config


def set_orchestrator(orch: "MapGPTOrchestrator") -> None:
    """Set the orchestrator instance during app lifespan startup.

    Args:
        orch: Fully initialized MapGPTOrchestrator.
    """
    global _orchestrator
    _orchestrator = orch


def get_orchestrator() -> "MapGPTOrchestrator":
    """FastAPI dependency — returns the orchestrator instance.

    Returns:
        The initialized MapGPTOrchestrator.

    Raises:
        RuntimeError: If called before lifespan startup completes.
    """
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized")
    return _orchestrator


def set_rag_service(svc: "RAGService") -> None:
    """Set the RAG service instance during app lifespan startup.

    Args:
        svc: Fully initialized RAGService.
    """
    global _rag_service
    _rag_service = svc


def get_rag_service() -> "RAGService":
    """FastAPI dependency — returns the RAG service instance.

    Returns:
        The initialized RAGService.

    Raises:
        RuntimeError: If called before lifespan startup completes.
    """
    if _rag_service is None:
        raise RuntimeError("RAGService not initialized")
    return _rag_service
