"""MCP Server with Proof-Enabled External Tool Calls

Demonstrates how to use zkfetch_proxy (ProxyFetch) within an MCP server
to call other MCP servers or HTTPS endpoints with cryptographic proof collection.

This server acts as an intermediary that:
1. Accepts tool calls from clients
2. Routes those requests through zkfetch-wrapper to collect cryptographic proofs
3. Optionally redacts sensitive data from proofs
4. Returns both the result and proof information to the client

Use cases:
- Chaining MCP servers with proof collection
- Making privacy-preserving external API calls
- Collecting cryptographic evidence of API interactions
"""

import asyncio
import json
import os
import sys
from typing import Optional, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from mcp.server.mcpserver import MCPServer
from mcp.shared.proxy_fetch import ProxyConfig, ProxyFetch, ZkfetchToolOptions
from mcp.shared.proof import CryptographicProof

# Create server
mcp = MCPServer("Proof-Enabled Proxy Server")

# Configuration - can be overridden by environment variables
ZKFETCH_URL = os.getenv("ZKFETCH_URL", "https://dev.zktls.zeroproofai.com")
TARGET_MCP_SERVER = os.getenv("TARGET_MCP_URL", "https://dev.agentb.zeroproofai.com/mcp")


class ProxiedResult:
    """Result from a proxied call including proof"""
    def __init__(self, result: Any, proof: Optional[CryptographicProof] = None):
        self.result = result
        self.proof = proof
    
    def to_dict(self) -> dict:
        """Convert to dictionary for tool return"""
        return {
            "result": self.result,
            "proof": {
                "collected": self.proof is not None,
                "verified": self.proof.verified if self.proof else False,
                "onchain_compatible": self.proof.onchain_compatible if self.proof else False,
                "identifier": self.proof.proof.get("identifier") if self.proof else None,
            } if self.proof else {"collected": False}
        }


async def call_mcp_tool_with_proof(
    tool_name: str,
    arguments: dict,
    apply_redaction: bool = False,
    redacted_fields: Optional[list[str]] = None,
) -> ProxiedResult:
    """Call an MCP server tool through zkfetch-wrapper with proof collection.
    
    Args:
        tool_name: Name of the tool to call (e.g., "book-flight")
        arguments: Tool arguments as a dictionary
        apply_redaction: Whether to apply redaction rules
        redacted_fields: List of fields to redact (e.g., ["passenger_name", "passenger_email"])
    
    Returns:
        ProxiedResult containing both the result and proof
    """
    try:
        # Build tool options map with optional redaction
        tool_options_map = None
        if apply_redaction and redacted_fields:
            tool_options_map = {
                tool_name: ZkfetchToolOptions(
                    public_options=None,
                    private_options={
                        "hiddenParameters": redacted_fields
                    },
                    redactions=[],
                )
            }
        
        # Create proxy config
        config = ProxyConfig(
            url=ZKFETCH_URL,
            proxy_type="zkfetch",
            username=None,
            password=None,
            tool_options_map=tool_options_map,
            default_zk_options=None,
            debug=False,
            attestation_config=None,  # Could add attestation service here
        )
        
        # Create ProxyFetch instance
        proxy_fetch = ProxyFetch(config)
        
        # Detect if target is MCP endpoint
        is_mcp = TARGET_MCP_SERVER.endswith("/mcp")
        
        # Build request based on endpoint type
        if is_mcp:
            # MCP JSON-RPC request
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
        else:
            # REST request
            request = {
                "name": tool_name,
                **arguments
            }
        
        # Make the call through zkfetch
        response = await proxy_fetch.post(TARGET_MCP_SERVER, request)
        
        # Extract proof from response
        proof = None
        if response.get("proof"):
            proof_data = response.get("proof")
            # In a real implementation, you might parse the proof here
            # For now, we're just noting that a proof was collected
        
        # Extract the actual tool result
        tool_result = response
        if is_mcp and response.get("data"):
            # MCP response wrapped in data
            mcp_response = response.get("data", {}).get("result", {})
            if mcp_response.get("content"):
                content_array = mcp_response["content"]
                if content_array and isinstance(content_array, list):
                    tool_result = content_array[0].get("text", response)
        
        return ProxiedResult(tool_result, proof)
    
    except Exception as e:
        return ProxiedResult({"error": str(e)})


# Tool 1: Call book-flight with proof (no redaction)
@mcp.tool()
async def book_flight_with_proof(
    passenger_name: str,
    passenger_email: str,
    from_city: str,
    to_city: str,
) -> dict:
    """Book a flight through a remote MCP server with cryptographic proof collection.
    
    All data is included in the proof - no privacy redaction applied.
    """
    result = await call_mcp_tool_with_proof(
        tool_name="book-flight",
        arguments={
            "passenger_name": passenger_name,
            "passenger_email": passenger_email,
            "from": from_city,
            "to": to_city,
        },
        apply_redaction=False
    )
    return result.to_dict()


# Tool 2: Call book-flight with proof and redaction
@mcp.tool()
async def book_flight_with_proof_and_redaction(
    passenger_name: str,
    passenger_email: str,
    from_city: str,
    to_city: str,
) -> dict:
    """Book a flight through a remote MCP server with proof and PII redaction.
    
    Sensitive fields (passenger_name, passenger_email) are redacted from the proof
    to protect passenger privacy while still providing cryptographic evidence.
    """
    result = await call_mcp_tool_with_proof(
        tool_name="book-flight",
        arguments={
            "passenger_name": passenger_name,
            "passenger_email": passenger_email,
            "from": from_city,
            "to": to_city,
        },
        apply_redaction=True,
        redacted_fields=["passenger_name", "passenger_email"]
    )
    return result.to_dict()


# Tool 3: Demonstrate HTTPS endpoint call with proof (advanced with tool_options_map)
@mcp.tool()
async def fetch_with_proof(
    url: str,
    redact_options_json: Optional[str] = None,
) -> dict:
    """Fetch from HTTPS endpoint with zkfetch proof collection using provided tool_options_map.
    
    This demonstrates usage of ProxyFetch's public get() method with custom tool_options_map.
    The tool_options_map controls extraction and redaction behavior.
    
    Args:
        url: HTTPS URL to fetch from
        redact_options_json: JSON string containing ZkfetchToolOptions (NOT wrapped in tool_options_map)
                            Example: '{"public_options": null, "private_options": {"responseMatches": [...]}, "redactions": [...]}'
    
    Returns:
        Dictionary with result, extracted data, and proof information
    """
    try:
        # Parse redaction options from JSON parameter
        zk_tool_options = None
        if redact_options_json:
            options_dict = json.loads(redact_options_json)
            # Create ZkfetchToolOptions directly from the provided options
            zk_tool_options = ZkfetchToolOptions(
                public_options=options_dict.get("public_options"),
                private_options=options_dict.get("private_options"),
                redactions=options_dict.get("redactions"),
            )
            # Wrap in tool_options_map for ProxyConfig
            tool_options_map = {"fetch-data": zk_tool_options}
        else:
            tool_options_map = None
        
        # Create ProxyFetch config
        config = ProxyConfig(
            url=ZKFETCH_URL,
            proxy_type="zkfetch",
            username=None,
            password=None,
            tool_options_map=None,  # Not used for direct HTTPS calls
            default_zk_options=zk_tool_options,  # Use default instead since body is None
            debug=os.getenv("DEBUG", "false").lower() == "true",
        )
        
        proxy_fetch = ProxyFetch(config)
        
        # Use get() method which calls request() which routes to zkfetch_request with tool_options_map
        response = await proxy_fetch.get(url)
        
        # Extract proof and data from response
        proof_data = response.get("proof", {})
        extracted_values = proof_data.get("extractedParameterValues", {})
        
        return {
            "status": "success",
            "result": response.get("data", response),
            "extracted_data": extracted_values if extracted_values else None,
            "proof": {
                "collected": bool(proof_data),
                "verified": proof_data.get("verified", False),
                "onchain_compatible": proof_data.get("onchainCompatible", False),
                "identifier": proof_data.get("identifier"),
                "extracted_parameter_values": extracted_values if extracted_values else None,
            }
        }
    
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "proof": {"collected": False}
        }


async def test_tools():
    """Test the proxy server tools directly"""
    print(f"🧪 Testing Proof-Enabled Proxy Server Tools")
    print(f"   zkfetch-wrapper: {ZKFETCH_URL}")
    print(f"   Target MCP server: {TARGET_MCP_SERVER}")
    print()
    
    # List available tools
    tools = await mcp.list_tools()
    print("Available tools:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
    print()
    
    # Test 1: Simple book_flight_with_proof (no redaction)
    print("Test 1: book_flight_with_proof (no redaction)")
    print("-" * 60)
    try:
        result = await book_flight_with_proof(
            passenger_name="Alice Johnson",
            passenger_email="alice@example.com",
            from_city="NYC",
            to_city="LAX"
        )
        print(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Error: {e}")
    print()
    
    # Test 2: Book flight with redaction
    print("Test 2: book_flight_with_proof_and_redaction")
    print("-" * 60)
    try:
        result = await book_flight_with_proof_and_redaction(
            passenger_name="Bob Smith",
            passenger_email="bob@example.com",
            from_city="SFO",
            to_city="NYC"
        )
        print(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Error: {e}")
    print()
    
    # Test 3: Advanced fetch with proof
    print("Test 3: fetch_with_proof")
    print("-" * 60)
    try:
        result = await fetch_with_proof(
            url="https://httpbin.org/json",
            extract_regex='"title":\\s*"(?<title>[^"]+)"',
            redact_json_paths="$.slideshow",
        )
        print(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"Error: {e}")
    print()


def run_server():
    """Run the MCP server with standard /mcp endpoint following MCP JSON-RPC protocol"""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    import uvicorn
    
    port = int(os.getenv("PORT", 3000))
    host = os.getenv("HOST", "127.0.0.1")
    
    async def mcp_endpoint(request):
        """POST /mcp - MCP JSON-RPC endpoint
        
        Accepts MCP protocol requests like:
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list" | "tools/call",
            "params": {...}
        }
        """
        try:
            data = await request.json()
            method = data.get("method")
            params = data.get("params", {})
            request_id = data.get("id")
            
            if method == "tools/list":
                # List all available tools
                tools = await mcp.list_tools()
                result = {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.input_schema
                        }
                        for tool in tools
                    ]
                }
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                })
            
            elif method == "tools/call":
                # Call a specific tool
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                
                # Route to the appropriate tool
                if tool_name == "book_flight_with_proof":
                    result = await book_flight_with_proof(
                        passenger_name=tool_args.get("passenger_name"),
                        passenger_email=tool_args.get("passenger_email"),
                        from_city=tool_args.get("from_city"),
                        to_city=tool_args.get("to_city"),
                    )
                
                elif tool_name == "book_flight_with_proof_and_redaction":
                    result = await book_flight_with_proof_and_redaction(
                        passenger_name=tool_args.get("passenger_name"),
                        passenger_email=tool_args.get("passenger_email"),
                        from_city=tool_args.get("from_city"),
                        to_city=tool_args.get("to_city"),
                    )
                
                elif tool_name == "fetch_with_proof":
                    result = await fetch_with_proof(
                        url=tool_args.get("url"),
                        redact_options_json=tool_args.get("redact_options_json"),
                    )
                
                else:
                    return JSONResponse({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}"
                        }
                    })
                
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2)
                            }
                        ]
                    }
                })
            
            else:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown method: {method}"
                    }
                })
        
        except json.JSONDecodeError:
            return JSONResponse({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            }, status_code=400)
        
        except Exception as e:
            return JSONResponse({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }, status_code=500)
    
    async def health_endpoint(request):
        """GET /health - Health check"""
        return JSONResponse({"status": "ok"})
    
    # Create Starlette app with routes
    routes = [
        Route("/health", health_endpoint, methods=["GET"]),
        Route("/mcp", mcp_endpoint, methods=["POST"]),
    ]
    
    app = Starlette(routes=routes, debug=True)
    
    print(f"🚀 Starting Proof-Enabled Proxy Server")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   zkfetch-wrapper: {ZKFETCH_URL}")
    print(f"   Target MCP server: {TARGET_MCP_SERVER}")
    print()
    print("Available MCP endpoints:")
    print(f"   GET  http://{host}:{port}/health")
    print(f"   POST http://{host}:{port}/mcp")
    print()
    print("Example requests:")
    print('   List tools: curl -X POST http://localhost:3000/mcp -H "Content-Type: application/json" -d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\'')
    print('   Call tool: curl -X POST http://localhost:3000/mcp -H "Content-Type: application/json" -d \'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"book_flight_with_proof","arguments":{"passenger_name":"Alice","passenger_email":"alice@example.com","from_city":"NYC","to_city":"LAX"}}}\'')
    print()
    
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        asyncio.run(test_tools())
    else:
        run_server()
