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
from typing import Dict, Any, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.proxy_fetch import ZkfetchToolOptions, ToolOptionsMap
from mcp.shared.proof import CryptographicProof


def build_tool_options_map() -> ToolOptionsMap:
    """Build a map of tool-specific redaction rules for privacy-preserving proofs.

    This defines which sensitive fields should be masked in cryptographic proofs
    for each MCP tool. The redaction rules use JSON path notation.

    Returns:
        Dictionary mapping tool names to their ZkfetchToolOptions
    """
    tool_map: ToolOptionsMap = {}

    # book-flight: Passenger booking - redact PII
    # Reveals ONLY: booking_id, confirmation_code, status
    # Hides: passenger_name, passenger_email, and other details
    tool_map["book-flight"] = ZkfetchToolOptions(
        public_options=None,
        # Use private_options to hide sensitive request body from proof
        # This keeps passenger PII out of the on-chain proof
        private_options={
            "hiddenParameters": ["passenger_name", "passenger_email"]
        },
        # Select ONLY the fields we want to reveal - everything else is redacted
        redactions=[
            {"jsonPath": "$.data.booking_id"},
            {"jsonPath": "$.data.confirmation_code"},
            {"jsonPath": "$.data.status"},
        ],
        response_redaction_paths={
            "booking_id": "$.data.booking_id"
        },
    )

    return tool_map


async def call_book_flight_without_redaction(
    session: ClientSession,
    server_url: str,
    passenger_name: str,
    passenger_email: str,
    from_city: str,
    to_city: str,
) -> tuple[Any, Optional[CryptographicProof]]:
    """Call book-flight tool without redaction (all data in proof)."""
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
        # No zkfetch_wrapper_url means no proof collection
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

    # Create HTTP client for MCP transport
    async with httpx.AsyncClient() as http_client:
        try:
            # Connect to MCP server
            print("🔗 Connecting to MCP server...")
            async with streamable_http_client(
                url=f"{server_url}/mcp",
                http_client=http_client,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    print("✅ Connected to MCP server")
                    await session.initialize()
                    print("✅ Session initialized")
                    print()

                    # Use case 1: Without redaction
                    print("📋 Use Case 1: Book Flight WITHOUT Redaction")
                    print("-" * 50)
                    result1, proof1 = await call_book_flight_without_redaction(
                        session, server_url, passenger_name, passenger_email, from_city, to_city
                    )

                    print("Result:", json.dumps(result1.content[0].text if result1.content else "No content", indent=2))
                    print("Proof collected:", proof1 is not None)
                    if proof1:
                        print("Proof verified:", proof1.verified)
                        print("On-chain compatible:", proof1.onchain_compatible)
                    print()

                    # Use case 2: With redaction
                    print("🔐 Use Case 2: Book Flight WITH Redaction")
                    print("-" * 50)
                    result2, proof2 = await call_book_flight_with_redaction(
                        session, server_url, zkfetch_url, passenger_name, passenger_email, from_city, to_city
                    )

                    print("Result:", json.dumps(result2.content[0].text if result2.content else "No content", indent=2))
                    print("Proof collected:", proof2 is not None)
                    if proof2:
                        print("Proof verified:", proof2.verified)
                        print("On-chain compatible:", proof2.onchain_compatible)
                        print("Redaction applied: Passenger PII hidden from proof")
                    print()

                    print("✅ Example completed successfully!")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())