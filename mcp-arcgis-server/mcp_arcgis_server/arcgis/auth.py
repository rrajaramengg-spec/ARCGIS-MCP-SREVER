"""
GIS authentication manager with multi-strategy initialization.

Handles ArcGIS portal authentication via three fallback strategies:
1. Standard GIS init (username/password)
2. Explicit token URL with use_gen_token
3. Pre-generated REST token

Thread-safe token refresh via asyncio.Lock.
"""

import asyncio
import logging
import os
from typing import List, Optional
from urllib.parse import urlparse

import requests as _requests
from arcgis.gis import GIS

logger = logging.getLogger(__name__)


class GISAuthManager:
    """Manages ArcGIS GIS instance lifecycle and authentication."""

    def __init__(self, config=None) -> None:
        self._gis: Optional[GIS] = None
        self._arcgis_hostname: str = ""
        self._verify_ssl: bool = True
        self._init_strategy: int = 0
        self._refresh_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()

        # Read from config if provided, else fall back to env vars
        if config is not None:
            self._portal_url = config.portal_url
            self._username = config.username
            self._password = config.password
            self._verify_ssl = config.verify_ssl
            self._token_url = config.token_url
            self._server_url = config.server_url
        else:
            # Resolve portal URL
            self._portal_url = os.getenv("ARCGIS_PORTAL_URL", "")
            if not self._portal_url:
                legacy_url = os.getenv("ARCGIS_URL", "")
                if legacy_url:
                    logger.warning(
                        "ARCGIS_URL is deprecated, use ARCGIS_PORTAL_URL instead"
                    )
                    self._portal_url = legacy_url

            self._username = os.getenv("ARCGIS_USERNAME", "")
            self._password = os.getenv("ARCGIS_PASSWORD", "")
            self._verify_ssl = os.getenv("ARCGIS_VERIFY_SSL", "true").lower() not in (
                "false",
                "0",
                "no",
            )
            self._token_url = os.getenv("ARCGIS_TOKEN_URL", "")
            self._server_url = os.getenv("ARCGIS_SERVER_URL", "")

        # Extract hostname for domain-based auth routing
        if self._portal_url:
            try:
                self._arcgis_hostname = (
                    urlparse(self._portal_url).hostname or ""
                ).lower()
            except Exception:
                pass

    @property
    def gis(self) -> Optional[GIS]:
        """The authenticated GIS instance, or None if not initialized."""
        return self._gis

    @property
    def arcgis_hostname(self) -> str:
        return self._arcgis_hostname

    @property
    def init_strategy(self) -> int:
        return self._init_strategy

    async def initialize(self) -> None:
        """Initialize GIS connection (runs blocking init in a thread).

        Guarded by _init_lock to prevent concurrent initialization.
        Skips if already initialized.
        """
        async with self._init_lock:
            if self._gis is not None:
                return
            if self._portal_url and self._username and self._password:
                await asyncio.to_thread(self._initialize_gis)
            else:
                logger.info(
                    "GIS not initialized — domain=%s, credentials=%s",
                    self._arcgis_hostname or "(none)",
                    "set" if (self._username and self._password) else "unset",
                )

    def _initialize_gis(self) -> None:
        """Try multiple GIS initialization strategies in sequence (blocking)."""
        # Strategy 1: Standard GIS init
        try:
            logger.debug("GIS init strategy 1: standard auth")
            self._gis = GIS(
                url=self._portal_url,
                username=self._username,
                password=self._password,
                verify_cert=self._verify_ssl,
            )
            self._init_strategy = 1
            logger.info(
                "GIS initialized via standard auth — portal=%s, user=%s",
                self._portal_url,
                self._username,
            )
            return
        except Exception as exc:
            logger.debug("GIS strategy 1 failed: %s", exc)

        # Strategy 2: Explicit token URL with use_gen_token
        token_url = self._resolve_token_url()
        try:
            logger.debug("GIS init strategy 2: explicit token_url=%s", token_url)
            self._gis = GIS(
                url=self._portal_url,
                username=self._username,
                password=self._password,
                verify_cert=self._verify_ssl,
                token_url=token_url,
                use_gen_token=True,
            )
            self._init_strategy = 2
            logger.info(
                "GIS initialized via explicit token URL — token_url=%s",
                token_url,
            )
            return
        except Exception as exc:
            logger.debug("GIS strategy 2 failed: %s", exc)

        # Strategy 3: Pre-generated token via REST, then GIS(token=...)
        logger.debug("GIS init strategy 3: pre-generated token")
        token = self._generate_token()
        if token:
            try:
                self._gis = GIS(
                    url=self._portal_url,
                    token=token,
                    verify_cert=self._verify_ssl,
                )
                self._init_strategy = 3
                logger.info(
                    "GIS initialized via pre-generated token — portal=%s",
                    self._portal_url,
                )
                return
            except Exception as exc:
                logger.debug("GIS strategy 3 (GIS with token) failed: %s", exc)

        # All strategies failed
        self._gis = None
        self._init_strategy = 0
        logger.error(
            "All GIS initialization strategies failed — portal=%s. "
            "Queries to secured services will fail. "
            "Set ARCGIS_TOKEN_URL or ARCGIS_SERVER_URL to override token endpoint.",
            self._portal_url,
        )

    async def refresh(self, clear_layer_cache_fn=None) -> None:
        """Re-initialize GIS with lock to prevent concurrent refreshes.

        Args:
            clear_layer_cache_fn: Optional callable to clear the client's layer cache
                                  after successful refresh.
        """
        async with self._init_lock:
            async with self._refresh_lock:
                logger.info("Re-initializing GIS (token may have expired)")
                self._gis = None
                await asyncio.to_thread(self._initialize_gis)
                if clear_layer_cache_fn:
                    clear_layer_cache_fn()

    def _reinitialize_gis(self) -> None:
        """Synchronous re-init (legacy compat). Prefer async refresh()."""
        logger.info("Re-initializing GIS (token may have expired)")
        self._initialize_gis()

    def _resolve_token_url(self) -> str:
        """Resolve the explicit token URL using priority order."""
        if self._token_url:
            return self._token_url

        if self._server_url:
            return f"{self._server_url.rstrip('/')}/tokens/generateToken"

        return f"{self._portal_url.rstrip('/')}/sharing/rest/generateToken"

    def _get_token_candidate_urls(self) -> List[str]:
        """Return ordered list of candidate token URLs for strategy 3 REST fallback."""
        candidates: List[str] = []

        if self._token_url:
            candidates.append(self._token_url)

        if self._server_url:
            candidates.append(f"{self._server_url.rstrip('/')}/tokens/generateToken")

        if self._portal_url:
            parsed = urlparse(self._portal_url)
            base = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port and parsed.port not in (80, 443):
                base += f":{parsed.port}"
            server_candidate = f"{base}/server/tokens/generateToken"
            if server_candidate not in candidates:
                candidates.append(server_candidate)

        if self._portal_url:
            portal_candidate = (
                f"{self._portal_url.rstrip('/')}/sharing/rest/generateToken"
            )
            if portal_candidate not in candidates:
                candidates.append(portal_candidate)

        return candidates

    def _generate_token(self) -> Optional[str]:
        """Generate a token via direct REST POST to candidate token URLs (blocking).

        Tries two client types per URL:
        1. client=referer  (matches working shell/curl usage — most compatible)
        2. client=requestip (fallback for servers that don't accept referer)
        """
        candidates = self._get_token_candidate_urls()

        # Try referer-based token first (mirrors the working shell script approach),
        # then fall back to requestip.
        client_variants = [
            {"client": "requestip"},
            {"client": "referer", "referer": "https://localhost", "expiration": "60"}
           
        ]

        for url in candidates:
            for client_params in client_variants:
                try:
                    data = {
                        "username": self._username,
                        "password": self._password,
                        "f": "json",
                        **client_params,
                    }
                    resp = _requests.post(
                        url,
                        data=data,
                        verify=self._verify_ssl,
                        timeout=30,
                    )
                    result = resp.json()
                    if "token" in result and result["token"]:
                        logger.info(
                            "Token generated via %s (client=%s)",
                            url, client_params["client"],
                        )
                        return result["token"]
                    if "error" in result:
                        logger.debug(
                            "Token endpoint %s client=%s returned error: %s",
                            url, client_params["client"], result["error"],
                        )
                except Exception as exc:
                    logger.debug(
                        "Token generation failed at %s client=%s: %s",
                        url, client_params.get("client"), exc,
                    )

        return None

    def is_internal_url(self, layer_url: str) -> bool:
        """Return True if layer_url hostname matches the configured ArcGIS domain."""
        if not self._arcgis_hostname:
            return False
        try:
            layer_hostname = (urlparse(layer_url).hostname or "").lower()
            return layer_hostname == self._arcgis_hostname
        except Exception:
            return False
