"""
Main entry point for the Immobiliensuche Pro Python actor.
Handles Apify actor execution with nodriver-based scraping.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from main import main

if __name__ == "__main__":
    asyncio.run(main())