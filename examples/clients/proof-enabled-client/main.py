#!/usr/bin/env python3
"""Proof-enabled MCP client example demonstrating call_tool_with_proof.

This example shows how to use the MCP client's call_tool_with_proof method
to call tools with cryptographic proof collection. It demonstrates two use cases:

1. Without redaction: All data is included in the proof
2. With redaction: Sensitive data is hidden from the proof

The example calls the "book-flight" tool from an Agent B MCP server.
"""

import asyncio
import json
import os
import sys
import time
from typing import Dict, Any, Optional

# Add the SDK src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.proxy_fetch import ZkfetchToolOptions, ToolOptionsMap, ProxyFetch, ProxyConfig
from mcp.shared.proof import CryptographicProof


class SimpleMCPClient:
    """Simple MCP client using HTTP POST requests."""

    def __init__(self, server_url: str, zkfetch_url: Optional[str] = None):
        self.server_url = server_url
        self.zkfetch_url = zkfetch_url
        self.next_id = 1

    async def call_tool_with_proof(
        self,
        name: str,
        arguments: Dict[str, Any],
        server_url: str,
        zkfetch_wrapper_url: Optional[str] = None,
        tool_options_map: Optional[ToolOptionsMap] = None,
    ) -> tuple[Any, Optional[CryptographicProof]]:
        """Call a tool with optional proof generation via zkfetch.
        
        If zkfetch_wrapper_url is provided, routes through ProxyFetch for proof generation.
        If tool_options_map is also provided, ProxyFetch applies redaction rules automatically.
        Otherwise, direct MCP call without proof.
        """
        if zkfetch_wrapper_url:
            # Route through zkfetch-wrapper (with or without redaction)
            return await self._call_with_zkfetch(
                name, arguments, server_url, zkfetch_wrapper_url, tool_options_map
            )
        
        # Direct call without proof
        result = await self.call("tools/call", {
            "name": name,
            "arguments": arguments
        })

        # Parse the result
        content = result['result']['content'][0]['text']
        tool_result = json.loads(content)

        # Wrap the response in adapter classes to provide the expected interface
        class ToolResultAdapter:
            def __init__(self, content_data):
                self.content = [ToolContentWrapper(content_data)]

        class ToolContentWrapper:
            def __init__(self, data):
                self.text = json.dumps(data)

        return ToolResultAdapter(tool_result), None

    async def _call_with_zkfetch(
        self,
        name: str,
        arguments: Dict[str, Any],
        server_url: str,
        zkfetch_wrapper_url: str,
        tool_options_map: Optional[ToolOptionsMap] = None,
    ) -> tuple[Any, Optional[CryptographicProof]]:
        """Call a tool through zkfetch-wrapper with optional redaction.
        
        ProxyFetch handles redaction automatically if tool_options_map is provided.
        """
        # Create ProxyFetch instance with tool options (may be None)
        proxy_config = ProxyConfig(
            url=zkfetch_wrapper_url,
            tool_options_map=tool_options_map,
            debug=True,
        )
        proxy_fetch = ProxyFetch(proxy_config)

        # Build the MCP tool call payload
        mcp_payload = {
            "jsonrpc": "2.0",
            "id": self.next_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            }
        }
        self.next_id += 1

        # Route through zkfetch-wrapper via ProxyFetch
        # ProxyFetch automatically applies redaction if tool_options_map is provided
        zkfetch_response = await proxy_fetch._zkfetch_request(
            url=self.server_url,
            method="POST",
            body=mcp_payload,
        )

        # Extract the MCP response from zkfetch response
        # The response is in the 'data' field
        mcp_result = {}
        if 'data' in zkfetch_response:
            data = zkfetch_response['data']
            if isinstance(data, str):
                try:
                    mcp_result = json.loads(data)
                except json.JSONDecodeError:
                    mcp_result = {}
            else:
                mcp_result = data

        # Parse tool result from the MCP response
        content = mcp_result.get('result', {}).get('content', [{}])[0].get('text', '{}')
        if isinstance(content, str):
            try:
                tool_result = json.loads(content)
            except json.JSONDecodeError:
                tool_result = {}
        else:
            tool_result = content

        # Extract proof from zkfetch response
        proof = None
        if 'proof' in zkfetch_response and zkfetch_response['proof']:
            proof_data = zkfetch_response['proof']
            # Include onchainProof if present in the zkfetch response
            if 'onchainProof' in zkfetch_response:
                proof_data['onchainProof'] = zkfetch_response['onchainProof']
            proof = CryptographicProof(
                tool_name=name,
                timestamp=int(time.time()),
                request=arguments,
                response=tool_result,
                proof=proof_data,
                proof_id=proof_data.get("proof_id"),
                verified=proof_data.get("verified", True),
                onchain_compatible=zkfetch_response.get("onchainProof") is not None,
                display_response=tool_result,
                redaction_metadata=None,
            )

        # Wrap the response in adapter classes
        class ToolResultAdapter:
            def __init__(self, content_data):
                self.content = [ToolContentWrapper(content_data)]

        class ToolContentWrapper:
            def __init__(self, data):
                self.text = json.dumps(data)

        return ToolResultAdapter(tool_result), proof

    async def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make an MCP call."""
        request = {
            "jsonrpc": "2.0",
            "id": self.next_id,
            "method": method,
        }
        if params:
            request["params"] = params

        self.next_id += 1

        async with httpx.AsyncClient(timeout=300.0) as client:  # Increased timeout
            response = await client.post(
                self.server_url,
                json=request,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()

    async def initialize(self):
        """Initialize MCP session."""
        return await self.call("initialize")


def build_tool_options_map() -> ToolOptionsMap:
    """Build a map of tool-specific redaction rules for privacy-preserving proofs.

    This defines which sensitive fields should be masked in cryptographic proofs
    for each MCP tool.

    For the book-flight tool:
    - The response contains booking details as a JSON string embedded in MCP response
    - We use hiddenParameters to mask sensitive fields at the REQUEST level
    - This prevents the sensitive data from being sent to the API in the first place

    Returns:
        Dictionary mapping tool names to their ZkfetchToolOptions
    """
    tool_map: ToolOptionsMap = {}

    # book-flight: Passenger booking - redact PII via hiddenParameters
    # This masks passenger_name and passenger_email at the request level
    # preventing them from being sent to the booking API and thus excluded from the proof
    tool_map["book-flight"] = ZkfetchToolOptions(
        public_options=None,
        private_options={
            "hiddenParameters": ["passenger_name", "passenger_email"]
        },
        # No redactions needed - hiddenParameters handles masking at request level
        redactions=[],
    )

    return tool_map


async def call_book_flight_without_redaction(
    session: ClientSession,
    server_url: str,
    zkfetch_url: str,
    passenger_name: str,
    passenger_email: str,
    from_city: str,
    to_city: str,
) -> tuple[Any, Optional[CryptographicProof]]:
    """Call book-flight tool without redaction (all data in proof, no privacy protection)."""
    print("🛫 Calling book-flight WITHOUT redaction...")

    result, proof = await session.call_tool_with_proof(
        name="book-flight",
        arguments={
            "passenger_name": passenger_name,
            "passenger_email": passenger_email,
            "from": from_city,
            "to": to_city,
        },
        server_url=server_url,
        zkfetch_wrapper_url=zkfetch_url,
        # No tool_options_map means no redaction - full data in proof
    )

    return result, proof


async def call_book_flight_with_redaction(
    session: ClientSession,
    server_url: str,
    zkfetch_url: str,
    passenger_name: str,
    passenger_email: str,
    from_city: str,
    to_city: str,
) -> tuple[Any, Optional[CryptographicProof]]:
    """Call book-flight tool with redaction (sensitive data hidden from proof)."""
    print("🔒 Calling book-flight WITH redaction...")

    # Get tool options for redaction
    tool_options_map = build_tool_options_map()

    result, proof = await session.call_tool_with_proof(
        name="book-flight",
        arguments={
            "passenger_name": passenger_name,
            "passenger_email": passenger_email,
            "from": from_city,
            "to": to_city,
        },
        server_url=server_url,
        zkfetch_wrapper_url=zkfetch_url,
        tool_options_map=tool_options_map,
    )

    return result, proof


async def main():
    """Main example function."""
    # Configuration - adjust these URLs based on your setup
    server_url = os.getenv("AGENT_B_URL", "https://dev.agentb.zeroproofai.com")  # Agent B MCP server
    zkfetch_url = os.getenv("ZKFETCH_URL", "https://dev.zktls.zeroproofai.com")  # zkfetch-wrapper

    # Booking details
    passenger_name = "John Doe"
    passenger_email = "john.doe@example.com"
    from_city = "NYC"
    to_city = "LAX"

    print("🚀 Proof-Enabled MCP Client Example")
    print(f"Server URL: {server_url}")
    print(f"zkfetch URL: {zkfetch_url}")
    print()

    try:
        # Create simple MCP client
        client = SimpleMCPClient(f"{server_url}/mcp", zkfetch_url)

        # Initialize MCP session
        print("🔗 Initializing MCP session...")
        init_result = await client.initialize()
        print("✅ MCP session initialized")
        print(f"   Protocol: {init_result['result']['protocolVersion']}")
        print(f"   Server: {init_result['result']['serverInfo']['name']}")
        print()

        # Use case 1: Without redaction
        print("📋 Use Case 1: Book Flight WITHOUT Redaction")
        print("-" * 50)
        result1, proof1 = await call_book_flight_without_redaction(
            client, server_url, zkfetch_url, passenger_name, passenger_email, from_city, to_city
        )

        print("Result:", json.dumps(result1.content[0].text if result1.content else "No content", indent=2))
        print("Proof collected:", proof1 is not None)
        if proof1:
            print("Proof verified:", proof1.verified)
            print("On-chain compatible:", proof1.onchain_compatible)
            print("Proof ID:", proof1.proof_id)
            print("Proof Summary:")
            print(f"  - Provider: {proof1.proof.get('claimData', {}).get('provider')}")
            print(f"  - Identifier: {proof1.proof.get('identifier')}")
            print(f"  - Witnesses: {len(proof1.proof.get('witnesses', []))} witness(es)")
            
            # Print onchainProof
            onchain_proof = proof1.proof.get('onchainProof')
            if onchain_proof:
                print("On-chain Proof:")
                print(json.dumps(onchain_proof, indent=2))
            
            # Print extracted parameter values for readability
            extracted = proof1.proof.get('extractedParameterValues', {}).get('data', '{}')
            if isinstance(extracted, str):
                try:
                    extracted_data = json.loads(extracted)
                    print("Extracted Data from Proof:")
                    print(json.dumps(extracted_data, indent=2))
                except:
                    pass
        print()

        # Use case 2: With redaction
        print("🔐 Use Case 2: Book Flight WITH Redaction")
        print("-" * 50)
        result2, proof2 = await call_book_flight_with_redaction(
            client, server_url, zkfetch_url, passenger_name, passenger_email, from_city, to_city
        )

        print("Result:", json.dumps(result2.content[0].text if result2.content else "No content", indent=2))
        print("Proof collected:", proof2 is not None)
        if proof2:
            print("Proof verified:", proof2.verified)
            print("On-chain compatible:", proof2.onchain_compatible)
            print("Proof ID:", proof2.proof_id)
            print("Proof Summary:")
            print(f"  - Provider: {proof2.proof.get('claimData', {}).get('provider')}")
            print(f"  - Identifier: {proof2.proof.get('identifier')}")
            print(f"  - Witnesses: {len(proof2.proof.get('witnesses', []))} witness(es)")
            
            # Print onchainProof
            onchain_proof = proof2.proof.get('onchainProof')
            if onchain_proof:
                print("On-chain Proof:")
                print(json.dumps(onchain_proof, indent=2))
            
            # Print extracted parameter values for readability
            extracted = proof2.proof.get('extractedParameterValues', {}).get('data', '{}')
            if isinstance(extracted, str):
                try:
                    extracted_data = json.loads(extracted)
                    # print("Extracted Data from Proof (WITH REDACTION):")
                    # print(json.dumps(extracted_data, indent=2))
                except:
                    pass
            print("Redaction applied: Passenger PII hidden from proof")
        print()

        print("✅ Example completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())