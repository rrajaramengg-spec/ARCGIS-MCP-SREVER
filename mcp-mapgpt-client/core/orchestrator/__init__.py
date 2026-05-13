"""
MapGPT Orchestrator — modular handler architecture with dynamic dispatch.

Public API: MapGPTOrchestrator (identical interface to the original monolith).
Handlers register via @register_handler and are auto-discovered at init time.
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from core.config import ClientConfig
from core.llm_service import LLMService
from core.mcp_client import MCPClient

from .base import _HANDLER_REGISTRY, BaseHandler

logger = logging.getLogger(__name__)


def _auto_import_handler_modules() -> None:
    """Auto-import handler modules to trigger @register_handler decorators.

    Walks core.orchestrator package and imports all public modules.
    Modules with ``_``-prefixed names (e.g. ``_actions/``) are skipped.
    Import errors are logged as warnings without crashing startup.
    """
    import core.orchestrator as pkg

    base_prefix = pkg.__name__ + "."
    for _, modname, _ in pkgutil.walk_packages(
        pkg.__path__, prefix=base_prefix
    ):
        # Get the relative path segments after core.orchestrator.
        relative = modname[len(base_prefix):]
        parts = relative.split(".")
        if any(p.startswith("_") for p in parts):
            continue  # skips _actions/ and any of its children
        try:
            importlib.import_module(modname)
        except Exception:
            logger.warning(
                "Failed to import handler module: %s", modname, exc_info=True
            )


def _load_prompts() -> Dict[str, Any]:
    """Load prompts configuration from YAML."""
    config_path = Path(__file__).parent.parent.parent / "prompts" / "config_prompts.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class MapGPTOrchestrator:
    """Orchestrates the MapGPT query pipeline.

    Delegates to registered handlers discovered via the handler registry.
    Maintains shared state (MCP client, LLM service, prompts, tools cache)
    and injects only the dependencies each handler needs.
    """

    def __init__(self, mcp_client: MCPClient, llm_service: LLMService, rag_service=None, config: Optional[ClientConfig] = None) -> None:
        self._mcp = mcp_client
        self._llm = llm_service
        self._rag_service = rag_service
        self._config = config
        self._prompts = _load_prompts()
        self._tools_cache: List[Dict[str, Any]] = []

        # Build graph runtime — always enabled (graph-only pipeline)
        self._graph_runtime = None
        try:
            from core.orchestrator.graph import GraphRuntime, EXECUTOR_MAP
            self._graph_runtime = GraphRuntime(EXECUTOR_MAP)
            logger.info("Graph runtime enabled")
        except Exception:
            logger.warning("Failed to initialise graph runtime", exc_info=True)

        # Auto-discover handler modules (triggers @register_handler decorators)
        _auto_import_handler_modules()

        # Instantiate registered handlers with explicit DI
        self._handlers: Dict[str, BaseHandler] = {}
        self._prefix_routes: List[tuple] = []

        for name, meta in _HANDLER_REGISTRY.items():
            cls = meta["cls"]
            handler = self._create_handler(name, cls)
            self._handlers[name] = handler

            # Build prefix routing table
            if meta.get("prefix"):
                self._prefix_routes.append((meta["prefix"], name, handler))

        # Sort by prefix length descending for overlap safety
        # (e.g., "/summarize-stat " before "/summarize ")
        self._prefix_routes.sort(key=lambda x: len(x[0]), reverse=True)

        logger.info(
            "Orchestrator initialised — %d handlers, %d prefix routes",
            len(self._handlers),
            len(self._prefix_routes),
        )

    def _create_handler(self, name: str, cls: type) -> BaseHandler:
        """Create a handler instance with the correct dependencies."""
        # Handlers that need prompts + tools_cache (+ optional rag_service)
        if name in ("query", "execute_llm"):
            kwargs = dict(
                mcp=self._mcp,
                llm=self._llm,
                prompts=self._prompts,
                tools_cache=self._tools_cache,
                rag_service=self._rag_service,
            )
            if name == "query":
                kwargs["graph_runtime"] = self._graph_runtime
                kwargs["config"] = self._config
            return cls(**kwargs)
        if name == "arcgis_execute":
            return cls(
                mcp=self._mcp,
                llm=self._llm,
                prompts=self._prompts,
                tools_cache=self._tools_cache,
            )
        # Handlers that need prompts only
        if name in ("summarize", "summarize_stat"):
            return cls(
                mcp=self._mcp,
                llm=self._llm,
                prompts=self._prompts,
            )
        # Handlers that need only base deps (mcp, llm)
        return cls(
            mcp=self._mcp,
            llm=self._llm,
        )

    

    async def plan(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a query plan via RAG + LLM without executing against ArcGIS."""
        return await self._handlers["query"].plan(query=query, session_id=session_id)

    async def execute(
        self,
        query: str,
        session_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Execute a query through the full pipeline with dynamic prefix routing."""
        # Prefix routing — check registered prefixes
        for prefix, handler_name, handler in self._prefix_routes:
            if query.startswith(prefix):
                stripped_query = query[len(prefix):]
                logger.info("Prefix routing: '%s' → %s", prefix.strip(), handler_name)

                if handler_name == "locate":
                    locate_result = await handler.locate(address=stripped_query)
                    # Wrap LocateResponse into ExecuteResponse shape
                    error_msg = locate_result.get("error")
                    message = error_msg if error_msg else locate_result.get("address")
                    return {
                        "action": "locate",
                        "message": message,
                        "data": locate_result,
                        "tool_name": "geocode",
                        "tool_args": {"address": stripped_query},
                        "execution_time_ms": locate_result.get("execution_time_ms", 0),
                        "timing": locate_result.get("timing"),
                    }
                elif handler_name == "summarize_stat":
                    return await handler.summarize_stat(
                        query=stripped_query,
                        session_id=session_id,
                        plan_fn=self.plan,
                        summarize_fn=self.summarize,
                    )
                elif handler_name == "summarize":
                    return await handler.summarize(
                        query=stripped_query,
                        session_id=session_id,
                        execute_fn=self.execute,
                    )
                elif handler_name == "arcgis_execute":
                    return await handler.arcgis_execute(
                        query=stripped_query,
                        session_id=session_id,
                    )
                elif handler_name == "execute_llm":
                    return await handler.execute_llm(
                        query=stripped_query,
                        session_id=session_id,
                    )

        # No prefix matched — default to query handler
        return await self._handlers["query"].execute(
            query=query, session_id=session_id,
            progress_callback=progress_callback,
        )

    async def locate(
        self,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Direct geocoding without LLM planning."""
        return await self._handlers["locate"].locate(
            address=address, latitude=latitude, longitude=longitude
        )

    async def summarize(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a query and return an LLM-generated summary."""
        return await self._handlers["summarize"].summarize(
            query=query, session_id=session_id, execute_fn=self.execute
        )

    async def summarize_stat(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Summarize a field's statistics via the summarize_field MCP tool."""
        return await self._handlers["summarize_stat"].summarize_stat(
            query=query,
            session_id=session_id,
            plan_fn=self.plan,
            summarize_fn=self.summarize,
        )

    async def arcgis_execute(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Direct MCP tool invocation via LLM."""
        return await self._handlers["arcgis_execute"].arcgis_execute(
            query=query, session_id=session_id
        )

    async def execute_llm(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RAG-augmented LLM tool-calling execution."""
        return await self._handlers["execute_llm"].execute_llm(
            query=query, session_id=session_id
        )
