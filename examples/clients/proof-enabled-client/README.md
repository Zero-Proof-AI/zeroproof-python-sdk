# Proof-Enabled MCP Client Example

This example demonstrates how to use the MCP client's `call_tool_with_proof` method to call tools with cryptographic proof collection. It shows two use cases for calling the "book-flight" tool from an Agent B MCP server:

## Use Cases

### 1. Without Redaction
- Calls the tool normally without proof collection
- All data remains visible (no privacy protection)

### 2. With Redaction
- Calls the tool through zkfetch-wrapper for proof generation
- Sensitive passenger information (name, email) is hidden from the cryptographic proof
- Only reveals booking confirmation details (booking_id, confirmation_code, status)

## Prerequisites

1. **Agent B MCP Server**: Running on `https://dev.agentb.zeroproofai.com` (configurable via `AGENT_B_URL`)
2. **zkfetch-wrapper**: Running on `https://dev.zktls.zeroproofai.com` (configurable via `ZKFETCH_URL`)

## Running the Example

### Option 1: Install SDK in Development Mode (Recommended)

```bash
# From the SDK root directory
cd /home/revolution/zeroproof-python-sdk
pip install -e .

# Then run the example from anywhere
cd examples/clients/proof-enabled-client
python3 main.py
```

### Option 2: Set PYTHONPATH Explicitly

```bash
cd /home/revolution/zeroproof-python-sdk/examples/clients/proof-enabled-client
PYTHONPATH=/home/revolution/zeroproof-python-sdk/src:$PYTHONPATH python3 main.py
```

**Note**: The first option is preferred because it installs the local SDK as an editable package, eliminating the need to set `PYTHONPATH` for every command.

## Configuration

Set environment variables to configure server URLs:

```bash
export AGENT_B_URL="http://your-agent-b-server:port"
export ZKFETCH_URL="http://your-zkfetch-wrapper:port"
```

## Redaction Rules

The example uses tool-specific redaction rules defined in `build_tool_options_map()`:

- **Hidden Parameters**: `passenger_name`, `passenger_email` are kept private
  - These parameters are extracted from the request body and converted to `paramValues`
  - Replaced with placeholders in the actual request (e.g., `{passenger_name}`)
- **Revealed Fields**: Only `booking_id`, `confirmation_code`, and `status` appear in the proof
- **Privacy Protection**: Passenger PII is excluded from on-chain verification

## How Redaction Works

When `hiddenParameters` is specified in the tool options:

1. **Extraction**: Hidden parameters are extracted from the request body/URL before sending to the API
2. **Placeholder Replacement**: Original values are replaced with placeholders (e.g., `{passenger_name}`)
3. **paramValues Storage**: Extracted values are stored in `privateOptions.paramValues`
4. **Proof Generation**: The zkfetch-wrapper generates a proof with placeholders, hiding the actual sensitive values
5. **Verification**: The proof proves these parameters *existed* without revealing their values

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

## Output

The example will show:
- Tool call results for both use cases (with and without redaction)
- Whether cryptographic proofs were collected
- Proof verification status and on-chain compatibility
- Comparison of request bodies before/after redaction:
  - **Without redaction**: Full PII visible (e.g., `"passenger_name": "John Doe"`)
  - **With redaction**: Placeholders used (e.g., `"passenger_name": "{passenger_name}"`)
- Extracted proof data demonstrating selective disclosure
- Verification that redaction is effective in hiding sensitive information

## Integration

This example shows how to integrate proof-enabled tool calls into MCP client applications, enabling privacy-preserving blockchain interactions while maintaining full MCP protocol compatibility.