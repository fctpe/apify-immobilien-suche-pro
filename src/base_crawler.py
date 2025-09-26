"""
Abstract base class for portal crawlers.
Provides common anti-detection and browser management functionality.
"""

import asyncio
import logging
import os
import random
import subprocess
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

import nodriver as uc
from nodriver import Tab, Browser

from types_def import PropertyListing, SearchBuilder
from utils import get_user_agents


class BasePortalCrawler(ABC):
    """Abstract base class for real estate portal crawlers."""

    def __init__(
        self,
        headless: bool = True,
        debug: bool = False,
        concurrency: int = 1,
        proxy_country: str = 'DE'
    ):
        self.headless = headless
        self.debug = debug
        self.concurrency = concurrency
        self.proxy_country = proxy_country
        self.logger = logging.getLogger(self.__class__.__name__)

        self.browser: Optional[Browser] = None
        self.tab: Optional[Tab] = None
        self.session_cookies: Dict[str, Any] = {}
        self.xvfb_process = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    async def initialize(self) -> None:
        """Initialize the browser with enhanced anti-detection."""
        self.logger.info("🚀 Initializing browser with anti-detection")

        try:
            # Detect if running on Apify platform or as root (Docker)
            is_apify = os.environ.get('APIFY_IS_AT_HOME') == '1'
            is_root = hasattr(os, 'getuid') and os.getuid() == 0
            needs_no_sandbox = is_apify or is_root

            if needs_no_sandbox:
                self.logger.info("🐳 Running on Apify platform or as root - using virtual display")
                await self._start_virtual_display()

                # Enhanced browser arguments for stealth
                browser_args = [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-default-apps',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-sync',
                    '--disable-translate',
                    '--hide-scrollbars',
                    '--metrics-recording-only',
                    '--mute-audio',
                    '--no-first-run',
                    '--safebrowsing-disable-auto-update',
                    '--ignore-certificate-errors',
                    '--ignore-ssl-errors',
                    '--ignore-certificate-errors-spki-list',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    f'--user-agent={self._get_random_user_agent()}',
                ]

                self.browser = await uc.start(
                    headless=self.headless,
                    browser_args=browser_args
                )
            else:
                # Local development - simpler setup
                self.logger.info("💻 Running locally - standard browser setup")
                self.browser = await uc.start(
                    headless=self.headless,
                    user_data_dir=None,
                    browser_args=[
                        '--disable-blink-features=AutomationControlled',
                        f'--user-agent={self._get_random_user_agent()}',
                    ]
                )

            # Get the main tab
            self.tab = await self.browser.get_tab()

            # Enhanced stealth measures
            await self._apply_stealth_measures()

            self.logger.info("✅ Browser initialized successfully")

        except Exception as error:
            self.logger.error(f"❌ Browser initialization failed: {error}")
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        """Clean up browser and virtual display resources."""
        try:
            if self.browser:
                self.logger.info("🧹 Cleaning up browser")
                await self.browser.stop()
                self.browser = None
                self.tab = None

            # Clean up virtual display
            if self.xvfb_process:
                self.logger.info("🖥️ Stopping virtual display")
                self.xvfb_process.terminate()
                try:
                    self.xvfb_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.xvfb_process.kill()
                    self.xvfb_process.wait()
                self.xvfb_process = None

        except Exception as error:
            self.logger.warning(f"⚠️ Cleanup warning: {error}")

    async def _start_virtual_display(self) -> None:
        """Start virtual display for headless environment."""
        try:
            # Only start if not already running
            if not os.environ.get('DISPLAY'):
                self.logger.info("🖥️ Starting virtual display")
                self.xvfb_process = subprocess.Popen([
                    'Xvfb', ':99', '-screen', '0', '1920x1080x24', '-nolisten', 'tcp'
                ])
                os.environ['DISPLAY'] = ':99'
                await asyncio.sleep(2)  # Give Xvfb time to start
        except Exception as error:
            self.logger.warning(f"⚠️ Virtual display setup failed: {error}")

    def _get_random_user_agent(self) -> str:
        """Get a random user agent string."""
        user_agents = get_user_agents()
        return random.choice(user_agents)

    async def _apply_stealth_measures(self) -> None:
        """Apply browser stealth measures to avoid detection."""
        try:
            # Remove webdriver property
            await self.tab.evaluate('''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
            ''')

            # Modify plugins array
            await self.tab.evaluate('''
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            ''')

            # Add languages
            await self.tab.evaluate('''
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['de-DE', 'de', 'en-US', 'en']
                });
            ''')

            self.logger.debug("🥷 Stealth measures applied")

        except Exception as error:
            self.logger.debug(f"Stealth measures warning: {error}")

    async def _handle_cookie_consent(self) -> None:
        """Handle cookie consent dialogs."""
        try:
            # Wait for potential cookie banner
            await asyncio.sleep(2)

            # Common selectors for German real estate sites
            consent_selectors = [
                '[data-testid="cookie-accept"]',
                '[data-cy="cookie-accept"]',
                'button[data-accept-all]',
                '.cookie-accept',
                '.cookies-accept',
                'button:contains("Alle akzeptieren")',
                'button:contains("Akzeptieren")',
                'button:contains("Accept")',
                '#cookie-accept',
                '.consent-accept'
            ]

            for selector in consent_selectors:
                try:
                    button = await self.tab.select(selector, timeout=2)
                    if button:
                        self.logger.info(f"🍪 Clicking cookie consent: {selector}")
                        await button.click()
                        await asyncio.sleep(1)
                        return
                except Exception:
                    continue

            self.logger.debug("No cookie consent dialog found")

        except Exception as error:
            self.logger.debug(f"Cookie consent handling: {error}")

    async def _human_like_wait(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Wait for a random human-like duration."""
        wait_time = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(wait_time)

    async def _simulate_human_scroll(self) -> None:
        """Simulate human-like scrolling behavior."""
        try:
            # Random scroll down
            scroll_distance = random.randint(300, 800)
            await self.tab.scroll_down(scroll_distance)
            await self._human_like_wait(0.5, 1.5)

            # Small scroll back up
            scroll_back = random.randint(50, 150)
            await self.tab.scroll_up(scroll_back)
            await self._human_like_wait(0.5, 1.0)

        except Exception as error:
            self.logger.debug(f"Scroll simulation: {error}")

    async def _take_debug_screenshot(self, filename: str) -> None:
        """Take a screenshot for debugging purposes if debug mode is enabled."""
        if self.debug and self.tab:
            try:
                await self.tab.save_screenshot(filename)
                self.logger.debug(f"📸 Debug screenshot saved: {filename}")
            except Exception as e:
                self.logger.debug(f"Failed to take screenshot {filename}: {e}")

    @abstractmethod
    async def build_search_url(self, builder: SearchBuilder) -> str:
        """Build search URL from SearchBuilder configuration."""
        pass

    @abstractmethod
    async def scrape_search_url(self, url: str, max_results: int = None) -> List[PropertyListing]:
        """Scrape listings from a search URL."""
        pass

    @abstractmethod
    async def scrape_search_builder(self, builder: SearchBuilder, max_results: int = None) -> List[PropertyListing]:
        """Scrape listings using search builder configuration."""
        pass

    @abstractmethod
    async def _extract_search_results(self, max_results: int = None) -> List[PropertyListing]:
        """Extract property URLs from search page and then scrape each detail page."""
        pass

    @abstractmethod
    async def _scrape_property_detail(self, url: str, index: int = 1) -> Optional[PropertyListing]:
        """Navigate to property detail page and extract comprehensive data."""
        pass