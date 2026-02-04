# Proof-Enabled Proxy MCP Server

This example demonstrates how to build an MCP server that acts as a **proxy** for other MCP servers or HTTPS endpoints, collecting **cryptographic proofs** of the interactions.

## Overview

The Proof-Enabled Proxy Server shows:
- ✅ How to use `ProxyFetch` within an MCP server
- ✅ Routing requests through zkfetch-wrapper for proof collection
- ✅ Calling other MCP servers with proof generation
- ✅ Applying redaction rules to protect sensitive data
- ✅ Returning both results and proof metadata to clients

## Architecture

```
MCP Client
    ↓
[Proof-Enabled Proxy Server]
    ↓ (ProxyFetch)
[zkfetch-wrapper]
    ↓
[Target MCP Server] or [HTTPS Endpoint]
    ↓ (with proof)
[attestation service (optional)]
```

## Key Features

### 1. **Proof Collection Without Client Libraries**
Instead of clients needing to import `ProxyFetch`, the proxy server handles all proof collection:
```python
# Clients just call tools normally via MCP
result = book_flight_with_proof(
    passenger_name="Alice",
    passenger_email="alice@example.com",
    from_city="NYC",
    to_city="LAX"
)
```

### 2. **Flexible Redaction**
Control what data appears in proofs:
```python
# With redaction - sensitive fields hidden
result = book_flight_with_proof_and_redaction(
    passenger_name="Alice",  # Redacted in proof
    passenger_email="alice@example.com",  # Redacted in proof
    from_city="NYC",
    to_city="LA"
)

# Without redaction - all data in proof
result = book_flight_with_proof(
    passenger_name="Alice",  # Visible in proof
    passenger_email="alice@example.com",  # Visible in proof
    from_city="NYC",
    to_city="LA"
)
```

### 3. **HTTPS Endpoint Calls with Proof**
Make direct calls to any HTTPS endpoint with extraction and redaction:
```python
result = fetch_with_proof(
    url="https://api.example.com/data",
    redact_options_json='{"public_options":null,"private_options":{"responseMatches":[...]},"redactions":[...]}'
)
```



## Configuration

Configure via environment variables:

```bash
# zkfetch-wrapper URL (for proof collection)
export ZKFETCH_URL=https://dev.zktls.zeroproofai.com

# Target MCP server to proxy to
export TARGET_MCP_URL=https://dev.agentb.zeroproofai.com/mcp

# Server port
export PORT=3000
```

## Usage Examples

### Example 1: Book Flight with Proof

```bash
# Start the proxy server
python proof_enabled_proxy.py

# In another terminal, test via curl using MCP JSON-RPC protocol:
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"tools/call",
    "params":{
      "name":"book_flight_with_proof",
      "arguments":{
        "passenger_name":"Alice Johnson",
        "passenger_email":"alice@example.com",
        "from_city":"NYC",
        "to_city":"LAX"
      }
    }
  }' | jq .

# Response includes:
# {
#   "result": {
#     "confirmation_number": "ABC123",
#     "status": "booked",
#     "price": "$299"
#   },
#   "proof": {
#     "collected": true,
#     "verified": true,
#     "onchain_compatible": true,
#     "identifier": "0x123..."
#   }
# }
```

### Example 2: Call with Redaction

```bash
# Test via curl with MCP JSON-RPC:
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":2,
    "method":"tools/call",
    "params":{
      "name":"book_flight_with_proof_and_redaction",
      "arguments":{
        "passenger_name":"Bob Smith",
        "passenger_email":"bob@example.com",
        "from_city":"SFO",
        "to_city":"NYC"
      }
    }
  }' | jq .

# Response proof shows:
# {
#   "proof": {
#     "collected": true,
#     "verified": true,
#     "onchain_compatible": true,
#     # Passenger name and email are REDACTED in actual proof
#   }
# }
```

### Example 3: Advanced HTTPS Fetch with ProxyFetch

This demonstrates direct usage of `ProxyFetch` for HTTPS endpoints with extraction and redaction:

```bash
# Test via curl with extraction and redaction options:
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"fetch_with_proof",
      "arguments":{
        "url":"https://httpbin.org/json",
        "redact_options_json":"{\"public_options\":null,\"private_options\":{\"responseMatches\":[{\"type\":\"regex\",\"value\":\"\\\"title\\\":\\\\s*\\\"(?<title>[^\\\"]+)\\\"\"}]},\"redactions\":[{\"jsonPath\":\"$.slideshow\"}]}"
      }
    }
  }' | jq .

# Response includes:
# {
#   "status": "success",
#   "result": { /* full API response */ },
#   "extracted_data": {
#       "title": "Wake up to WonderWidgets!"
#   },
#   "proof": {
#       "collected": true,
#       "verified": true,
#       "onchain_compatible": true,
#       "identifier": "0x...",
#       "extracted_parameter_values": {
#           "title": "Wake up to WonderWidgets!"
#       }
#   }
# }
```

**Key Parameters:**
- `url`: HTTPS endpoint to fetch from
- `redact_options_json`: JSON string with `ZkfetchToolOptions` structure (NOT wrapped in a tool_options_map):
  - `public_options`: Public request settings (method, timeout, etc.)
  - `private_options`: Private options including:
    - `responseMatches`: Regex patterns for data extraction with named groups
    - `hiddenParameters`: Parameters to hide from proof
  - `redactions`: JSON paths to redact from proof

#### CRITICAL: Using `default_zk_options` for GET Requests

When calling HTTPS endpoints with the `get()` method (which passes `body=None`):
- The `_extract_tool_name(body)` returns `None` because there's no request body
- Tool name extraction fails because there's no request body to parse
- The `_resolve_tool_options()` method cannot look up tools in `tool_options_map` without a tool name
- **Solution: Use `default_zk_options` instead of `tool_options_map` in ProxyConfig**

```python
# ✅ CORRECT: Use default_zk_options for GET requests
config = ProxyConfig(
    url=ZKFETCH_URL,
    proxy_type="zkfetch",
    tool_options_map=None,  # Not applicable for GET requests with no body
    default_zk_options=zk_tool_options,  # Use this instead!
    debug=True,
)

proxy_fetch = ProxyFetch(config)
response = await proxy_fetch.get(url)  # body=None → uses default_zk_options

# ❌ WRONG: Using tool_options_map for GET requests won't work
# because there's no tool_name to look it up
config = ProxyConfig(
    url=ZKFETCH_URL,
    proxy_type="zkfetch",
    tool_options_map={"some-tool": zk_tool_options},  # Won't be found!
    default_zk_options=None,
)
```

**Why this matters:**
1. MCP tool calls (POST with body) → `tool_options_map` (tool name in request body)
2. Direct HTTPS calls (GET/no body) → `default_zk_options` (no tool name available)

The `_resolve_tool_options(tool_name=None)` method falls back to `default_zk_options` when tool_name is None, which is exactly what happens with GET requests.

**Key insight: Verifiers can see the extracted title in the proof, proving it exists in the API response, but cannot see the rest of the slideshow data (redacted).**

---

## Architecture: ProxyConfig Patterns for Different Request Types

The `ProxyConfig` class supports two distinct patterns for different request scenarios:

### Pattern 1: MCP Tool Calls (with `tool_options_map`)
Used when calling other MCP servers with tool calls that include tool names in the request body.

**How it works:**
1. MCP client sends `tools/call` request with tool name and arguments
2. Server extracts tool name from request body
3. `_extract_tool_name(body)` returns the tool name (e.g., "book-flight")
4. `_resolve_tool_options(tool_name)` looks up configuration in `tool_options_map`
5. Proof generation uses the matched tool's configuration

```python
# Example: Calling another MCP server with tool-specific redaction
config = ProxyConfig(
    url=ZKFETCH_URL,
    proxy_type="zkfetch",
    tool_options_map={
        "book-flight": ZkfetchToolOptions(
            redactions=[
                {"jsonPath": "$.passenger_name"},
                {"jsonPath": "$.passenger_email"}
            ]
        ),
        "search-flights": ZkfetchToolOptions(
            redactions=[]  # No redaction for search
        ),
    },
    default_zk_options=None,  # Not needed for MCP calls
)
```

### Pattern 2: Direct HTTPS Calls (with `default_zk_options`)
Used when making direct HTTP/HTTPS requests (GET, PUT, DELETE) that have no request body.

**How it works:**
1. Client makes direct HTTP call (e.g., `proxy_fetch.get(url)`)
2. HTTP method doesn't include a request body (body=None)
3. `_extract_tool_name(None)` returns None (no tool name in body)
4. `_resolve_tool_options(None)` falls back to `default_zk_options`
5. Proof generation uses the default configuration

```python
# Example: Direct HTTPS call with extraction and redaction
config = ProxyConfig(
    url=ZKFETCH_URL,
    proxy_type="zkfetch",
    tool_options_map=None,  # Won't be used for GET requests
    default_zk_options=ZkfetchToolOptions(
        public_options=None,
        private_options={
            "responseMatches": [
                {"type": "regex", "value": '"title": "(?<title>[^"]+)"'}
            ]
        },
        redactions=[
            {"jsonPath": "$.slideshow"}  # Redact the full slideshow
        ]
    ),
)

proxy_fetch = ProxyFetch(config)
response = await proxy_fetch.get(url)  # body=None → uses default_zk_options
```

### Why Both Patterns Exist

| Request Type | Body Available? | Tool Name Available? | Use This Config |
|-------------|-----------------|----------------------|-----------------|
| MCP `tools/call` | Yes | Yes (in JSON-RPC) | `tool_options_map` |
| POST with tool name | Yes | Yes (in body) | `tool_options_map` |
| GET/PUT/DELETE | No | No | `default_zk_options` |
| Direct HTTPS calls | No | No | `default_zk_options` |

The `_resolve_tool_options()` method implements this pattern:
```
If tool_name is provided:
  → Look it up in tool_options_map
  → Return the specific configuration
Else (tool_name is None):
  → Return default_zk_options
  → This handles direct HTTPS calls
```

---

All tools return a `ProxiedResult` with this structure:

```python
{
    "result": {
        # ... actual tool result from remote server
    },
    "proof": {
        "collected": bool,  # Whether a proof was collected
        "verified": bool,   # Whether proof verification succeeded
        "onchain_compatible": bool,  # Whether proof is compatible with blockchain
        "identifier": str   # Proof identifier/hash
    }
}
```

## Proof Details

When `proof.collected` is `true`, the proof contains:

- **claimInfo**: The Reclaim protocol claim metadata
  - ID, context, redaction hash, etc.
- **signedClaim**: Cryptographic signature from the witness
- **onchainProof**: Additional on-chain verification data

The full proof structure follows the Reclaim Protocol specification and is compatible with blockchain verification.

## Redaction Behavior

When redaction is applied:
- Specified fields are hashed instead of included plaintext
- The proof still proves those fields existed
- The actual values cannot be extracted from the proof
- Useful for PII: emails, names, phone numbers, etc.

## Use Cases

### 1. **Chaining MCP Servers**
Create a network of MCP servers where one acts as a gateway collecting proofs of interactions between them.

### 2. **Privacy-Preserving APIs**
Call third-party APIs through this proxy to:
- Collect cryptographic evidence of the interaction
- Protect sensitive data with redaction
- Enable audit trails with verifiable proofs

### 3. **Blockchain Integration**
Submit proofs to blockchain for:
- Smart contract verification
- DeFi applications requiring proof of API calls
- Oracle-like functionality with cryptographic guarantees

### 4. **Compliance & Auditing**
Generate immutable records of API interactions with:
- Cryptographic verification
- Optional selective data redaction
- Blockchain-submittable proofs

## Implementation Details

### ProxyFetch Integration

```python
from mcp.shared.proxy_fetch import ProxyConfig, ProxyFetch, ZkfetchToolOptions

# Create configuration
config = ProxyConfig(
    url="https://dev.zktls.zeroproofai.com",
    proxy_type="zkfetch",
    tool_options_map={
        "tool-name": ZkfetchToolOptions(
            public_options=None,
            private_options={
                "hiddenParameters": ["sensitive_field1", "sensitive_field2"]
            },
            redactions=[],
        )
    },
    attestation_config=None,  # Optional: submit proofs to attestation service
)

# Use it
proxy_fetch = ProxyFetch(config)
response = proxy_fetch.post("https://dev.agentb.zeroproofai.com/mcp", request)
```

### MCP Endpoint Detection

The proxy automatically detects MCP endpoints (ending in `/mcp`) and formats requests accordingly:

```python
if TARGET_MCP_SERVER.endswith("/mcp"):
    # Format as MCP JSON-RPC
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }
else:
    # Format as REST
    request = {"name": tool_name, **arguments}
```

## Testing

To test this server with the example MCP server:

```bash
# Terminal 1: Start this proxy server
python proof_enabled_proxy.py
# Server runs on http://localhost:3000

# Terminal 2: Create an MCP client that calls this server's tools
# (Use the SDK client examples or write your own)
```

## Advanced Configuration

### Using Custom Redaction Options

For `fetch_with_proof`, pass `redact_options_json` as a JSON string containing `ZkfetchToolOptions`:

```python
# Example with extraction and redaction
redact_options = {
    "public_options": None,
    "private_options": {
        "responseMatches": [
            {
                "type": "regex",
                "value": r'"title":\s*"(?<title>[^"]+)"'  # Named group captures
            }
        ]
    },
    "redactions": [
        {"jsonPath": "$.slideshow"},  # Redact entire slideshow
        {"jsonPath": "$.author"}      # Redact author field
    ]
}

result = fetch_with_proof(
    url="https://httpbin.org/json",
    redact_options_json=json.dumps(redact_options)
)

# Proof includes:
# - extracted_parameter_values: {"title": "Wake up to WonderWidgets!"}
# - All data under $.slideshow and $.author is redacted
```

The actual parameters supported are:

- **public_options**: Public request settings (currently null in most cases)
- **private_options**: Private extraction/redaction options:
  - `responseMatches`: Array of regex patterns with named capture groups
  - `hiddenParameters`: List of parameters to mark as private
- **redactions**: Array of JSON paths to exclude from responses


## Related Examples

- **[Proof-Enabled Client](../clients/proof-enabled-client/)**: Client-side proof generation
- **[Weather Structured](./weather_structured.py)**: MCP server with structured outputs
- **[Simple Echo](./simple_echo.py)**: Basic MCP server pattern

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client                               │
└────────────────────────┬────────────────────────────────────┘
                         │ book_flight_with_proof()
                         │ book_flight_with_proof_and_redaction()
                         │ fetch_with_proof()
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         Proof-Enabled Proxy Server (this example)           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ • Receives tool calls from clients                   │   │
│  │ • Manages ProxyFetch configuration                   │   │
│  │ • Routes through zkfetch-wrapper                     │   │
│  │ • Applies redaction rules                            │   │
│  │ • Returns proof + result to client                   │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ POST request
                         │ (via ProxyFetch)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              zkfetch-wrapper (Proxy Service)                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ • Intercepts HTTP/HTTPS calls                        │   │
│  │ • Generates cryptographic proofs                     │   │
│  │ • Applies redaction transformations                  │   │
│  │ • Returns proof + original response                  │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ Proxied request
                         ▼
┌─────────────────────────────────────────────────────────────┐
│            Target Service (MCP Server or HTTPS)             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ • Processes request normally                         │   │
│  │ • Returns response                                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

Optional:
                         │ Submit proof
                         ▼
        ┌──────────────────────────────┐
        │  Attestation Service (opt.)  │
        │  • Stores proof              │
        │  • Enables verification      │
        └──────────────────────────────┘
```

## Troubleshooting

### "Proof not collected"
- Check zkfetch-wrapper URL is accessible
- Verify TARGET_MCP_URL is correct
- Check network connectivity to target server

### "Invalid JSON in arguments"
- Ensure `arguments_json` is valid JSON string
- Use double quotes for JSON strings

### "Redaction not working"
- Verify field names match exactly in `redacted_fields`
- Check ProxyFetch configuration is correct
- Confirm tool_options_map includes the tool

## References

- [Reclaim Protocol](https://reclaimprotocol.org) - Underlying ZK proof system
- [ProxyFetch Documentation](../../docs/proxy-fetch.md)
- [ZkfetchToolOptions Reference](../../src/mcp/shared/proxy_fetch.py)
- [PR #1: Proof-Enabled Client](https://github.com/Zero-Proof-AI/zeroproof-python-sdk/pull/1)
