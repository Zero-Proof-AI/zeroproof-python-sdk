"""
Proof submission and storage module
Handles cryptographic proof submission to attestation services and databases
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

import httpx


@dataclass
class RedactionMetadata:
    """Metadata tracking which fields were redacted from a proof"""
    redacted_field_count: int = 0
    redacted_paths: List[str] = field(default_factory=list)
    was_redacted: bool = False


@dataclass
class CryptographicProof:
    """Cryptographic proof record for tool calls"""
    tool_name: str
    timestamp: int
    request: Dict[str, Any]
    response: Dict[str, Any]
    proof: Dict[str, Any]  # zkfetch proof
    proof_id: Optional[str] = None
    verified: bool = False
    onchain_compatible: bool = False

    # Display version of response with sensitive fields redacted
    display_response: Optional[Dict[str, Any]] = None

    # Metadata about which fields were redacted
    redaction_metadata: Optional[RedactionMetadata] = None


async def send_proof_to_ui(
    crypto_proof: CryptographicProof,
    attestation_config: Optional[Any],  # AttestationConfig
    session_id: str,
    state: Any,  # BookingState
    progress_tx: Optional[Any],  # tokio::sync::mpsc::Sender<String>
) -> None:
    """Collect and send cryptographic proof to UI via progress channel

    This function:
    - Pushes the proof to BookingState's cryptographic_traces
    - Builds a JSON message with all metadata
    - Adds workflow_stage and submitted_by from attestation config
    - Sends it to the UI via the progress channel with __PROOF__ prefix
    """
    state.cryptographic_traces.append(crypto_proof)
    print(f"[PROOF] Collected proof for {crypto_proof.tool_name}: {len(state.cryptographic_traces)}")

    # Send proof to UI via progress channel with all available metadata
    if progress_tx:
        proof_msg = {
            "tool_name": crypto_proof.tool_name,
            "timestamp": crypto_proof.timestamp,
            "verified": crypto_proof.verified,
            "onchain_compatible": crypto_proof.onchain_compatible,
            "proof_id": f"{session_id}_{crypto_proof.timestamp}",
            "request": crypto_proof.request,
            "response": crypto_proof.response,
            "proof": crypto_proof.proof,
            "session_id": session_id,
        }

        # Add workflow_stage and submitted_by from attestation config
        if attestation_config:
            if hasattr(attestation_config, 'workflow_stage') and attestation_config.workflow_stage:
                proof_msg["workflow_stage"] = attestation_config.workflow_stage
            if hasattr(attestation_config, 'submitted_by'):
                proof_msg["submitted_by"] = attestation_config.submitted_by

        # Send via progress channel (this would need to be adapted for Python async)
        # await progress_tx.send(f"__PROOF__{json.dumps(proof_msg)}")

    # Proof submission is now handled automatically by ProxyFetch via attestation_config


async def submit_proof(
    client: httpx.AsyncClient,
    attestation_service_url: str,
    session_id: str,
    proof: CryptographicProof,
    workflow_stage: Optional[str],
    submitted_by: str,
) -> str:
    """Submit a proof to zk-attestation-service for independent verification"""
    submit_url = f"{attestation_service_url}/proofs/submit"

    payload = {
        "session_id": session_id,
        "tool_name": proof.tool_name,
        "timestamp": proof.timestamp,
        "request": proof.request,
        "response": proof.response,
        "proof": proof.proof,
        "verified": proof.verified,
        "onchain_compatible": proof.onchain_compatible,
        "submitted_by": submitted_by,
        "workflow_stage": workflow_stage or "general",
        "display_response": proof.display_response,
        "redaction_metadata": proof.redaction_metadata.__dict__ if proof.redaction_metadata else None,
    }

    try:
        response = await client.post(submit_url, json=payload)
    except Exception as e:
        print(f"[PROOF] Error sending request to {submit_url}: {e}")
        print(f"[PROOF] Error details: {str(e)}")
        # Check for specific error types if needed
        raise Exception(f"Failed to send request to attestation service: {e}")

    if not response.is_success:
        status = response.status_code
        try:
            error_text = response.text
        except:
            error_text = "<could not read response body>"
        print(f"[PROOF] Attestation service returned error status: {status}")
        print(f"[PROOF] Response body: {error_text}")
        raise Exception(f"Failed to submit proof: HTTP {status} - {error_text}")

    result = response.json()

    if "proof_id" in result and isinstance(result["proof_id"], str):
        proof_id = result["proof_id"]
        print(f"[PROOF] ✓ Proof submitted to attestation service: {proof_id}")
        return proof_id
    else:
        raise Exception("No proof_id in response from attestation service")