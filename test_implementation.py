#!/usr/bin/env python3
"""
Test script for the nodriver-based ImmobilienScout24 scraper.
"""

import asyncio
import json
import logging
from typing import Dict, Any

# Test input configuration
TEST_INPUT: Dict[str, Any] = {
    "searchUrls": [
        {
            "url": "https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-mieten?price=0-1500&livingspace=50-&numberofrooms=2-&radius=10"
        }
    ],
    "maxResults": 20,
    "trackingMode": False,
    "dedupeLevel": "cross_portal",
    "concurrency": 1,
    "proxyCountry": "DE",
    "complianceMode": True,
    "debug": True,
    "headless": False  # Set to False for testing to see what's happening
}

async def test_scraper():
    """Test the scraper implementation."""
    print("🧪 Starting nodriver scraper test")

    try:
        # Import our modules
        from src.types_def import ActorInput
        from src.crawler import ImmobilienScout24Crawler

        # Validate input
        input_data = ActorInput(**TEST_INPUT)
        print(f"✅ Input validation passed: {input_data.dict()}")

        # Test crawler initialization
        crawler = ImmobilienScout24Crawler(
            headless=input_data.headless,
            debug=input_data.debug,
            concurrency=input_data.concurrency,
            proxy_country=input_data.proxyCountry
        )

        print("🔄 Testing crawler...")

        async with crawler:
            # Test homepage access
            print("🏠 Testing homepage access...")
            await crawler.tab.get(crawler.BASE_URL)
            await asyncio.sleep(3)

            title = await crawler.tab.evaluate("document.title")
            print(f"📄 Homepage title: {title}")

            # Test search URL scraping
            if input_data.searchUrls:
                search_url = input_data.searchUrls[0].url
                print(f"🔍 Testing search URL: {search_url}")

                listings = await crawler.scrape_search_url(search_url)
                print(f"📊 Extracted {len(listings)} listings")

                if listings:
                    # Show first listing as example
                    first_listing = listings[0]
                    print(f"📋 Sample listing:")
                    print(f"   Title: {first_listing.title}")
                    print(f"   Price: {first_listing.price.total if first_listing.price else 'N/A'}")
                    print(f"   Size: {first_listing.size.livingSqm if first_listing.size else 'N/A'} m²")
                    print(f"   Rooms: {first_listing.rooms or 'N/A'}")
                    print(f"   URL: {first_listing.url}")

                return listings

    except Exception as error:
        print(f"❌ Test failed: {error}")
        import traceback
        traceback.print_exc()
        return None

async def test_basic_browser():
    """Test basic nodriver functionality."""
    print("🌐 Testing basic nodriver browser functionality...")

    try:
        import nodriver as uc

        browser = await uc.start(headless=False)
        tab = await browser.get('https://www.immobilienscout24.de')

        await asyncio.sleep(5)

        title = await tab.evaluate("document.title")
        print(f"📄 Page title: {title}")

        await browser.stop()
        print("✅ Basic browser test passed")
        return True

    except Exception as error:
        print(f"❌ Basic browser test failed: {error}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)

    print("🚀 Starting nodriver implementation tests")

    # Test basic browser first
    basic_result = asyncio.run(test_basic_browser())

    if basic_result:
        print("\n" + "="*50)
        # Test full scraper
        result = asyncio.run(test_scraper())

        if result:
            print(f"✅ Test completed successfully with {len(result)} listings")
        else:
            print("❌ Test failed")
    else:
        print("❌ Basic browser test failed, skipping scraper test")