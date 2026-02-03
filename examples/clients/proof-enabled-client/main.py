#!/usr/bin/env python3
"""Proof-enabled MCP client example demonstrating call_tool_with_proof.

This example shows how to use the MCP client's call_tool_with_proof method
to call tools with cryptographic proof collection and attestation service submission.
It demonstrates two use cases:

1. Without redaction: All data is included in the proof
2. With redaction: Sensitive data is hidden from the proof

The example uses session.call_tool_with_proof() from the SDK which automatically:
- Routes through zkfetch-wrapper for proof generation
- Applies redaction rules if tool_options_map is provided
- Submits proofs to attestation service if attestation_config is provided

The example calls the "book-flight" tool from an Agent B MCP server.
"""

import asyncio
import json
import os
import sys
import uuid
from typing import Dict, Any, Optional

# Add the SDK src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.proxy_fetch import (
    ZkfetchToolOptions, 
    ToolOptionsMap, 
    AttestationConfig
)
from mcp.shared.proof import CryptographicProof



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
    attestation_config: Optional[AttestationConfig],
    passenger_name: str,
    passenger_email: str,
    from_city: str,
    to_city: str,
) -> tuple[Any, Optional[CryptographicProof]]:
    """Call book-flight tool without redaction (all data in proof, no privacy protection)."""
    print("🛫 Calling book-flight WITHOUT redaction...")
    print(f"   Server URL: {server_url}")
    print(f"   Zkfetch URL: {zkfetch_url}")
    print(f"   Request arguments: passenger_name={passenger_name}, passenger_email={passenger_email}, from={from_city}, to={to_city}")

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
        attestation_config=attestation_config,
        # No tool_options_map means no redaction - full data in proof
    )

    return result, proof


async def call_book_flight_with_redaction(
    session: ClientSession,
    server_url: str,
    zkfetch_url: str,
    attestation_config: Optional[AttestationConfig],
    passenger_name: str,
    passenger_email: str,
    from_city: str,
    to_city: str,
) -> tuple[Any, Optional[CryptographicProof]]:
    """Call book-flight tool with redaction (sensitive data hidden from proof)."""
    print("🔒 Calling book-flight WITH redaction...")
    print(f"   Server URL: {server_url}")
    print(f"   Zkfetch URL: {zkfetch_url}")
    print(f"   Request arguments: passenger_name={passenger_name}, passenger_email={passenger_email}, from={from_city}, to={to_city}")

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
        attestation_config=attestation_config,
        tool_options_map=tool_options_map,
    )

    return result, proof


async def main():
    """Main example function."""
    # Configuration - adjust these URLs based on your setup
    server_url = os.getenv("AGENT_B_URL", "https://dev.agentb.zeroproofai.com/mcp")  # Agent B MCP endpoint
    zkfetch_url = os.getenv("ZKFETCH_URL", "https://dev.zktls.zeroproofai.com")  # zkfetch-wrapper
    attestation_url = os.getenv("ATTESTATION_URL", "https://dev.attester.zeroproofai.com")  # Attestation service

    # Booking details
    passenger_name = "John Doe"
    passenger_email = "john.doe@example.com"
    from_city = "NYC"
    to_city = "LAX"

    print("🚀 Proof-Enabled MCP Client Example")
    print(f"Server URL: {server_url}")
    print(f"zkfetch URL: {zkfetch_url}")
    print(f"Attestation URL: {attestation_url}")
    print()

    try:
        # Create a session using the HTTP client
        async with streamable_http_client(server_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                print("🔗 MCP session created")
                print()

                # Create attestation config for proof submission
                # Set enabled=True to automatically submit proofs to the attestation service
                attestation_config = AttestationConfig(
                    service_url=attestation_url,
                    enabled=True,  # Enable automatic proof submission
                    workflow_stage="booking",  # Workflow stage for context
                    session_id=str(uuid.uuid4()),  # Unique session identifier
                    submitted_by="proof-enabled-client",  # Client identifier
                )

                print(f"📝 Attestation config created:")
                print(f"   Service: {attestation_config.service_url}")
                print(f"   Enabled: {attestation_config.enabled}")
                print(f"   Workflow Stage: {attestation_config.workflow_stage}")
                print(f"   Session ID: {attestation_config.session_id}")
                print()

                # Use case 1: Without redaction
                print("📋 Use Case 1: Book Flight WITHOUT Redaction")
                print("-" * 50)
                try:
                    result1, proof1 = await call_book_flight_without_redaction(
                        session, server_url, zkfetch_url, attestation_config,
                        passenger_name, passenger_email, from_city, to_city
                    )

                    if result1:
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
                        
                        # Print extracted parameter values for readability
                        extracted_data = proof1.proof.get('extractedParameterValues', {})
                        if extracted_data:
                            print("Extracted Data from Proof:")
                            print(json.dumps(extracted_data, indent=2))
                except Exception as e:
                    print(f"⚠️  Use Case 1 failed: {str(e)[:200]}")
                    print("   (This is expected if zkfetch-wrapper or Agent B server is not available)")
                print()

                # Use case 2: With redaction
                print("🔐 Use Case 2: Book Flight WITH Redaction")
                print("-" * 50)
                try:
                    result2, proof2 = await call_book_flight_with_redaction(
                        session, server_url, zkfetch_url, attestation_config,
                        passenger_name, passenger_email, from_city, to_city
                    )

                    if result2:
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
                        
                        # Print extracted parameter values for readability
                        extracted_data = proof2.proof.get('extractedParameterValues', {})
                        if extracted_data:
                            print("Extracted Data from Proof (WITH REDACTION):")
                            print(json.dumps(extracted_data, indent=2))
                except Exception as e:
                    print(f"⚠️  Use Case 2 failed: {str(e)[:200]}")
                    print("   (This is expected if zkfetch-wrapper or Agent B server is not available)")
                print()

                print("✅ Example completed successfully!")
                print("\nNote: Proofs have been submitted to the attestation service (if enabled and configured).")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())