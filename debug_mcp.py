import httpx
import asyncio
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger("mcp_debug")

async def check_mcp():
    url = "http://127.0.0.1:3003/mcp"
    auth_token = "local_mcp_auth_token_12345"
    
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2024-11-05"
    }
    
    init_request = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "debug-client",
                "version": "1.0.0"
            }
        }
    }
    
    print(f"Connecting to {url}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, headers=headers, json=init_request)
            print(f"Status: {response.status_code}")
            print(f"Headers: {response.headers}")
            print(f"Content: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_mcp())
