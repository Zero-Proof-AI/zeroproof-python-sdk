"""
Proxy Fetch Module - Route HTTP requests through a proxy server

This module provides a `ProxyFetch` client that routes HTTP requests through either:
- Standard HTTP proxies with optional authentication
- zkfetch-wrapper for privacy-preserving ZK proof generation

Supports tool-specific configuration for MCP tool calls, allowing different
tools to have different redaction policies and ZK options.
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs, unquote

import httpx


@dataclass
class ZkfetchToolOptions:
    """Tool-specific ZK proof configuration for zkfetch-wrapper"""
    # Options exposed in the generated ZK proof (e.g., method, headers)
    public_options: Optional[Dict[str, Any]] = None

    # Options hidden from the ZK proof (e.g., sensitive data)
    private_options: Optional[Dict[str, Any]] = None

    # Fields to exclude from the proof (specified as JSON paths)
    # Example: `{"jsonPath": "$.data.card_number"}` to hide the card_number field
    redactions: Optional[List[Dict[str, Any]]] = None

    # Sensitive field paths in the response that should be redacted
    # Maps field names to their jsonPath in the response structure
    # Example: `{"passenger_name": "$.data.passenger_name"}`
    response_redaction_paths: Optional[Dict[str, str]] = None


@dataclass
class RedactionRule:
    """A redaction rule for masking sensitive data in proofs

    Redactions use dot-notation paths to identify fields to mask.
    Examples:
    - `"response.data.passenger_name"` - masks passenger_name in response data
    - `"body.card_number"` - masks card_number in request body
    - `"request.body.cvv"` - masks CVV in request body
    """
    # Dot-notation path to the field to redact (e.g., "body.passenger_name")
    path: str

    # Type of redaction: "mask" (****), "hash", "remove"
    redaction_type: str = "mask"


@dataclass
class AttestationConfig:
    """Configuration for attestation service proof submission

    When enabled, ProxyFetch will automatically extract ZK proofs from zkfetch responses
    and submit them to the attestation service for storage and verification.
    """
    # URL of the attestation service (e.g., 'http://localhost:3001')
    service_url: str

    # Whether to automatically submit proofs to the attestation service
    enabled: bool = True

    # Optional workflow stage identifier (e.g., "pricing", "payment", "booking")
    # If not provided, will be auto-inferred from the tool name
    workflow_stage: Optional[str] = None

    # Unique session identifier for grouping related proofs
    # If not provided, one will be generated per request
    session_id: Optional[str] = None

    # Agent identifier for proof submission attribution (e.g., "agent-a" or "agent-b")
    submitted_by: str = "unknown-agent"

    @classmethod
    def new(cls, service_url: str) -> "AttestationConfig":
        """Creates a new attestation config for automatic proof submission"""
        return cls(service_url=service_url)

    @classmethod
    def with_stage(cls, service_url: str, workflow_stage: str) -> "AttestationConfig":
        """Creates an attestation config with a specific workflow stage"""
        return cls(
            service_url=service_url,
            workflow_stage=workflow_stage
        )


# Type alias for tool-specific redaction options
ToolOptionsMap = Dict[str, ZkfetchToolOptions]


@dataclass
class ProxyConfig:
    """Configuration for proxy server routing"""

    # Proxy server URL (e.g., 'http://localhost:8000' for zkfetch-wrapper)
    url: str

    # Type of proxy: "http" (standard proxy) or "zkfetch" (privacy-preserving)
    proxy_type: str = "http"

    # Optional username for proxy authentication
    username: Optional[str] = None

    # Optional password for proxy authentication
    password: Optional[str] = None

    # Per-tool ZK options for different MCP tools
    tool_options_map: Optional[Dict[str, ZkfetchToolOptions]] = None

    # Default ZK options applied to all tools without specific config
    default_zk_options: Optional[ZkfetchToolOptions] = None

    # Enable debug logging for proxy requests
    debug: bool = False

    # Optional attestation service configuration for automatic proof submission
    attestation_config: Optional[AttestationConfig] = None


class ProxyFetch:
    """HTTP client that routes requests through a proxy server

    Supports:
    - Standard HTTP proxies with optional authentication
    - zkfetch-wrapper for privacy-preserving ZK proof generation
    - Tool-specific ZK options for different MCP tools
    - Both sync and async operations
    """

    def __init__(self, config: ProxyConfig):
        """Creates a new ProxyFetch client with the given configuration"""
        self.config = config
        # Create HTTP client with extended timeout for proof generation and booking operations
        # Proof generation can take time, so we set a generous timeout
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(900.0)  # 15 minutes timeout for proof generation
        )

    async def get(self, url: str) -> Dict[str, Any]:
        """Makes a GET request through the proxy"""
        return await self.request(url, "GET", None)

    async def post(self, url: str, body: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Makes a POST request through the proxy"""
        return await self.request(url, "POST", body)

    async def put(self, url: str, body: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Makes a PUT request through the proxy"""
        return await self.request(url, "PUT", body)

    async def delete(self, url: str) -> Dict[str, Any]:
        """Makes a DELETE request through the proxy"""
        return await self.request(url, "DELETE", None)

    async def request(self, url: str, method: str, body: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Makes a generic HTTP request through the proxy

        This method:
        1. Determines proxy type (HTTP or zkfetch)
        2. For zkfetch: extracts tool name from request body
        3. Resolves tool-specific ZK options
        4. Routes request through appropriate proxy
        """
        if self.config.proxy_type == "zkfetch":
            return await self._zkfetch_request(url, method, body)
        else:
            return await self._http_proxy_request(url, method, body)

    async def _http_proxy_request(
        self,
        url: str,
        method: str,
        body: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Routes a request through standard HTTP proxy"""
        if self.config.debug:
            print(f"🔀 Routing through HTTP proxy: {self.config.url} ({method})")

        request = self._build_request(url, method, body)

        # Add proxy authentication if credentials provided
        if self.config.username and self.config.password:
            import base64
            credentials = base64.b64encode(
                f"{self.config.username}:{self.config.password}".encode()
            ).decode()
            request.headers["Proxy-Authorization"] = f"Basic {credentials}"

        response = await request.send()
        return await self._handle_response(response)

    async def _zkfetch_request(
        self,
        url: str,
        method: str,
        body: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Routes a request through zkfetch-wrapper for ZK proof generation

        This method:
        1. Extracts tool name from request body (for tool-specific options)
        2. Resolves per-tool ZK options or uses default
        3. Builds zkfetch payload with public/private/redactions
        4. POSTs to zkfetch-wrapper /zkfetch endpoint
        5. Returns the verified response
        """
        # Extract tool name from request body for option resolution
        tool_name = self._extract_tool_name(body)

        if self.config.debug:
            print(f"🔐 Routing through zkfetch: {self.config.url} (tool: {tool_name})")

        # Resolve tool-specific ZK options
        zk_options = self._resolve_tool_options(tool_name)

        # Extract hidden parameters and convert to paramValues
        final_body = body or {}
        private_options = dict(zk_options.private_options) if zk_options.private_options else {}
        final_url = url

        # Parse body if it's a string (likely from JSON serialization)
        if isinstance(final_body, str):
            try:
                final_body = json.loads(final_body)
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract hidden parameters from body and URL
        param_values_map = {}

        if "hiddenParameters" in private_options:
            hidden_params = private_options.get("hiddenParameters", [])
            if isinstance(hidden_params, list):
                # Extract from request body
                if isinstance(final_body, dict):
                    for param in hidden_params:
                        if isinstance(param, str) and param in final_body:
                            param_values_map[param] = final_body[param]
                            final_body[param] = f"{{{param}}}"

                # Extract from URL query parameters
                if "?" in url:
                    base_url, query_string = url.split("?", 1)
                    query_params = parse_qs(query_string, keep_blank_values=True)
                    url_modified = False
                    new_query_parts = []

                    for key, values in query_params.items():
                        if key in hidden_params:
                            actual_value = unquote(values[0]) if values else ""
                            param_values_map[key] = actual_value
                            new_query_parts.append(f"{key}={{{{{key}}}}}")
                            url_modified = True
                        else:
                            for value in values:
                                new_query_parts.append(f"{key}={value}")

                    if url_modified:
                        final_url = f"{base_url}?{'&'.join(new_query_parts)}"

                if param_values_map:
                    private_options["paramValues"] = param_values_map
                    private_options.pop("hideRequestBody", None)
                    private_options.pop("hiddenParameters", None)

        # Build zkfetch payload
        zkfetch_payload = {
            "url": final_url,
            "publicOptions": {
                "method": method,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(final_body) if final_body else None,
                "timeout": zk_options.public_options.get("timeout", 30000) if zk_options.public_options else 30000,
            },
            "privateOptions": private_options,
            "redactions": zk_options.redactions or [],
        }

        if self.config.debug:
            print("📦 Final zkfetch payload structure:")
            print(f"  URL: {final_url}")
            print(f"  Method: {method}")
            public_opts = zkfetch_payload.get("publicOptions", {})
            body_content = public_opts.get("body", "")
            print(f"  Public body: {body_content}")

            # Log privateOptions structure
            if "privateOptions" in zkfetch_payload:
                private_opts = zkfetch_payload["privateOptions"]
                print(f"  Private options keys: {list(private_opts.keys()) if isinstance(private_opts, dict) else 'N/A'}")
                if "paramValues" in private_opts:
                    param_values = private_opts["paramValues"]
                    count = len(param_values) if isinstance(param_values, dict) else 0
                    print(f"  ✓ paramValues present: {count} keys")
                else:
                    print("  ✗ paramValues NOT in privateOptions!")

        # POST to zkfetch-wrapper
        zkfetch_url = f"{self.config.url}/zkfetch"
        response = await self.client.post(zkfetch_url, json=zkfetch_payload)
        zkfetch_response = await self._handle_response(response)

        # If attestation is configured, extract proof and submit it asynchronously
        if self.config.attestation_config and self.config.attestation_config.enabled:
            print(f"[PROXY_FETCH] attestation_config is Some, enabled={self.config.attestation_config.enabled}")
            print(f"[PROXY_FETCH] Submitting proof for tool: {tool_name}")
            await self._submit_proof_async(
                zkfetch_response,
                tool_name,
                self.config.attestation_config,
                final_body,
                final_url,
            )
            print(f"[PROXY_FETCH] ✓ Spawn call completed for tool: {tool_name}")
        else:
            print("[PROXY_FETCH] attestation_config is None!")

        return zkfetch_response

    async def _submit_proof_async(
        self,
        zkfetch_response: Dict[str, Any],
        tool_name: Optional[str],
        attestation_config: AttestationConfig,
        request_body: Dict[str, Any],
        request_url: str,
    ) -> None:
        """Extract proof from zkfetch response and submits it to attestation service asynchronously"""
        tool_name_str = tool_name or "direct-fetch"

        # Extract proof from zkfetch response
        # The proof is directly at response.proof, not response.proof.proof
        proof_value = zkfetch_response.get("proof")

        print(f"[PROXY_FETCH] Extracted proof_value for {tool_name_str}: {proof_value is not None}")

        if proof_value:
            # Generate session ID if not provided
            session_id = (
                attestation_config.session_id
                or f"agent-{tool_name_str}-{int(time.time())}"
            )

            # Use provided workflow stage or default to "general"
            workflow_stage = attestation_config.workflow_stage or "general"

            # Check if onchainProof exists in response - if yes, proof is on-chain compatible
            onchain_compatible = "onchainProof" in zkfetch_response

            # Create background task to submit proof
            service_url = attestation_config.service_url
            tool_name_clone = tool_name_str
            response_body = zkfetch_response.copy()

            # Create the task (in Python, we can use asyncio.create_task)
            async def submit_task():
                print(f"[PROXY_FETCH] 🚀 Spawned task started for: {tool_name_clone}")
                # Create CryptographicProof structure
                from .proof import CryptographicProof

                crypto_proof = CryptographicProof(
                    tool_name=tool_name_clone,
                    timestamp=int(time.time()),
                    request={
                        "url": request_url,
                        "body": request_body,
                    },
                    response=response_body,
                    proof={
                        "proof": proof_value,
                        "onchainProof": response_body.get("onchainProof"),
                    },
                    verified=zkfetch_response.get("verified", False),
                    onchain_compatible=onchain_compatible,
                )

                try:
                    from .proof import submit_proof
                    proof_id = await submit_proof(
                        self.client,
                        service_url,
                        session_id,
                        crypto_proof,
                        workflow_stage,
                        attestation_config.submitted_by,
                    )
                    print(f"[PROXY_FETCH] ✓ Proof submitted to attestation service for {tool_name_clone}: {proof_id}")
                except Exception as e:
                    print(f"[PROXY_FETCH] Failed to submit proof for {tool_name_clone}: {e}")

            # Create and run the task
            asyncio.create_task(submit_task())

    def _build_request(
        self,
        url: str,
        method: str,
        body: Optional[Dict[str, Any]],
    ) -> httpx.Request:
        """Builds a request builder for the given URL and method"""
        if method == "GET":
            request = self.client.build_request("GET", url)
        elif method == "POST":
            request = self.client.build_request("POST", url, json=body)
        elif method == "PUT":
            request = self.client.build_request("PUT", url, json=body)
        elif method == "DELETE":
            request = self.client.build_request("DELETE", url)
        elif method == "PATCH":
            request = self.client.build_request("PATCH", url, json=body)
        elif method == "HEAD":
            request = self.client.build_request("HEAD", url)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        request.headers["Content-Type"] = "application/json"
        return request

    async def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handles HTTP response and extracts JSON body"""
        if not response.is_success:
            error_text = response.text
            raise Exception(f"Proxy request failed with status {response.status_code}: {error_text}")

        return response.json()

    def _extract_tool_name(self, body: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extracts tool name from request body

        Looks for these patterns in order:
        1. body.name (for MCP tools)
        2. body.params.name (nested tool name)
        3. body.params.toolName (snake_case variant)
        4. Returns None if not found
        """
        if not body:
            return None

        # Try direct name field
        if "name" in body and isinstance(body["name"], str):
            return body["name"]

        # Try nested params.name
        if "params" in body and isinstance(body["params"], dict):
            params = body["params"]
            if "name" in params and isinstance(params["name"], str):
                return params["name"]

            # Try params.toolName (snake_case variant)
            if "toolName" in params and isinstance(params["toolName"], str):
                return params["toolName"]

        return None

    def _resolve_tool_options(self, tool_name: Optional[str]) -> ZkfetchToolOptions:
        """Resolves tool-specific ZK options

        Resolution order:
        1. If tool_name is Some, looks up in tool_options_map
        2. Falls back to default_zk_options if provided
        3. Returns empty ZkfetchToolOptions if neither found
        """
        if tool_name and self.config.tool_options_map and tool_name in self.config.tool_options_map:
            return self.config.tool_options_map[tool_name]

        if self.config.default_zk_options:
            return self.config.default_zk_options

        return ZkfetchToolOptions()

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


def apply_redactions(value: Dict[str, Any], redactions: List[Dict[str, Any]]) -> None:
    """Apply redactions to a JSON value based on a list of redaction rules

    Redactions are applied using dot-notation paths. Each redaction
    masks the value at the specified path with "****".

    Args:
        value: The JSON value to redact (modified in-place)
        redactions: List of redaction rules to apply
    """
    for redaction in redactions:
        if "path" in redaction:
            path = redaction["path"]
            _redact_at_path(value, path)


def _redact_at_path(value: Dict[str, Any], path: str) -> None:
    """Redact a value at a specific dot-notation path

    Navigates through nested objects using dot-separated path components
    and masks the final value with "****".

    Args:
        value: The root JSON value to navigate
        path: Dot-notation path (e.g., "response.data.passenger_name")
    """
    parts = path.split(".")
    if not parts:
        return

    # Navigate to the parent of the target field
    current = value
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            # Last component: redact it
            if isinstance(current, dict) and part in current:
                current[part] = "****"
        else:
            # Intermediate component: navigate deeper
            if not isinstance(current, dict):
                # If we hit a non-object before reaching the end, we can't navigate further
                return

            # Ensure the next level exists and navigate into it
            if part not in current:
                # Path doesn't exist, can't redact
                return

            current = current[part]