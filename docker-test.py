#!/usr/bin/env python3
"""
Simple test to verify nodriver works in Docker environment.
"""

import asyncio
import sys

print(f"🐍 Python version: {sys.version}")

try:
    import nodriver as uc
    print("✅ nodriver imported successfully")
except Exception as e:
    print(f"❌ Failed to import nodriver: {e}")
    sys.exit(1)

async def test_nodriver():
    """Test basic nodriver functionality."""
    try:
        print("🌐 Starting nodriver browser...")
        browser = await uc.start(headless=True)

        print("📄 Creating new tab...")
        tab = await browser.get('https://httpbin.org/get')

        await asyncio.sleep(2)

        title = await tab.evaluate("document.title")
        print(f"📄 Page title: {title}")

        await browser.stop()
        print("✅ nodriver test passed")
        return True

    except Exception as e:
        print(f"❌ nodriver test failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_nodriver())
    if result:
        print("🎉 All tests passed!")
    else:
        print("💥 Tests failed!")
        sys.exit(1)