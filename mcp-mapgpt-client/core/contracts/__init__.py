"""Service contracts — Protocol interfaces for dependency injection."""

from .llm import ILLMService
from .mcp import IMCPClient
from .rag import IRAGService

__all__ = [
    "ILLMService",
    "IMCPClient",
    "IRAGService",
]
