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

```bash
cd /home/revolution/zeroproof-python-sdk/examples/clients/proof-enabled-client
python main.py
```

## Configuration

Set environment variables to configure server URLs:

```bash
export AGENT_B_URL="http://your-agent-b-server:port"
export ZKFETCH_URL="http://your-zkfetch-wrapper:port"
```

## Redaction Rules

The example uses tool-specific redaction rules defined in `build_tool_options_map()`:

- **Hidden Parameters**: `passenger_name`, `passenger_email` are kept private
- **Revealed Fields**: Only `booking_id`, `confirmation_code`, and `status` appear in the proof
- **Privacy Protection**: Passenger PII is excluded from on-chain verification

## Output

The example will show:
- Tool call results for both use cases
- Whether cryptographic proofs were collected
- Proof verification status and on-chain compatibility
- Demonstration of redaction effectiveness

## Integration

This example shows how to integrate proof-enabled tool calls into MCP client applications, enabling privacy-preserving blockchain interactions while maintaining full MCP protocol compatibility.