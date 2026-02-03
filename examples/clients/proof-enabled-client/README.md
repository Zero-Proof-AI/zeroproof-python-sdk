# Python SDK Examples - Proof-Enabled MCP Client

This folder aims to provide simple examples of using the Python SDK. Please refer to the
[servers repository](https://github.com/modelcontextprotocol/servers)
for real-world servers.

## Proof-Enabled MCP Client Example

This example demonstrates how to use the MCP client's `session.call_tool_with_proof()` method to call tools with cryptographic proof collection and optional attestation service submission.

## Features

- **Proof Generation**: Automatically generates cryptographic proofs for tool calls via zkfetch-wrapper
- **Privacy-Preserving**: Supports redaction rules to mask sensitive data from proofs
- **Attestation Service Integration**: Optional automatic proof submission to attestation service
- **Two Use Cases**:
  1. **Without Redaction**: All request/response data included in the proof
  2. **With Redaction**: Sensitive fields (e.g., PII) hidden from the proof

## Prerequisites

1. **Agent B MCP Server**: Running on `https://dev.agentb.zeroproofai.com` (configurable via `AGENT_B_URL`)
2. **zkfetch-wrapper**: Running on `https://dev.zktls.zeroproofai.com` (configurable via `ZKFETCH_URL`)
3. **Attestation Service** (Optional): Running on `http://localhost:3001` (configurable via `ATTESTATION_URL`)

## Running the Example

### Option 1: Install SDK in Development Mode (Recommended)

```bash
# From the SDK root directory
cd /home/revolution/zeroproof-python-sdk
pip install -e .

# Then run the example
cd examples/clients/proof-enabled-client
python3 main.py
```

### Option 2: Set PYTHONPATH Explicitly

```bash
cd /home/revolution/zeroproof-python-sdk/examples/clients/proof-enabled-client
PYTHONPATH=/home/revolution/zeroproof-python-sdk/src:$PYTHONPATH python3 main.py
```

## Configuration

Set environment variables to configure server URLs:

```bash
export AGENT_B_URL="http://your-agent-b-server:port"
export ZKFETCH_URL="http://your-zkfetch-wrapper:port"
export ATTESTATION_URL="http://your-attestation-service:port"
```

## Key Components

### AttestationConfig
Configures proof submission behavior:
- `service_url`: Attestation service endpoint (e.g., `http://localhost:3001`)
- `enabled`: Enable/disable automatic proof submission (default: `True`)
- `workflow_stage`: Optional workflow context (e.g., "booking", "payment")
- `session_id`: Unique identifier for grouping related proofs
- `submitted_by`: Client identifier for attribution

### ZkfetchToolOptions
Defines per-tool redaction rules:
- `hiddenParameters`: Request fields to mask from the proof
- `redactions`: Response field redaction rules

## Redaction Rules

The example uses tool-specific redaction rules defined in `build_tool_options_map()`:

- **Hidden Parameters**: `passenger_name`, `passenger_email` are kept private
- **Placeholder Replacement**: Original values are replaced with placeholders (e.g., `{passenger_name}`)
- **Privacy Protection**: Passenger PII is excluded from proofs and attestation service storage

### How Redaction Works

When `hiddenParameters` is specified in the tool options:

1. **Extraction**: Hidden parameters are extracted from the request body before sending to the API
2. **Placeholder Replacement**: Original values are replaced with placeholders (e.g., `{passenger_name}`)
3. **paramValues Storage**: Extracted values are stored in `privateOptions.paramValues`
4. **Proof Generation**: The zkfetch-wrapper generates a proof with placeholders, hiding actual sensitive values
5. **Attestation Submission**: Proofs are submitted to attestation service (if enabled) without sensitive data

Example transformation:
```json
// Before redaction
{
  "passenger_name": "John Doe",
  "passenger_email": "john@example.com"
}

// After redaction (sent to API)
{
  "passenger_name": "{passenger_name}",
  "passenger_email": "{passenger_email}"
}

// In privateOptions
{
  "paramValues": {
    "passenger_name": "John Doe",
    "passenger_email": "john@example.com"
  }
}
```

## Code Example

```python
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
from mcp.shared.proxy_fetch import AttestationConfig, ZkfetchToolOptions

async with streamable_http_client(server_url) as (read_stream, write_stream):
    async with ClientSession(read_stream, write_stream) as session:
        # Configure attestation service submission
        attestation_config = AttestationConfig(
            service_url="http://localhost:3001",
            enabled=True,
            workflow_stage="booking",
            session_id=str(uuid.uuid4()),
            submitted_by="my-client"
        )
        
        # Configure redaction rules
        tool_options_map = {
            "book-flight": ZkfetchToolOptions(
                public_options=None,
                private_options={"hiddenParameters": ["passenger_name", "passenger_email"]},
                redactions=[]
            )
        }
        
        # Call tool with proof and attestation
        result, proof = await session.call_tool_with_proof(
            name="book-flight",
            arguments={
                "passenger_name": "John Doe",
                "passenger_email": "john@example.com",
                "from": "NYC",
                "to": "LAX"
            },
            server_url=server_url,
            zkfetch_wrapper_url=zkfetch_url,
            attestation_config=attestation_config,
            tool_options_map=tool_options_map,
        )
        
        # Process results
        if proof:
            print(f"Proof generated and submitted to attestation service")
            print(f"Proof ID: {proof.proof_id}")
```

## Output

The example will show:
- Tool call results for both use cases (with and without redaction)
- Proof verification status and on-chain compatibility
- Attestation service configuration and submission status
- Comparison of request data before/after redaction
- Extracted proof data demonstrating selective disclosure
- Verification that redaction effectively hides sensitive information

## Proof Structure

The cryptographic proofs generated by zkfetch-wrapper contain the following structure:

### CryptographicProof Object

The `CryptographicProof` returned by `session.call_tool_with_proof()` includes:

```python
{
    "tool_name": "book-flight",
    "timestamp": 1770154188,
    "request": {"passenger_name": "John Doe", ...},
    "response": "<booking_json_string>",
    "proof": {
        # Reclaim Protocol proof structure:
        "claimData": {
            "context": "{...}",  # Extraction context with regex patterns
            "epoch": 1,
            "identifier": "0xd63a86202ff56639055899ef98a4a363cca98a0aa36b277f366c61324122188c",
            "owner": "0x6202d6e4b1c98f4e7e22d7b969dec142aa282ec6",
            "parameters": "{...}",  # Request parameters including URL, method, headers
            "provider": "http",  # Data source provider
            "timestampS": 1770154188
        },
        "extractedParameterValues": {
            "title": "Wake up to WonderWidgets!"  # Extracted data from HTTP response
        },
        "identifier": "0xd63a86202ff56639055899ef98a4a363cca98a0aa36b277f366c61324122188c",
        "signatures": ["0x..."],  # Cryptographic signatures
        "witnesses": [
            {
                "id": "0x244897572368eadf65bfbc5aec98d8e5443a9072",
                "url": "wss://attestor.reclaimprotocol.org:444/ws"
            }
        ]
    },
    "verified": true,  # Proof verification status
    "onchain_compatible": true,  # Whether proof can be verified on-chain
    "proof_id": "<attestation_service_id>"  # ID from attestation service (if submitted)
}
```

### Key Proof Fields

- **claimData**: Contains the HTTP request/response context
  - `provider`: The data source (e.g., "http" for HTTP requests)
  - `identifier`: Unique claim identifier
  - `parameters`: Complete request details (URL, method, headers, body)
  - `timestampS`: Unix timestamp of the proof generation
  - `context`: Extraction context with JSON paths and regex patterns

- **extractedParameterValues**: Data extracted from the HTTP response using regex patterns
  - Contains values matched by the extraction rules defined in ZkfetchToolOptions
  - Example: `{"title": "Wake up to WonderWidgets!"}` from httpbin.org/json response

- **signatures**: Cryptographic signatures from Reclaim protocol witnesses
  - Used to verify proof authenticity and integrity

- **witnesses**: Attestors that verified the proof
  - Default witness: `wss://attestor.reclaimprotocol.org:444/ws`

### Proof Verification

The proof object provides verification status through:

```python
proof.verified  # Boolean - whether proof signatures are valid
proof.onchain_compatible  # Boolean - whether proof can be verified on Ethereum
```

### Extracting Proof Data

Access extracted parameters from the proof:

```python
if proof:
    # Get extracted values from the HTTP response
    extracted_data = proof.proof.get('extractedParameterValues', {})
    
    # Get proof metadata
    provider = proof.proof.get('claimData', {}).get('provider')
    identifier = proof.proof.get('identifier')
    witnesses = proof.proof.get('witnesses', [])
    
    # Check attestation submission
    if proof.proof_id:
        print(f"Proof submitted to attestation service: {proof.proof_id}")
```

### With Redaction

When redaction is enabled, sensitive fields are replaced with placeholders before proof generation:

```python
# Before redaction (in proof context)
"passenger_name": "{passenger_name}"  # Placeholder instead of "John Doe"

# But the extracted data remains unchanged
"extractedParameterValues": {
    "title": "Wake up to WonderWidgets!"  # Only non-redacted extracted data
}
```

## Integration

This example shows how to integrate proof-enabled tool calls with attestation service submission into MCP client applications, enabling privacy-preserving blockchain interactions while maintaining full MCP protocol compatibility.