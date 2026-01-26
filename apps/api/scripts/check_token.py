import asyncio
import sys
from pathlib import Path
import os

# Add apps/api to path explicitly
api_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(api_path))

from app.config import get_settings
from notion_client import AsyncClient

async def check():
    settings = get_settings()
    token = settings.notion_token
    print(f"Token loaded from env: {'Yes' if token else 'No'}")
    if token:
        print(f"Token length: {len(token)}")
        print(f"Token prefix: {token[:4]}...")
        print(f"Token suffix: ...{token[-4:]}")
        
        # Check for extra quotes or spaces
        if token.startswith('"') or token.startswith("'"):
            print("⚠️  WARNING: Token starts with a quote!")
        if token.endswith('"') or token.endswith("'"):
            print("⚠️  WARNING: Token ends with a quote!")
        if " " in token:
            print("⚠️  WARNING: Token contains spaces!")
        
        client = AsyncClient(auth=token)
        try:
            me = await client.users.me()
            print("✅ Token is valid! User:", me.get('name'))
        except Exception as e:
            print(f"❌ Token validation failed: {e}")

if __name__ == "__main__":
    asyncio.run(check())
