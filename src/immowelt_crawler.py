"""
Immowelt crawler using nodriver for enhanced anti-detection.
Implements dynamic location resolution and data extraction.
"""

import asyncio
import json
import logging
import os
import random
import re
import subprocess
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse, parse_qs

import nodriver as uc
from nodriver import Tab, Browser

# Removed base_crawler dependency to match existing pattern
from location_resolver import ImmoweltLocationResolver
from types_def import PropertyListing, SearchBuilder
from utils import (
    extract_price_from_text, extract_area_from_text, extract_rooms_from_text,
    normalize_property_type, normalize_deal_type, clean_html_text, get_user_agents
)


class ImmoweltCrawler:
    """Enhanced Immowelt crawler with dynamic location resolution."""

    BASE_URL = "https://www.immowelt.de"
    SEARCH_BASE = "https://www.immowelt.de/classified-search"

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
        self.logger = logging.getLogger(__name__)

        self.browser: Optional[Browser] = None
        self.tab: Optional[Tab] = None
        self.session_cookies: Dict[str, Any] = {}
        self.xvfb_process = None
        self.location_resolver: Optional[ImmoweltLocationResolver] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    async def initialize(self) -> None:
        """Initialize the browser with enhanced anti-detection."""
        self.logger.info("🚀 Initializing Immowelt crawler with nodriver")

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

            # Get main tab or create new one
            try:
                self.tab = self.browser.main_tab
                if not self.tab:
                    self.logger.debug("No main tab, getting new tab...")
                    self.tab = await self.browser.get('about:blank')
                else:
                    self.logger.debug("Using main tab")
            except Exception as tab_error:
                self.logger.warning(f"Tab acquisition issue: {tab_error}")
                # Try alternative tab acquisition
                self.tab = await self.browser.get('about:blank')

            self.logger.debug("✅ Tab acquired successfully")

            # Test basic functionality
            try:
                test_result = await self.tab.evaluate('() => "test"', return_by_value=True)
                if test_result == "test":
                    self.logger.debug("✅ JavaScript evaluation working")
                else:
                    self.logger.warning(f"⚠️ JavaScript evaluation test failed, got: {test_result}")
            except Exception as eval_error:
                self.logger.warning(f"⚠️ JavaScript evaluation error: {eval_error}")

            # Apply basic stealth measures
            await self._apply_stealth_measures()

            # Initialize location resolver
            self.location_resolver = ImmoweltLocationResolver(self.tab, self.debug)

            # Perform session warm-up to establish natural browsing pattern
            await self._warm_up_session()

            self.logger.info("✅ Immowelt crawler initialized successfully")

        except Exception as error:
            self.logger.error(f"❌ Browser initialization failed: {error}")
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        """Clean up browser and virtual display resources."""
        try:
            if self.browser:
                self.logger.info("🧹 Cleaning up browser resources")
                # nodriver's stop method is not async
                self.browser.stop()
                self.browser = None
                self.tab = None

            # Stop virtual display if running
            await self._stop_virtual_display()

        except Exception as error:
            self.logger.warning(f"⚠️ Cleanup warning: {error}")

    async def _stop_virtual_display(self) -> None:
        """Stop virtual display if running."""
        try:
            if self.xvfb_process:
                self.logger.info("🖥️ Stopping virtual display")
                self.xvfb_process.terminate()
                try:
                    self.xvfb_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.logger.warning("Xvfb did not terminate gracefully, killing process")
                    self.xvfb_process.kill()
                    self.xvfb_process.wait()
                self.xvfb_process = None
        except Exception as error:
            self.logger.warning(f"⚠️ Virtual display cleanup error: {error}")

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
        """Apply comprehensive browser stealth measures to avoid detection."""
        try:
            # Comprehensive stealth script with better fingerprinting
            stealth_script = '''
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                // Set realistic plugins array
                Object.defineProperty(navigator, 'plugins', {
                    get: () => ({
                        length: 3,
                        0: { name: 'Chrome PDF Plugin' },
                        1: { name: 'Chromium PDF Plugin' },
                        2: { name: 'Microsoft Edge PDF Plugin' }
                    })
                });

                // Set proper language preferences for Germany
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['de-DE', 'de', 'en-US', 'en']
                });

                // Set proper timezone
                try {
                    Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {
                        value: function() {
                            return {
                                ...this.constructor.prototype.resolvedOptions.call(this),
                                timeZone: 'Europe/Berlin'
                            };
                        }
                    });
                } catch(e) {}

                // Override Chrome runtime
                if (window.chrome) {
                    Object.defineProperty(window.chrome, 'runtime', {
                        get: () => ({
                            onConnect: null,
                            onMessage: null
                        })
                    });
                }

                // Set realistic screen properties
                Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
                Object.defineProperty(screen, 'availHeight', { get: () => 1040 });
                Object.defineProperty(screen, 'width', { get: () => 1920 });
                Object.defineProperty(screen, 'height', { get: () => 1080 });

                // Set proper permissions
                Object.defineProperty(navigator, 'permissions', {
                    get: () => ({
                        query: () => Promise.resolve({ state: 'granted' })
                    })
                });

                // Hide automation flags
                ['__webdriver_evaluate', '__selenium_evaluate', '__webdriver_script_function',
                 '__webdriver_script_func', '__webdriver_script_fn', '__fxdriver_evaluate',
                 '__driver_unwrapped', '__webdriver_unwrapped', '__driver_evaluate',
                 '__selenium_unwrapped', '__fxdriver_unwrapped'].forEach(prop => {
                    delete window[prop];
                });
            '''

            await self.tab.evaluate(stealth_script)

            # Set proper viewport
            try:
                await self.tab.send('Emulation.setDeviceMetricsOverride', {
                    'width': 1920,
                    'height': 1080,
                    'deviceScaleFactor': 1,
                    'mobile': False
                })
            except Exception as e:
                self.logger.debug(f"Viewport setting failed: {e}")

            # Set geolocation to Germany
            try:
                await self.tab.send('Emulation.setGeolocationOverride', {
                    'latitude': 52.5200,
                    'longitude': 13.4050,
                    'accuracy': 100
                })
            except Exception as e:
                self.logger.debug(f"Geolocation setting failed: {e}")

            # Enable additional stealth features
            try:
                await self.tab.send('Page.addScriptToEvaluateOnNewDocument', {
                    'source': stealth_script
                })
            except Exception as e:
                self.logger.debug(f"Script injection failed: {e}")

            self.logger.debug("🥷 Enhanced stealth measures applied")

        except Exception as error:
            self.logger.debug(f"Stealth measures warning: {error}")

    async def _warm_up_session(self) -> None:
        """Warm up the browser session by visiting homepage first."""
        try:
            self.logger.info("🏠 Warming up session with Immowelt homepage")

            # Navigate to Immowelt homepage first
            await self.tab.get("https://www.immowelt.de")
            await asyncio.sleep(3)

            # Handle cookie consent on homepage
            await self._handle_cookie_consent()

            # Add some human-like interaction
            try:
                # Simulate a small scroll to appear more human-like
                await self.tab.evaluate('''
                    window.scrollTo({
                        top: 200,
                        behavior: 'smooth'
                    });
                ''')
                await asyncio.sleep(random.uniform(1.0, 2.0))

                # Move mouse to simulate user activity
                await self.tab.send("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": random.randint(200, 600),
                    "y": random.randint(200, 400)
                })
                await asyncio.sleep(random.uniform(0.5, 1.0))

            except Exception:
                pass  # Don't fail on interaction simulation

            self.logger.info("✅ Session warmed up successfully")

        except Exception as error:
            self.logger.warning(f"⚠️ Session warm-up failed: {error}, proceeding anyway")

    async def _handle_cookie_consent(self) -> None:
        """Handle cookie consent dialogs."""
        try:
            # Take screenshot before attempting cookie consent
            await self._take_debug_screenshot('before_cookie_consent.png')

            # Wait for potential cookie banner
            await asyncio.sleep(3)

            # Simplified JavaScript approach with timeout
            cookie_handled = False
            try:
                cookie_handled = await asyncio.wait_for(
                    self.tab.evaluate('''
                        (() => {
                            // Look for buttons with OK text first
                            const buttons = document.querySelectorAll('button');
                            for (const btn of buttons) {
                                const text = btn.textContent.trim().toLowerCase();
                                if (text === 'ok' && btn.offsetParent !== null) {
                                    btn.click();
                                    return true;
                                }
                            }
                            return false;
                        })()
                    '''),
                    timeout=10  # 10 second timeout
                )
            except asyncio.TimeoutError:
                self.logger.debug("Cookie consent JavaScript evaluation timed out")
                cookie_handled = False

            if cookie_handled:
                self.logger.info("🍪 ✅ Cookie consent handled via JavaScript")
                await asyncio.sleep(2)
                await self._take_debug_screenshot('after_cookie_consent.png')
                return

            # Fallback: Try simpler CSS selector approach
            simple_selectors = ['button']  # Just try all buttons

            for selector in simple_selectors:
                try:
                    elements = await self.tab.select_all(selector)
                    if elements:
                        for element in elements:
                            try:
                                # Get the text to check if it's the OK button
                                text = await element.get_text()
                                if text and text.strip().upper() == 'OK':
                                    await element.click()
                                    self.logger.info(f"🍪 ✅ Clicked OK button via fallback")
                                    await asyncio.sleep(2)
                                    await self._take_debug_screenshot('after_cookie_consent.png')
                                    return
                            except Exception:
                                continue
                except Exception:
                    continue

            self.logger.debug("No cookie consent dialog found")

        except Exception as error:
            self.logger.debug(f"Cookie consent handling error: {error}")

    async def _human_like_wait(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Wait for a random human-like duration."""
        wait_time = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(wait_time)

    async def _take_debug_screenshot(self, filename: str) -> None:
        """Take a screenshot for debugging purposes if debug mode is enabled."""
        if self.debug and self.tab:
            try:
                await self.tab.save_screenshot(filename)
                self.logger.debug(f"📸 Debug screenshot saved: {filename}")
            except Exception as e:
                self.logger.debug(f"Failed to take screenshot {filename}: {e}")

    async def build_search_url(self, builder: SearchBuilder) -> str:
        """Build Immowelt search URL from SearchBuilder configuration."""
        try:
            # Base URL
            params = []

            # Deal type
            if builder.dealType == 'rent':
                params.append('distributionTypes=Rent')
            else:
                params.append('distributionTypes=Buy')

            # Property types
            if hasattr(builder, 'propertyTypes') and builder.propertyTypes:
                property_types = []
                for prop_type in builder.propertyTypes:
                    if prop_type.lower() == 'apartment':
                        property_types.append('Apartment')
                    elif prop_type.lower() == 'house':
                        property_types.append('House')
                    elif prop_type.lower() == 'commercial':
                        property_types.append('Commercial')
                if property_types:
                    params.append(f"estateTypes={','.join(property_types)}")
            else:
                # Default to apartment and house
                params.append('estateTypes=House,Apartment')

            # Resolve locations dynamically
            if builder.regions:
                location_ids = []
                for region in builder.regions:
                    self.logger.info(f"🏠 Resolving location: {region}")
                    location_id = await self.location_resolver.resolve_location(region)
                    if location_id and location_id != 'unknown':
                        location_ids.append(location_id)
                    else:
                        self.logger.warning(f"⚠️ Could not resolve location: {region}")

                if location_ids:
                    params.append(f"locations={','.join(location_ids)}")
                else:
                    self.logger.warning("⚠️ No valid locations resolved, using default")
                    # Fallback to Berlin
                    params.append('locations=AD08DE8634')
            else:
                # Default location
                params.append('locations=AD08DE8634')

            # Size range
            if builder.sizeMin:
                params.append(f'spaceMin={builder.sizeMin}')
            if hasattr(builder, 'sizeMax') and builder.sizeMax:
                params.append(f'spaceMax={builder.sizeMax}')

            # Price range
            if builder.priceMin:
                params.append(f'priceMin={builder.priceMin}')
            if builder.priceMax:
                params.append(f'priceMax={builder.priceMax}')

            # Rooms
            if builder.roomsMin:
                params.append(f'roomsMin={builder.roomsMin}')
            if hasattr(builder, 'roomsMax') and builder.roomsMax:
                params.append(f'roomsMax={builder.roomsMax}')

            # Sorting - newest listings first
            params.append('order=CreateDate')

            # Combine URL and parameters
            search_url = f"{self.SEARCH_BASE}?{'&'.join(params)}"

            self.logger.info(f"🔗 Built Immowelt search URL: {search_url}")
            return search_url

        except Exception as error:
            self.logger.error(f"❌ Error building Immowelt URL: {error}")
            # Return a basic search URL as fallback
            return f"{self.SEARCH_BASE}?distributionTypes=Rent&estateTypes=House,Apartment&locations=AD08DE8634"

    async def scrape_search_url(self, url: str, max_results: int = None) -> List[PropertyListing]:
        """Scrape listings from a direct search URL."""
        self.logger.info(f"🕷️ Starting Immowelt search scraping: {url}")

        try:
            # Navigate to search URL
            await self.tab.get(url)
            await asyncio.sleep(3)

            # Handle cookie consent
            await self._handle_cookie_consent()
            await asyncio.sleep(2)

            # Check for blocking or CAPTCHA
            if await self._detect_captcha_or_block():
                self.logger.error("❌ Detected blocking or CAPTCHA - cannot proceed")
                return []

            # Take initial screenshot
            await self._take_debug_screenshot('immowelt_search_loaded.png')

            # Extract listings from search results
            listings = await self._extract_search_results(max_results)

            self.logger.info(f"✅ Extracted {len(listings)} listings from Immowelt search")
            return listings

        except Exception as error:
            self.logger.error(f"❌ Error scraping Immowelt search URL: {error}")
            return []

    async def scrape_search_builder(self, builder: SearchBuilder, max_results: int = None) -> List[PropertyListing]:
        """Scrape listings using search builder configuration."""
        try:
            # Build search URL
            search_url = await self.build_search_url(builder)

            # Use the search URL scraper
            return await self.scrape_search_url(search_url, max_results)

        except Exception as error:
            self.logger.error(f"❌ Error with Immowelt search builder: {error}")
            return []

    async def _detect_captcha_or_block(self) -> bool:
        """Detect if we've been blocked or shown a CAPTCHA."""
        try:
            # Check page title and content for blocking indicators
            blocking_result = await self.tab.evaluate('''
                (() => {
                    const title = document.title.toLowerCase();
                    const bodyText = document.body.textContent.toLowerCase();

                    // Check for cookie consent (NOT blocking)
                    if (bodyText.includes('wir benötigen ihre zustimmung') ||
                        bodyText.includes('we need your consent') ||
                        bodyText.includes('cookie') && bodyText.includes('akzeptieren')) {
                        return { blocked: false, reason: 'cookie_consent' };
                    }

                    // Check for real blocking patterns
                    const blockingTitles = ['captcha', 'blocked', 'robot', 'forbidden', 'access denied'];
                    for (const term of blockingTitles) {
                        if (title.includes(term)) {
                            return { blocked: true, reason: `title_${term}` };
                        }
                    }

                    const blockingBodyTerms = [
                        'zugriff verweigert',
                        'access denied',
                        'captcha',
                        'please verify',
                        'sind sie ein roboter',
                        'are you a robot',
                        'cloudflare',
                        'checking your browser',
                        'überprüfung ihres browsers'
                    ];

                    for (const term of blockingBodyTerms) {
                        if (bodyText.includes(term)) {
                            return { blocked: true, reason: `body_${term.replace(' ', '_')}` };
                        }
                    }

                    // Check if page has actual property content
                    const hasPropertyContent = document.querySelector([
                        '[data-testid*="estate"]',
                        '[class*="estate"]',
                        '[class*="property"]',
                        '[class*="expose"]',
                        'h1, h2, h3',
                        '.price',
                        '[class*="price"]'
                    ].join(', '));

                    // If no content and page is very short, might be blocked
                    if (!hasPropertyContent && bodyText.length < 200) {
                        return { blocked: true, reason: 'no_content' };
                    }

                    return { blocked: false, reason: 'ok' };
                })()
            ''')

            if blocking_result and blocking_result.get('blocked'):
                reason = blocking_result.get('reason', 'unknown')
                self.logger.debug(f"🔍 Blocking detected: {reason}")

                # Take screenshot when actually blocked for debugging
                await self._take_debug_screenshot(f'blocked_{reason}.png')
                return True

            return False

        except Exception as error:
            self.logger.debug(f"CAPTCHA detection error: {error}")
            return False

    async def _extract_search_results(self, max_results: int = None) -> List[PropertyListing]:
        """Extract property URLs from search page and scrape detail pages."""
        self.logger.info("📋 Extracting Immowelt property URLs from search results")

        listings = []

        try:
            # Wait for results to load
            await asyncio.sleep(3)

            # Extract property URLs using JavaScript - simplified approach
            property_urls_result = await self.tab.evaluate('''
                (() => {
                    const urls = [];
                    const seenIds = new Set();

                    // Selectors for Immowelt property links
                    const selectors = [
                        'a[href*="/expose/"]',
                        '[data-testid*="listing"] a[href*="/expose/"]',
                        '.estate-list-item a[href*="/expose/"]',
                        '.listing-card a[href*="/expose/"]'
                    ];

                    for (const selector of selectors) {
                        const links = document.querySelectorAll(selector);

                        for (const link of links) {
                            const href = link.href;
                            if (href && href.includes('/expose/')) {
                                // Extract ID from URL
                                const idMatch = href.match(/expose\/([a-f0-9-]+|[a-z0-9]+)/);
                                if (idMatch) {
                                    const id = idMatch[1];
                                    if (!seenIds.has(id)) {
                                        seenIds.add(id);
                                        urls.push(href);
                                    }
                                }
                            }
                        }
                    }

                    return urls;  // Return array directly
                })()
            ''', return_by_value=True)

            # Process the result - handle nodriver's RemoteObject structure
            property_urls = []

            if isinstance(property_urls_result, list):
                property_urls = property_urls_result
            elif hasattr(property_urls_result, 'deep_serialized_value'):
                # Extract from deep_serialized_value
                dsv = property_urls_result.deep_serialized_value
                if hasattr(dsv, 'value') and isinstance(dsv.value, list):
                    for item in dsv.value:
                        if isinstance(item, dict) and item.get('type') == 'string':
                            url = item.get('value')
                            if url:
                                property_urls.append(url)
                elif hasattr(dsv, 'value') and isinstance(dsv.value, dict):
                    # Handle dict format with value list
                    value_list = dsv.value.get('value', [])
                    for item in value_list:
                        if isinstance(item, dict) and item.get('type') == 'string':
                            url = item.get('value')
                            if url:
                                property_urls.append(url)
            else:
                self.logger.warning(f"⚠️ Unexpected result type: {type(property_urls_result)}")
                property_urls = []

            self.logger.info(f"✅ Found {len(property_urls)} Immowelt property URLs")

            if not property_urls:
                self.logger.warning("❌ No property URLs found")
                await self._take_debug_screenshot('immowelt_no_urls_found.png')
                return []

            # Limit results if specified
            if max_results and len(property_urls) > max_results:
                property_urls = property_urls[:max_results]
                self.logger.info(f"🔢 Limited to first {max_results} properties")

            # Extract data from each property detail page
            for index, url in enumerate(property_urls, 1):
                try:
                    self.logger.info(f"🏠 Scraping Immowelt property {index}/{len(property_urls)}: {url}")

                    listing = await self._scrape_property_detail_with_retry(url, index)
                    if listing:
                        listings.append(listing)
                        self.logger.info(f"✅ Successfully extracted listing {index}: {listing.title}")
                    else:
                        # Fallback: try to extract partial data from search results page
                        partial_listing = await self._extract_partial_data_from_search(url, index)
                        if partial_listing:
                            listings.append(partial_listing)
                            self.logger.info(f"📄 Extracted partial listing {index}: {partial_listing.title}")
                        else:
                            self.logger.debug(f"❌ Failed to extract listing from {url}")

                    # Extended delay between requests to avoid triggering rate limits
                    await self._human_like_wait(5.0, 10.0)

                except Exception as error:
                    self.logger.warning(f"❌ Error scraping Immowelt property {index} ({url}): {error}")
                    continue

            self.logger.info(f"✅ Successfully extracted {len(listings)} listings from Immowelt")
            return listings

        except Exception as error:
            self.logger.error(f"❌ Error in Immowelt search results extraction: {error}")
            await self._take_debug_screenshot('immowelt_search_extraction_error.png')
            return []

    async def _scrape_property_detail_with_retry(self, url: str, index: int, max_retries: int = 3) -> Optional[PropertyListing]:
        """Scrape property detail with retry logic and exponential backoff."""
        for attempt in range(max_retries):
            try:
                listing = await self._scrape_property_detail(url, index)
                if listing:
                    return listing

                # If we get None (blocked), implement exponential backoff
                if attempt < max_retries - 1:
                    backoff_delay = min(30.0, 5.0 * (2 ** attempt))  # Cap at 30 seconds
                    self.logger.warning(f"⏳ Property {index} blocked, retrying in {backoff_delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(backoff_delay)

                    # Add extra mouse movement between retries
                    try:
                        await self.tab.send("Input.dispatchMouseEvent", {
                            "type": "mouseMoved",
                            "x": random.randint(100, 1000),
                            "y": random.randint(100, 700)
                        })
                    except Exception:
                        pass

            except Exception as error:
                self.logger.warning(f"❌ Attempt {attempt + 1} failed for property {index}: {error}")
                if attempt < max_retries - 1:
                    backoff_delay = min(30.0, 10.0 * (2 ** attempt))
                    await asyncio.sleep(backoff_delay)

        self.logger.error(f"❌ All {max_retries} attempts failed for property {index}")
        return None

    async def _extract_partial_data_from_search(self, target_url: str, index: int) -> Optional[PropertyListing]:
        """Extract partial data from search results page as fallback when detail page is blocked."""
        try:
            self.logger.debug(f"🔍 Attempting partial extraction for property {index}")

            # Extract partial data from current search results page
            partial_data = await self.tab.evaluate(f'''
                (() => {{
                    const targetUrl = "{target_url}";

                    // Find the listing containing this URL
                    const links = document.querySelectorAll('a[href*="/expose/"]');
                    let targetListing = null;

                    for (const link of links) {{
                        if (link.href === targetUrl) {{
                            // Find the parent listing container
                            let parent = link.parentElement;
                            let attempts = 0;
                            while (parent && attempts < 10) {{
                                if (parent.classList.contains('listitem') ||
                                    parent.classList.contains('listitem_wrap') ||
                                    parent.hasAttribute('data-testid') ||
                                    parent.tagName === 'ARTICLE') {{
                                    targetListing = parent;
                                    break;
                                }}
                                parent = parent.parentElement;
                                attempts++;
                            }}
                            break;
                        }}
                    }}

                    if (!targetListing) return null;

                    // Extract data from the listing
                    const data = {{
                        title: '',
                        price: '',
                        area: '',
                        rooms: '',
                        location: '',
                        sourceId: ''
                    }};

                    // Extract ID from URL
                    const idMatch = targetUrl.match(/expose\/([a-f0-9-]+)/);
                    if (idMatch) {{
                        data.sourceId = idMatch[1];
                    }}

                    // Extract title
                    const titleElement = targetListing.querySelector('h2, h3, .title, [data-test*="title"]');
                    if (titleElement) {{
                        data.title = titleElement.textContent.trim();
                    }}

                    // Extract price
                    const priceElements = targetListing.querySelectorAll('*');
                    for (const el of priceElements) {{
                        const text = el.textContent;
                        if (text && text.match(/\\d+[.,]\\d*\\s*€/)) {{
                            data.price = text.trim();
                            break;
                        }}
                    }}

                    // Extract area (look for m² or qm)
                    for (const el of targetListing.querySelectorAll('*')) {{
                        const text = el.textContent;
                        if (text && text.match(/\\d+[.,]?\\d*\\s*(m²|qm)/i)) {{
                            data.area = text.trim();
                            break;
                        }}
                    }}

                    // Extract rooms (look for "Zimmer" or room count)
                    for (const el of targetListing.querySelectorAll('*')) {{
                        const text = el.textContent;
                        if (text && text.match(/\\d+[.,]?\\d*\\s*(zimmer|room)/i)) {{
                            data.rooms = text.trim();
                            break;
                        }}
                    }}

                    return data;
                }})()
            ''')

            if not partial_data:
                return None

            # Handle the case where partial_data might be a list or dict
            if isinstance(partial_data, list):
                if not partial_data:
                    return None
                partial_data = partial_data[0] if partial_data else {}

            if not isinstance(partial_data, dict) or not partial_data.get('sourceId'):
                return None

            # Create a PropertyListing with partial data
            listing = PropertyListing(
                source='immowelt',
                sourceId=partial_data['sourceId'],
                url=target_url,
                title=partial_data.get('title', 'Immowelt Listing (Partial Data)'),
                dealType='rent',  # Default since we're searching for rentals
                propertyType='apartment',  # Default
                description=f"Partial data extracted from search results (detail page blocked)",
                price=partial_data.get('price'),
                size=self._parse_area(partial_data.get('area')),
                rooms=self._parse_rooms(partial_data.get('rooms')),
                features=['partial_data'],  # Mark as partial
                address=partial_data.get('location')
            )

            return listing

        except Exception as error:
            self.logger.debug(f"❌ Partial extraction failed for property {index}: {error}")
            return None

    def _parse_area(self, area_text: str) -> Optional[float]:
        """Parse area from text like '75 m²' -> 75.0"""
        if not area_text:
            return None

        import re
        match = re.search(r'(\d+[.,]?\d*)', area_text)
        if match:
            try:
                return float(match.group(1).replace(',', '.'))
            except ValueError:
                pass
        return None

    def _parse_rooms(self, rooms_text: str) -> Optional[float]:
        """Parse room count from text like '3 Zimmer' -> 3.0"""
        if not rooms_text:
            return None

        import re
        match = re.search(r'(\d+[.,]?\d*)', rooms_text)
        if match:
            try:
                return float(match.group(1).replace(',', '.'))
            except ValueError:
                pass
        return None

    async def _scrape_property_detail(self, url: str, index: int) -> Optional[PropertyListing]:
        """Navigate to property detail page and extract data."""
        try:
            self.logger.debug(f"🌍 Navigating to Immowelt property: {url}")

            # More human-like navigation with extended delay
            await self._human_like_wait(2.0, 5.0)

            # Set proper referrer header before navigation
            current_url = await self.tab.evaluate('(() => window.location.href)()')
            if current_url:
                self.logger.debug(f"🔗 Setting referrer from: {current_url}")
                # Set user agent and accept language using CDP with correct parameter names
                try:
                    await self.tab.send("Network.setUserAgentOverride", {
                        "userAgent": self._get_random_user_agent(),
                        "acceptLanguage": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"
                    })
                except Exception as e:
                    self.logger.debug(f"Setting user agent failed: {e}")

            # Navigate to the property detail page
            await self.tab.get(url)

            # Extended wait for page to fully load
            await asyncio.sleep(5)

            # Handle cookie consent on property page (it might appear again)
            await self._handle_cookie_consent()

            # Additional human-like mouse movements to mimic real user behavior
            try:
                # Move mouse randomly to simulate user interaction
                await self.tab.send("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": random.randint(100, 800),
                    "y": random.randint(100, 600)
                })
                await asyncio.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass  # Don't fail on mouse movement

            # Check for blocking AFTER handling cookies
            if await self._detect_captcha_or_block():
                self.logger.warning(f"❌ Property {index} blocked or CAPTCHA detected")
                # Screenshot is already taken in _detect_captcha_or_block when blocked
                return None

            # Take debug screenshot of successful property page
            await self._take_debug_screenshot(f'immowelt_property_{index}_success.png')

            # Also log page info for debugging
            try:
                page_info = await self.tab.evaluate('''
                    (() => ({
                        title: document.title,
                        url: window.location.href,
                        bodyLength: document.body.textContent.length,
                        hasContent: !!document.querySelector('h1, h2, h3, .price, [class*="price"]')
                    }))()
                ''')
                self.logger.debug(f"📄 Property {index} page info: {page_info}")
            except Exception:
                pass

            # Extract data from property page
            property_data = await self._extract_property_data(url)

            if not property_data:
                self.logger.warning(f"❌ Could not extract data from property {index}")
                return None

            # Create PropertyListing object using the simplified approach
            return self._create_property_listing(property_data)

        except Exception as error:
            self.logger.error(f"❌ Error scraping Immowelt property detail {url}: {error}")
            return None

    async def _extract_property_data(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract property data from individual property page."""
        try:
            source_id = self._extract_property_id(url)
            if not source_id:
                self.logger.warning(f"⚠️ Could not extract property ID from URL: {url}")
                return None

            self.logger.debug(f"📄 Extracting data from property page: {url}")

            # Extract title from page (we know this works from the debug logs)
            page_title = await self.tab.evaluate('(() => document.title)()')

            if not isinstance(page_title, str):
                self.logger.warning(f"⚠️ Invalid page title type: {type(page_title)}")
                page_title = 'Immowelt Property'

            self.logger.debug(f"📝 Page title: {page_title}")

            # Start with basic data
            processed_data = {
                'sourceId': source_id,
                'title': page_title,
                'dealType': 'rent',  # Default, will be overridden by title parsing
                'propertyType': 'apartment',  # Default, will be overridden by title parsing
                'description': None,
                'address': None,
            }

            # Parse essential data from title string since it's the most reliable source
            # Example title: "Wohnung 67.73 m² 1117.55 € zur Miete Langhansstraße 70,Weißensee,Berlin (13086)"
            title_data = self._parse_title_data(page_title)
            processed_data.update(title_data)

            # Extract posted date from the property page
            try:
                posted_date = await self._extract_posted_date()
                if posted_date:
                    processed_data['postedDate'] = posted_date
                    self.logger.debug(f"📅 Found posted date: {posted_date}")
            except Exception as e:
                self.logger.debug(f"⚠️ Could not extract posted date: {e}")

            self.logger.debug(f"📊 Processed property data: {processed_data}")

            return processed_data

        except Exception as error:
            self.logger.error(f"❌ Failed to extract property data from {url}: {error}")
            import traceback
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
            return None

    def _extract_property_id(self, url: str) -> str:
        """Extract property ID from Immowelt URL."""
        try:
            # Immowelt URLs: https://www.immowelt.de/expose/de622d4d-bf13-4734-813e-3e587ea4f896
            match = re.search(r'/expose/([a-f0-9-]+)', url)
            if match:
                return match.group(1)

            # Fallback: use the last part of the path
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            if path_parts:
                return path_parts[-1]

            return 'unknown'

        except Exception:
            return 'unknown'

    def _parse_title_data(self, title: str) -> Dict[str, Any]:
        """Parse essential data from the property title.

        Example title: "Wohnung 67.73 m² 1117.55 € zur Miete Langhansstraße 70,Weißensee,Berlin (13086)"
        """
        data = {}

        if not title or not isinstance(title, str):
            return data

        self.logger.debug(f"🔍 Parsing title: {title}")

        # Extract price (e.g., "1117.55 €" or "1.117,55 €")
        price_match = re.search(r'([0-9.,]+)\s*€', title)
        if price_match:
            try:
                price_str = price_match.group(1)

                # Handle German number format (1.117,55 or 1117,55 or 1117.55)
                if ',' in price_str and '.' in price_str:
                    # Format: 1.117,55 (German thousands separator with decimal comma)
                    price_str = price_str.replace('.', '').replace(',', '.')
                elif ',' in price_str:
                    # Format: 1117,55 (German decimal comma)
                    price_str = price_str.replace(',', '.')
                # else: Format: 1117.55 (English decimal point) - keep as is

                data['price'] = float(price_str)
                self.logger.debug(f"💰 Found price: {data['price']}")
            except ValueError:
                pass

        # Extract area (e.g., "67.73 m²")
        area_match = re.search(r'([0-9.,]+)\s*m²', title)
        if area_match:
            try:
                area_str = area_match.group(1).replace(',', '.')
                data['size'] = float(area_str)
                self.logger.debug(f"📐 Found size: {data['size']}")
            except ValueError:
                pass

        # Calculate price per sqm
        if data.get('price') and data.get('size'):
            data['pricePerSqm'] = round(data['price'] / data['size'], 2)
            self.logger.debug(f"💰/📐 Calculated pricePerSqm: {data['pricePerSqm']}")

        # Extract address (after "zur Miete" or "zu verkaufen")
        address_match = re.search(r'zur\s+(?:Miete|miete)\s+(.+)', title, re.IGNORECASE)
        if not address_match:
            address_match = re.search(r'zu\s+verkaufen\s+(.+)', title, re.IGNORECASE)

        if address_match:
            address = address_match.group(1).strip()
            data['address'] = address
            self.logger.debug(f"📍 Found address: {data['address']}")

        # Determine property type from title
        title_lower = title.lower()
        if 'wohnung' in title_lower or 'apartment' in title_lower:
            data['propertyType'] = 'apartment'
        elif 'haus' in title_lower or 'house' in title_lower:
            data['propertyType'] = 'house'
        elif 'gewerbe' in title_lower or 'büro' in title_lower:
            data['propertyType'] = 'commercial'
        else:
            data['propertyType'] = 'apartment'  # Default

        # Determine deal type from title
        if 'zur miete' in title_lower or 'miete' in title_lower:
            data['dealType'] = 'rent'
        elif 'verkauf' in title_lower or 'kauf' in title_lower:
            data['dealType'] = 'sale'
        else:
            data['dealType'] = 'rent'  # Default

        self.logger.debug(f"📊 Title parsing result: {data}")
        return data

    async def _extract_posted_date(self) -> Optional[str]:
        """Extract posted date from Immowelt property page."""
        try:
            # Try to find date information on the page
            date_result = await self.tab.evaluate('''
                (() => {
                    // Look for common date patterns in German
                    const datePatterns = [
                        // Look for "Verfügbar ab" or similar date indicators
                        'verfügbar ab',
                        'einstellungsdatum',
                        'inseriert am',
                        'erstellt am',
                        'datum',
                        'veröffentlicht'
                    ];

                    // Search for date elements
                    const allElements = document.querySelectorAll('*');

                    for (const element of allElements) {
                        const text = element.textContent?.toLowerCase() || '';

                        for (const pattern of datePatterns) {
                            if (text.includes(pattern)) {
                                // Look for date patterns: DD.MM.YYYY or DD/MM/YYYY
                                const dateMatch = text.match(/(\d{1,2})[\.\/](\d{1,2})[\.\/](\d{4})/);
                                if (dateMatch) {
                                    const day = parseInt(dateMatch[1]);
                                    const month = parseInt(dateMatch[2]);
                                    const year = parseInt(dateMatch[3]);

                                    // Validate date ranges to avoid parsing other numbers
                                    if (day >= 1 && day <= 31 && month >= 1 && month <= 12 && year >= 2000 && year <= 2030) {
                                        return `${year}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;
                                    }
                                }

                                // Look for German month names
                                const germanDateMatch = text.match(/(\d{1,2})\.?\s*(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s*(\d{4})/i);
                                if (germanDateMatch) {
                                    const months = {
                                        'januar': '01', 'februar': '02', 'märz': '03', 'april': '04',
                                        'mai': '05', 'juni': '06', 'juli': '07', 'august': '08',
                                        'september': '09', 'oktober': '10', 'november': '11', 'dezember': '12'
                                    };
                                    const month = months[germanDateMatch[2].toLowerCase()];
                                    if (month) {
                                        return `${germanDateMatch[3]}-${month}-${germanDateMatch[1].padStart(2, '0')}`;
                                    }
                                }
                            }
                        }
                    }

                    return null;
                })()
            ''')

            if date_result and isinstance(date_result, str):
                return date_result

            return None

        except Exception as e:
            self.logger.debug(f"Date extraction error: {e}")
            return None

    def _clean_text(self, text) -> Optional[str]:
        """Clean and normalize text content."""
        if not text:
            return None

        # Handle non-string types
        if not isinstance(text, str):
            if isinstance(text, dict):
                # If it's a dict, try to get a reasonable string representation
                return None
            try:
                text = str(text)
            except Exception:
                return None

        # Remove extra whitespace and newlines
        cleaned = re.sub(r'\s+', ' ', text.strip())

        return cleaned if cleaned else None

    def _create_property_listing(self, property_data: Dict[str, Any]) -> PropertyListing:
        """Create PropertyListing object from extracted data."""
        return PropertyListing(
            source='immowelt',
            sourceId=property_data['sourceId'],
            url=property_data.get('url', ''),
            title=property_data['title'],
            dealType=property_data['dealType'],
            propertyType=property_data['propertyType'],
            description=property_data.get('description'),
            address=property_data.get('address'),
            price=property_data.get('price'),
            size=property_data.get('size'),
            rooms=property_data.get('rooms'),
            floor=property_data.get('floor'),
            yearBuilt=property_data.get('yearBuilt'),
            condition=property_data.get('condition'),
            pricePerSqm=property_data.get('pricePerSqm'),
            features=property_data.get('features', []),
            images=property_data.get('images', []),
            contactName=property_data.get('contactName'),
            contactPhone=property_data.get('contactPhone'),
            contactAgency=property_data.get('contactAgency'),
            postedDate=property_data.get('postedDate')
        )