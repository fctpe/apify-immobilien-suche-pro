"""
ImmobilienScout24 crawler using nodriver for enhanced anti-detection.
Implements AWS WAF bypass capabilities and human-like behavior.
"""

import asyncio
import logging
import os
import random
import re
import subprocess
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse, parse_qs
import json
import time
from functools import wraps

import nodriver as uc
from nodriver import Tab, Browser

from types_def import PropertyListing, SearchBuilder, PriceInfo, SizeInfo, AddressInfo, GeoInfo, ContactInfo, ScrapingResult
from utils import (
    extract_price_from_text, extract_area_from_text, extract_rooms_from_text,
    normalize_property_type, normalize_deal_type, clean_html_text,
    generate_canonical_id, extract_location_key, get_user_agents,
    extract_from_nodriver_result
)


def async_timeout(timeout_seconds: int):
    """Decorator to add timeout to async functions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger = logging.getLogger(__name__)
                logger.warning(f"⏰ Timeout ({timeout_seconds}s) in {func.__name__}")
                return None
        return wrapper
    return decorator


class ImmobilienScout24Crawler:
    """Enhanced anti-detection crawler for ImmobilienScout24 using nodriver."""

    BASE_URL = "https://www.immobilienscout24.de"
    SEARCH_BASE = "https://www.immobilienscout24.de/Suche/de"

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
        self.xvfb_process = None  # Track virtual display process

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()

    async def initialize(self) -> None:
        """Initialize the browser with enhanced anti-detection."""
        self.logger.info("🚀 Initializing nodriver browser with anti-detection")

        try:
            # Detect if running on Apify platform or as root (Docker)
            is_apify = os.environ.get('APIFY_IS_AT_HOME') == '1'
            is_root = hasattr(os, 'getuid') and os.getuid() == 0
            needs_no_sandbox = is_apify or is_root

            if needs_no_sandbox:
                self.logger.info("🐳 Running on Apify platform or as root - using virtual display")

                # Start virtual display for anti-detection
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
                    '--mute-audio',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-logging',
                    '--disable-gpu-logging',
                    '--silent',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-field-trial-config',
                    '--disable-back-forward-cache',
                    '--disable-ipc-flooding-protection'
                ]

                self.browser = await uc.start(
                    headless=False,  # Use virtual display instead of headless
                    sandbox=False,   # Required for Docker
                    browser_args=browser_args
                )
            else:
                self.browser = await uc.start(headless=self.headless)

            self.logger.debug("✅ Browser started successfully")

            # Wait a moment for browser to be ready
            await asyncio.sleep(2)

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

            # Test basic functionality with proper parameters
            try:
                test_result = await self.tab.evaluate('() => "test"', return_by_value=True)
                if test_result == "test":
                    self.logger.debug("✅ JavaScript evaluation working")
                else:
                    self.logger.warning(f"⚠️ JavaScript evaluation test failed, got: {test_result}")
            except Exception as eval_error:
                self.logger.warning(f"⚠️ JavaScript evaluation error: {eval_error}")
                # This is expected if page hasn't loaded yet, we'll continue anyway

            # Apply basic stealth measures (nodriver handles most automatically)
            await self._apply_stealth_measures()

            self.logger.info("✅ Browser initialized successfully")

        except Exception as error:
            self.logger.error(f"❌ Failed to initialize browser: {error}")
            raise

    async def _start_virtual_display(self) -> None:
        """Start Xvfb virtual display for anti-detection."""
        try:
            # Check if DISPLAY is already set (might be running locally with actual display)
            if os.environ.get('DISPLAY') and not os.environ.get('APIFY_IS_AT_HOME'):
                self.logger.debug("Display already available, skipping virtual display")
                return

            # Start Xvfb virtual display
            self.logger.info("🖥️ Starting virtual display (Xvfb)")
            display_num = os.environ.get('DISPLAY', ':99').replace(':', '')

            xvfb_cmd = [
                'Xvfb', f':{display_num}',
                '-screen', '0', '1920x1080x24',
                '-ac', '+extension', 'GLX',
                '+render', '-noreset'
            ]

            self.xvfb_process = subprocess.Popen(
                xvfb_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Set DISPLAY environment variable
            os.environ['DISPLAY'] = f':{display_num}'

            # Give Xvfb a moment to start
            await asyncio.sleep(1)

            self.logger.info(f"✅ Virtual display started on :{display_num}")

        except Exception as error:
            self.logger.warning(f"⚠️ Could not start virtual display: {error}")
            # Continue without virtual display - fallback to headless

    async def _stop_virtual_display(self) -> None:
        """Stop the virtual display."""
        try:
            if self.xvfb_process:
                self.logger.info("🖥️ Stopping virtual display")
                self.xvfb_process.terminate()
                self.xvfb_process.wait(timeout=5)
                self.xvfb_process = None
        except Exception as error:
            self.logger.warning(f"⚠️ Error stopping virtual display: {error}")

    async def cleanup(self) -> None:
        """Clean up browser resources."""
        try:
            if self.browser:
                self.logger.info("🧹 Cleaning up browser resources")
                # nodriver's stop method is not async
                self.browser.stop()

            # Stop virtual display if running
            await self._stop_virtual_display()

        except Exception as error:
            self.logger.error(f"⚠️ Error during cleanup: {error}")

    async def _apply_stealth_measures(self) -> None:
        """Apply basic stealth measures - nodriver handles most stealth automatically."""
        if not self.tab:
            return

        try:
            # Use simple JavaScript evaluation instead of CDP commands
            await self.tab.evaluate("""
                () => {
                    // Basic stealth - hide webdriver property
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });

                    // Set realistic language preferences
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['de-DE', 'de', 'en-US', 'en'],
                    });
                }
            """, return_by_value=False)

            self.logger.debug("🔒 Applied basic stealth measures")

        except Exception as error:
            self.logger.warning(f"⚠️ Failed to apply stealth measures: {error}")
            # This is okay - nodriver handles most stealth automatically

    @async_timeout(30)
    async def _warm_up_session(self) -> None:
        """Simplified session warm-up with timeout."""
        try:
            self.logger.info("🏠 Quick session warm-up")

            # Navigate to homepage
            await self.tab.get(self.BASE_URL)
            await self._human_like_wait(1, 2)

            # Handle cookie banner
            await self._handle_cookie_consent()

            self.logger.info("✅ Session ready")

        except Exception as error:
            self.logger.warning(f"⚠️ Session warm-up failed: {error}, proceeding anyway")

    async def _handle_cookie_consent(self) -> None:
        """Handle cookie consent banner using nodriver's native methods."""
        try:
            self.logger.info("🍪 Handling cookie consent modal using nodriver methods...")

            # Give page time to load and modal to appear
            await asyncio.sleep(2)

            # Take screenshot for debugging
            await self._take_debug_screenshot('cookie_consent_before.png')

            success = False

            # Strategy 1: Enhanced tab.find() with multiple text variations
            try:
                self.logger.info("🔘 Strategy 1: Enhanced tab.find() with multiple text variations...")

                # Try multiple consent button text variations
                consent_texts = [
                    'Alle akzeptieren',
                    'Akzeptieren',
                    'Accept all',
                    'Alle Cookies akzeptieren',
                    'Zustimmen',
                    'OK',
                    'Einverstanden'
                ]

                for text in consent_texts:
                    try:
                        self.logger.debug(f"Looking for button with text: '{text}'")
                        accept_button = await self.tab.find(text, best_match=True, timeout=3)
                        if accept_button:
                            self.logger.info(f"✅ Found cookie consent button with text: '{text}'")
                            await accept_button.click()
                            success = True
                            self.logger.info("✅ Cookie consent button clicked successfully!")
                            await asyncio.sleep(2)
                            break
                    except Exception as text_error:
                        self.logger.debug(f"Failed with text '{text}': {text_error}")
                        continue

            except Exception as find_error:
                self.logger.debug(f"Enhanced tab.find() approach failed: {find_error}")

            # Strategy 2: Enhanced CSS selector approach as fallback
            if not success:
                try:
                    self.logger.info("🔘 Using tab.select() with CSS selectors...")

                    # Try different CSS selectors
                    selectors = [
                        'button:contains("Alle akzeptieren")',
                        '[data-cy*="accept"]',
                        '[data-testid*="accept"]',
                        '[id*="accept"]',
                        '[class*="accept"]',
                        'button[title*="akzeptieren"]',
                        # Generic button selectors
                        'button',
                        '[role="button"]'
                    ]

                    for selector in selectors:
                        try:
                            elements = await self.tab.select_all(selector, timeout=2)
                            if elements:
                                self.logger.debug(f"Found {len(elements)} elements with selector: {selector}")

                                # Check each element for the right text
                                for element in elements:
                                    try:
                                        # Get element text using different approaches
                                        try:
                                            text_content = await element.text
                                        except:
                                            try:
                                                text_content = str(await element.evaluate('element => element.textContent'))
                                            except:
                                                continue

                                        if text_content and 'Alle akzeptieren' in text_content:
                                            self.logger.info(f"✅ Found button with text: '{text_content}'")
                                            await element.click()
                                            success = True
                                            self.logger.info("✅ Cookie consent clicked via CSS selector!")
                                            await asyncio.sleep(2)
                                            break
                                    except Exception as text_error:
                                        self.logger.debug(f"Error getting text from element: {text_error}")
                                        continue

                                if success:
                                    break
                        except Exception as selector_error:
                            self.logger.debug(f"Selector {selector} failed: {selector_error}")
                            continue

                except Exception as select_error:
                    self.logger.debug(f"tab.select() approach failed: {select_error}")

            # Strategy 3: Use wait_for method as final fallback
            if not success:
                try:
                    self.logger.info("🔘 Using tab.wait_for() method...")

                    # Wait for button with specific text
                    await self.tab.wait_for(text='Alle akzeptieren', timeout=5)

                    # Try to find and click again
                    button = await self.tab.find('Alle akzeptieren', timeout=2)
                    if button:
                        await button.click()
                        success = True
                        self.logger.info("✅ Cookie consent clicked via wait_for!")
                        await asyncio.sleep(2)

                except Exception as wait_error:
                    self.logger.debug(f"wait_for approach failed: {wait_error}")

            # Verify modal was closed
            if success:
                await self._take_debug_screenshot('cookie_consent_after_click.png')

                # Wait a bit more for modal animation
                await asyncio.sleep(2)

                # Check if we can now access page content
                try:
                    title = await self.tab.evaluate('document.title')
                    if title:
                        title_str = str(title).strip()
                        if title_str and title_str != 'RemoteObject':
                            self.logger.info(f"✅ Page accessible after cookie consent: {title_str}")
                        else:
                            self.logger.info("✅ Page accessible after cookie consent")
                    else:
                        self.logger.warning("⚠️ Page still may not be fully accessible")

                except Exception as verify_error:
                    self.logger.debug(f"Page verification failed: {verify_error}")

            else:
                self.logger.warning("⚠️ Could not click cookie consent button - will try to proceed anyway")

            # Final screenshot
            await self._take_debug_screenshot('cookie_consent_final.png')

        except Exception as error:
            self.logger.error(f"❌ Cookie consent handling failed: {error}")
            # Continue anyway - maybe the modal isn't present

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

    async def _human_like_wait(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Wait for a random human-like duration."""
        wait_time = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(wait_time)

    @async_timeout(60)


    async def _take_debug_screenshot(self, filename: str) -> None:
        """Take a screenshot for debugging purposes if debug mode is enabled."""
        if self.debug:
            try:
                await self.tab.save_screenshot(filename)
                self.logger.debug(f"📸 Debug screenshot saved: {filename}")
            except Exception as e:
                self.logger.debug(f"Failed to take screenshot {filename}: {e}")

    def build_immoscout24_url(self, filters: dict) -> str:
        """Build ImmobilienScout24 URL from search filters."""
        try:
            # Base path components
            state = filters.get('state', 'berlin')
            city = filters.get('city', 'berlin')
            deal_type = 'wohnung-mieten' if filters.get('dealType', 'rent') == 'rent' else 'wohnung-kaufen'

            # Build base URL
            base_url = f"{self.SEARCH_BASE}/{state}/{city}/{deal_type}"

            # Build query parameters
            params = []

            # Price range
            if filters.get('priceMin') or filters.get('priceMax'):
                price_min = str(filters.get('priceMin', '')) if filters.get('priceMin') is not None else ''
                price_max = str(filters.get('priceMax', '')) if filters.get('priceMax') is not None else ''
                params.append(f"price={price_min}-{price_max}")

            # Living space range
            if filters.get('sizeMin') or filters.get('sizeMax'):
                size_min = str(filters.get('sizeMin', '')) if filters.get('sizeMin') is not None else ''
                size_max = str(filters.get('sizeMax', '')) if filters.get('sizeMax') is not None else ''
                params.append(f"livingspace={size_min}-{size_max}")

            # Number of rooms range
            if filters.get('roomsMin') or filters.get('roomsMax'):
                rooms_min = str(filters.get('roomsMin', '')) if filters.get('roomsMin') is not None else ''
                rooms_max = str(filters.get('roomsMax', '')) if filters.get('roomsMax') is not None else ''
                params.append(f"numberofrooms={rooms_min}-{rooms_max}")

            # Search radius
            if filters.get('radiusKm'):
                params.append(f"radius={filters['radiusKm']}")

            # Posted since days
            if filters.get('postedSinceDays'):
                params.append(f"publicationdate={filters['postedSinceDays']}")

            # Combine URL and parameters
            if params:
                url = f"{base_url}?" + "&".join(params)
            else:
                url = base_url

            self.logger.info(f"🔗 Built search URL: {url}")
            return url

        except Exception as error:
            self.logger.error(f"❌ Error building URL from filters: {error}")
            # Fallback to basic Berlin search
            return f"{self.SEARCH_BASE}/berlin/berlin/wohnung-mieten"

    @async_timeout(180)
    async def scrape_search_url(self, search_url: str, max_results: int = 5) -> List[PropertyListing]:
        """Scrape listings from a direct search URL."""
        self.logger.info(f"🔍 Scraping search URL: {search_url}")

        try:
            # Navigate to search URL with better error handling
            self.logger.info(f"📍 Navigating to: {search_url}")

            try:
                await self.tab.get(search_url)
                self.logger.info("✅ Navigation completed")
            except Exception as nav_error:
                self.logger.error(f"❌ Navigation failed: {nav_error}")
                # Try alternative navigation method
                await self.tab.send({'method': 'Page.navigate', 'params': {'url': search_url}})
                await asyncio.sleep(5)

            # Give page a moment to load (simplified approach)
            await asyncio.sleep(2)

            # Handle cookie consent if still present
            await self._handle_cookie_consent()

            # Wait a moment for search results to load after cookie consent
            await asyncio.sleep(2)

            # Check if we hit a CAPTCHA or error page
            if await self._detect_captcha_or_block():
                self.logger.error("❌ Detected CAPTCHA or blocking page")
                return []

            # Take screenshot before extraction
            await self._take_debug_screenshot('before_extraction.png')

            # Extract listings from search results
            listings = await self._extract_search_results(max_results)

            # Take screenshot after extraction
            await self._take_debug_screenshot('after_extraction.png')

            self.logger.info(f"✅ Extracted {len(listings)} listings from search URL")
            return listings

        except Exception as error:
            self.logger.error(f"❌ Error scraping search URL: {error}")
            return []

    async def scrape_search_builder(self, builder: SearchBuilder, max_results: int = None) -> List[PropertyListing]:
        """Scrape listings using search builder configuration."""
        self.logger.info(f"🔨 Building search for regions: {builder.regions}")

        try:
            # Convert SearchBuilder to filters dict
            filters = {
                'dealType': builder.dealType or 'rent',
                'priceMin': builder.priceMin,
                'priceMax': builder.priceMax,
                'sizeMin': builder.sizeMin,
                'roomsMin': builder.roomsMin,
                'roomsMax': builder.roomsMax,
                'radiusKm': builder.radiusKm,
                'postedSinceDays': builder.postedSinceDays
            }

            # Handle regions - use first region or default to Berlin
            if builder.regions:
                primary_region = builder.regions[0].lower()
                # Simple city/state mapping
                if 'berlin' in primary_region:
                    filters['state'] = 'berlin'
                    filters['city'] = 'berlin'
                elif 'münchen' in primary_region or 'munich' in primary_region:
                    filters['state'] = 'bayern'
                    filters['city'] = 'muenchen'
                elif 'hamburg' in primary_region:
                    filters['state'] = 'hamburg'
                    filters['city'] = 'hamburg'
                else:
                    # Default to treating as city in respective state
                    filters['city'] = primary_region.replace(' ', '-')
                    filters['state'] = primary_region.replace(' ', '-')

            # Build search URL using the new URL builder
            search_url = self.build_immoscout24_url(filters)

            # Use the search URL scraper
            result_max = max_results or 5  # Default for builders
            return await self.scrape_search_url(search_url, max_results=result_max)

        except Exception as error:
            self.logger.error(f"❌ Error with search builder: {error}")
            return []


    @async_timeout(10)
    async def _detect_captcha_or_block(self) -> bool:
        """Detect if we've been blocked or shown a CAPTCHA."""
        try:
            # Use JavaScript to check for blocking indicators (simplified to avoid RemoteObject)
            blocking_check = await self.tab.evaluate("""
                (() => {
                    // Check page title
                    const title = document.title.toLowerCase();
                    if (title.includes('captcha') || title.includes('blocked') ||
                        title.includes('robot') || title.includes('forbidden')) {
                        return 'blocked';
                    }

                    // Check for error messages in page content
                    const bodyText = document.body.textContent.toLowerCase();
                    if (bodyText.includes('zugriff verweigert') ||
                        bodyText.includes('access denied') ||
                        bodyText.includes('ich bin kein roboter')) {
                        return 'blocked';
                    }

                    // Check URL for blocking patterns
                    const url = window.location.href.toLowerCase();
                    if (url.includes('captcha') || url.includes('block') || url.includes('denied')) {
                        return 'blocked';
                    }

                    return 'ok';
                })()
            """)

            return str(blocking_check) == 'blocked'

        except Exception as error:
            self.logger.debug(f"CAPTCHA detection error: {error}")
            return False

    @async_timeout(30)
    async def _extract_search_results(self, max_results: int = 5) -> List[PropertyListing]:
        """Extract property URLs from search page and then scrape each detail page."""
        self.logger.info("📋 Extracting property URLs from search results")

        listings = []

        try:
            # Wait for results to load
            await asyncio.sleep(2)

            # Get all property URLs using JavaScript
            self.logger.info("🔗 Extracting property URLs using JavaScript...")

            # Debug: Log current page info - try different evaluation methods
            try:
                current_url = await self.tab.evaluate('() => window.location.href', await_promise=False)
                if not current_url:
                    current_url = "Unable to get URL"
            except:
                current_url = "Error getting URL"

            try:
                page_title = await self.tab.evaluate('() => document.title', await_promise=False)
                if not page_title:
                    page_title = "Unable to get title"
            except:
                page_title = "Error getting title"

            self.logger.debug(f"🌍 Current page: {current_url}")
            self.logger.debug(f"📄 Page title: {page_title}")

            # Try simpler JavaScript evaluation and handle RemoteObject
            try:
                result = await self.tab.evaluate('''
                    (() => {
                        const debug = {
                            totalLinks: document.querySelectorAll('a').length,
                            patterns: {},
                            samples: []
                        };

                        // Use correct selectors based on actual HTML structure
                        const patterns = [
                            'a[href*="/expose/"][data-exp-id]',  // Primary: Individual listings
                            '.listing-card a[data-exp-id][href^="/expose/"]',  // Within listing cards
                            'a[href*="/neubau/"]',  // New construction projects
                            'a[href*="/expose/"]'   // Fallback
                        ];

                        const urls = [];
                        const seenExposeIds = new Set();

                        for (const pattern of patterns) {
                            const links = document.querySelectorAll(pattern);
                            debug.patterns[pattern] = links.length;

                            for (const link of links) {
                                // Prefer using data-exp-id for unique identification
                                const exposeId = link.getAttribute('data-exp-id');
                                let fullUrl = '';

                                if (exposeId && !seenExposeIds.has(exposeId)) {
                                    fullUrl = `https://www.immobilienscout24.de/expose/${exposeId}`;
                                    seenExposeIds.add(exposeId);
                                } else {
                                    // Fallback to href
                                    const href = link.href || link.getAttribute('href');
                                    if (href && (href.includes('/expose') || href.includes('/neubau'))) {
                                        fullUrl = href.startsWith('/') ? 'https://www.immobilienscout24.de' + href : href;

                                        // Check if we already have this URL
                                        if (urls.includes(fullUrl)) continue;
                                    }
                                }

                                if (fullUrl && !urls.includes(fullUrl)) {
                                    urls.push(fullUrl);
                                }
                            }

                            if (urls.length > 0) break; // Stop if we found URLs with this pattern
                        }

                        // Get sample of all links for debugging
                        const allLinks = Array.from(document.querySelectorAll('a')).slice(0, 10);
                        debug.samples = allLinks.map(link => ({
                            href: link.href || link.getAttribute('href'),
                            text: link.textContent ? link.textContent.trim().substring(0, 50) : ''
                        }));

                        return { urls, debug };
                    })()
                ''', await_promise=False)

                # Debug: Check what type of result we got
                self.logger.debug(f"🔧 JavaScript result type: {type(result)}")
                self.logger.debug(f"🔧 JavaScript result: {str(result)[:200]}...")

                # Handle complex result structures from nodriver

                property_urls = extract_from_nodriver_result(result)
                self.logger.debug(f"✅ Processed result: {str(property_urls)[:200]}...")

            except Exception as e:
                self.logger.error(f"❌ JavaScript evaluation failed: {e}")
                property_urls = None

            # Log debug information
            if property_urls and isinstance(property_urls, dict) and 'debug' in property_urls:
                debug_info = property_urls['debug']
                if isinstance(debug_info, dict):
                    self.logger.debug(f"🔗 Total links on page: {debug_info.get('totalLinks', 0)}")
                else:
                    self.logger.debug(f"🔗 Debug info is {type(debug_info)}, cannot get totalLinks")

                # Skip debug patterns parsing for now - complex nested structure
                # patterns_info = debug_info.get('patterns', {})
                # if isinstance(patterns_info, dict):
                #     for pattern, count in patterns_info.items():
                #         self.logger.debug(f"📊 Pattern '{pattern}': {count} matches")

                # self.logger.debug("🔍 Sample links on page:")
                # samples = debug_info.get('samples', [])
                # if isinstance(samples, list):
                #     for i, sample in enumerate(samples[:5]):
                #         if isinstance(sample, dict):
                #             self.logger.debug(f"  {i+1}. href='{sample.get('href', 'N/A')}' text='{sample.get('text', 'N/A')}'")
                self.logger.debug("✅ Skipped detailed debug processing")

                property_urls = property_urls.get('urls', [])
            elif property_urls and isinstance(property_urls, dict) and 'urls' in property_urls:
                # Just URLs without debug info
                self.logger.debug("✅ Got URLs without debug info")
                property_urls = property_urls.get('urls', [])
            elif property_urls and isinstance(property_urls, list):
                # Direct list of URLs
                self.logger.debug("✅ Got direct list of URLs")
                # property_urls is already the list we want
            else:
                self.logger.debug("❌ No valid URL data returned from JavaScript")
                property_urls = []

            self.logger.debug(f"🎯 Extracted {len(property_urls)} property URLs")

            if not property_urls or len(property_urls) == 0:
                self.logger.warning("❌ No property URLs found")

                # Additional debugging - check if page loaded correctly
                try:
                    body_text = await self.tab.evaluate('(() => document.body ? document.body.textContent.substring(0, 500) : "NO BODY")()', await_promise=False)
                    self.logger.debug(f"📝 Page content sample: {body_text}")
                except Exception as e:
                    self.logger.debug(f"❌ Could not get page content: {e}")

                await self._take_debug_screenshot('no_urls_found.png')
                return []

            self.logger.info(f"✅ Found {len(property_urls)} property URLs")

            # Limit to maxResults if specified
            if max_results and len(property_urls) > max_results:
                property_urls = property_urls[:max_results]
                self.logger.info(f"🔢 Limited to first {max_results} properties per configuration")

            # Extract data from each property detail page
            for index, url in enumerate(property_urls, 1):
                try:
                    self.logger.info(f"🏠 Scraping property {index}/{len(property_urls)}: {url}")

                    listing = await self._scrape_property_detail(url, index)
                    if listing:
                        listings.append(listing)
                        self.logger.info(f"✅ Successfully extracted listing {index}: {listing.title}")
                    else:
                        self.logger.debug(f"❌ Failed to extract listing from {url}")

                except Exception as error:
                    self.logger.warning(f"❌ Error scraping property {index} ({url}): {error}")
                    continue

            self.logger.info(f"✅ Successfully extracted {len(listings)} listings from {len(property_urls)} URLs")
            return listings

        except Exception as error:
            self.logger.error(f"❌ Error in search results extraction: {error}")
            # Add more detailed error info
            import traceback
            self.logger.debug(f"❌ Full traceback: {traceback.format_exc()}")
            await self._take_debug_screenshot('search_extraction_error.png')
            return []

    async def _scrape_property_detail(self, url: str, index: int) -> Optional[PropertyListing]:
        """Navigate to property detail page and extract comprehensive data."""
        try:
            self.logger.debug(f"🌍 Navigating to property detail: {url}")

            # Navigate to the property detail page
            await self.tab.get(url)

            # Wait for page to load
            await asyncio.sleep(3)

            # Debug: Check if page loaded correctly
            try:
                actual_url = await self.tab.evaluate('(() => window.location.href)()', await_promise=False)
                self.logger.debug(f"📍 Loaded page: {actual_url}")
            except Exception as e:
                self.logger.debug(f"❌ Could not get page URL: {e}")

            try:
                page_title = await self.tab.evaluate('(() => document.title)()', await_promise=False)
                self.logger.debug(f"📄 Page title: {page_title}")
            except Exception as e:
                self.logger.debug(f"❌ Could not get page title: {e}")

            # Extract all property data using JavaScript
            try:
                property_data = await self.tab.evaluate('''
                    (() => {
                        const data = {
                            title: '',
                            price: '',
                            area: '',
                            rooms: '',
                            address: '',
                            description: '',
                            propertyId: ''
                        };

                        // Extract title
                        const titleSelectors = [
                            'h1[data-testid="headline"]',
                            'h1.headline-detailed-view__title',
                            'h1',
                            '.headline h1'
                        ];

                        for (const selector of titleSelectors) {
                            const elem = document.querySelector(selector);
                            if (elem && elem.textContent && elem.textContent.trim()) {
                                data.title = elem.textContent.trim();
                                break;
                            }
                        }

                        // Extract property ID from URL or page
                        const urlMatch = window.location.href.match(/expose\\/([0-9]+)/);
                        if (urlMatch) {
                            data.propertyId = urlMatch[1];
                        }

                        // Extract price information using correct selectors
                        const coldRentSelectors = [
                            '.is24qa-kaltmiete',
                            '.is24qa-kaltmiete-main .is24-preis-value'
                        ];
                        for (const selector of coldRentSelectors) {
                            const elem = document.querySelector(selector);
                            if (elem && elem.textContent && elem.textContent.includes('€')) {
                                data.price = elem.textContent.trim();
                                break;
                            }
                        }

                        // Extract warm rent as backup
                        if (!data.price) {
                            const warmRentElem = document.querySelector('.is24qa-warmmiete-main span, .is24qa-gesamtmiete');
                            if (warmRentElem && warmRentElem.textContent && warmRentElem.textContent.includes('€')) {
                                data.price = warmRentElem.textContent.trim();
                            }
                        }

                        // Extract area with correct selectors
                        const areaSelectors = [
                            '.is24qa-flaeche-main',
                            '.is24qa-wohnflaeche-ca',
                            '.is24qa-wohnflaeche'
                        ];
                        for (const selector of areaSelectors) {
                            const elem = document.querySelector(selector);
                            if (elem && elem.textContent && elem.textContent.includes('m²')) {
                                data.area = elem.textContent.trim();
                                break;
                            }
                        }

                        // Extract rooms with correct selectors
                        const roomSelectors = [
                            '.is24qa-zi-main',
                            '.is24qa-zimmer',
                            '.is24qa-schlafzimmer'
                        ];
                        for (const selector of roomSelectors) {
                            const elem = document.querySelector(selector);
                            if (elem && elem.textContent && elem.textContent.trim()) {
                                const text = elem.textContent.trim();
                                // Check if it's a number or contains "Zimmer"
                                if (/^\\d+([.,]\\d+)?$/.test(text) || text.includes('Zimmer')) {
                                    data.rooms = text;
                                    break;
                                }
                            }
                        }

                        // Extract additional property details
                        const additionalData = {};

                        // Property type
                        const typeElem = document.querySelector('.is24qa-typ');
                        if (typeElem && typeElem.textContent) {
                            additionalData.propertyType = typeElem.textContent.trim();
                        }

                        // Floor
                        const floorElem = document.querySelector('.is24qa-etage');
                        if (floorElem && floorElem.textContent) {
                            additionalData.floor = floorElem.textContent.trim();
                        }

                        // Additional costs
                        const additionalCostsElem = document.querySelector('.is24qa-nebenkosten');
                        if (additionalCostsElem && additionalCostsElem.textContent) {
                            additionalData.additionalCosts = additionalCostsElem.textContent.trim();
                        }

                        // Price per sqm
                        const pricePerSqmElem = document.querySelector('.is24qa-preism², .is24qa-kaltmiete-main-label span');
                        if (pricePerSqmElem && pricePerSqmElem.textContent) {
                            additionalData.pricePerSqm = pricePerSqmElem.textContent.trim();
                        }

                        // Available from
                        const availableFromElem = document.querySelector('.is24qa-bezugsfrei-ab');
                        if (availableFromElem && availableFromElem.textContent) {
                            additionalData.availableFrom = availableFromElem.textContent.trim();
                        }

                        // Add additional data to main data object
                        Object.assign(data, additionalData);

                        // Extract address
                        const addressSelectors = [
                            '[data-testid="address"]',
                            '.address-block',
                            '.location-info .address'
                        ];

                        for (const selector of addressSelectors) {
                            const elem = document.querySelector(selector);
                            if (elem && elem.textContent && elem.textContent.trim()) {
                                data.address = elem.textContent.trim();
                                break;
                            }
                        }

                        // Extract description
                        const descSelectors = [
                            '.is24qa-objektbeschreibung',
                            '.description-text',
                            '.expose-description'
                        ];

                        for (const selector of descSelectors) {
                            const elem = document.querySelector(selector);
                            if (elem && elem.textContent && elem.textContent.trim()) {
                                data.description = elem.textContent.trim();
                                break;
                            }
                        }

                        return data;
                    })()
                ''', await_promise=False)
            except Exception as e:
                self.logger.warning(f"❌ JavaScript evaluation failed for property data: {e}")
                property_data = None

            # Handle complex result structures from nodriver

            property_data = extract_from_nodriver_result(property_data)

            # Debug: Log extracted data
            if property_data and isinstance(property_data, dict):
                self.logger.debug(f"📊 Extracted data from {url}:")
                for key, value in property_data.items():
                    if value:
                        value_preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        self.logger.debug(f"  {key}: {value_preview}")
                    else:
                        self.logger.debug(f"  {key}: [EMPTY]")
            else:
                self.logger.warning(f"❌ No valid data extracted from {url}")
                return None

            # Create PropertyListing from extracted data
            listing = await self._create_property_listing_from_data(property_data, url, index)

            if listing:
                self.logger.debug(f"✅ Created listing: {listing.title} - {listing.price}")
            else:
                self.logger.debug(f"❌ Failed to create listing from extracted data")

            return listing

        except Exception as error:
            self.logger.warning(f"❌ Error scraping detail page {url}: {error}")
            return None

    async def _create_property_listing_from_data(self, data: dict, url: str, index: int) -> Optional[PropertyListing]:
        """Create PropertyListing object from extracted data."""
        try:
            import re

            # Parse price as simple number
            price_value = None
            if data.get('price'):
                price_value = extract_price_from_text(data['price'])

            # Parse area as simple number
            size_value = None
            if data.get('area'):
                size_value = extract_area_from_text(data['area'])

            # Parse rooms
            rooms_count = None
            if data.get('rooms'):
                rooms_count = extract_rooms_from_text(data['rooms'])

            # Parse address as simple string
            address_str = data.get('address', '').strip() if data.get('address') else None

            # Calculate price per sqm
            price_per_sqm = None
            if price_value and size_value and size_value > 0:
                price_per_sqm = round(price_value / size_value, 2)

            # Generate source ID
            source_id = data.get('propertyId') or f'detail_{index}'

            # Create simplified listing
            listing = PropertyListing(
                sourceId=source_id,
                title=data.get('title') or f"Property {index}",
                url=url,
                dealType='rent',
                propertyType=data.get('propertyType', 'apartment'),
                price=price_value,
                size=size_value,
                rooms=rooms_count,
                address=address_str,
                source="immobilienscout24",
                description=data.get('description', ''),
                pricePerSqm=price_per_sqm
            )

            return listing

        except Exception as error:
            self.logger.debug(f"Error creating listing from data: {error}")
            return None


    async def _extract_listing_data(self, element, index: int) -> Optional[PropertyListing]:
        """Extract data from a single listing element."""
        try:
            # Get listing ID (obid)
            source_id = await element.get_attribute('data-obid') or f"scraped_{index}"

            # Extract title
            title_element = await element.select('a[data-testid="result-list-entry-title"] h3, .result-list-entry__data h3')
            title = await title_element.get_text() if title_element else f"Property {index}"
            title = clean_html_text(title)

            # Extract URL
            link_element = await element.select('a[data-testid="result-list-entry-title"], .result-list-entry__data a')
            relative_url = await link_element.get_attribute('href') if link_element else ""
            url = urljoin(self.BASE_URL, relative_url) if relative_url else ""

            # Extract price as simple number
            price_element = await element.select('.result-list-entry__primary-criterion dd, [data-testid="price"]')
            price_text = await price_element.get_text() if price_element else ""
            price_value = extract_price_from_text(price_text)

            # Extract area as simple number
            area_element = await element.select('.result-list-entry__primary-criterion:nth-child(2) dd, [data-testid="area"]')
            area_text = await area_element.get_text() if area_element else ""
            area_value = extract_area_from_text(area_text)

            # Extract rooms
            rooms_element = await element.select('.result-list-entry__primary-criterion:nth-child(3) dd, [data-testid="rooms"]')
            rooms_text = await rooms_element.get_text() if rooms_element else ""
            rooms = extract_rooms_from_text(rooms_text)

            # Extract address as simple string
            address_element = await element.select('.result-list-entry__address, [data-testid="address"]')
            address_text = await address_element.get_text() if address_element else ""
            address_str = clean_html_text(address_text).strip() if address_text else None

            # Calculate price per sqm
            price_per_sqm = None
            if price_value and area_value and area_value > 0:
                price_per_sqm = round(price_value / area_value, 2)

            # Create simplified listing object
            listing = PropertyListing(
                source='immoscout24',
                sourceId=source_id,
                url=url,
                title=title,
                dealType='rent',  # Will be refined
                propertyType='apartment',  # Will be refined
                price=price_value,
                size=area_value,
                rooms=rooms,
                address=address_str,
                pricePerSqm=price_per_sqm
            )

            return listing

        except Exception as error:
            self.logger.debug(f"Error extracting listing data: {error}")
            return None

    def _parse_address(self, address_text: str) -> Optional[AddressInfo]:
        """Parse address information from text."""
        if not address_text:
            return None

        try:
            # Split address components
            parts = [part.strip() for part in address_text.split(',')]

            address_info = AddressInfo(raw=address_text)

            # Extract postcode and city (usually last part)
            if parts:
                last_part = parts[-1].strip()
                postcode_match = re.search(r'(\d{5})\s+(.+)', last_part)
                if postcode_match:
                    address_info.postcode = postcode_match.group(1)
                    address_info.city = postcode_match.group(2).strip()

            # Extract street (usually first part)
            if len(parts) > 1:
                street_part = parts[0].strip()
                # Try to separate street name and house number
                street_match = re.search(r'(.+?)\s+(\d+.*?)$', street_part)
                if street_match:
                    address_info.street = street_match.group(1).strip()
                    address_info.houseNo = street_match.group(2).strip()
                else:
                    address_info.street = street_part

            return address_info

        except Exception:
            return AddressInfo(raw=address_text)

    async def _handle_pagination(self) -> List[PropertyListing]:
        """Handle pagination to get more results."""
        all_listings = []
        page = 2  # Start from page 2 since we already got page 1
        max_pages = 5  # Limit to prevent infinite loops

        while page <= max_pages:
            try:
                self.logger.info(f"📄 Loading page {page}")

                # Look for next page button
                try:
                    next_button = await self.tab.select('a[data-testid="pagination-next"], .pagination-next', timeout=3)
                    if not next_button:
                        break

                    # Click next button
                    await next_button.click()
                except Exception as next_error:
                    self.logger.debug(f"No next page button found: {next_error}")
                    break
                await self._human_like_wait(3, 5)

                # Check for blocking
                if await self._detect_captcha_or_block():
                    self.logger.warning(f"⚠️ Blocked on page {page}")
                    break

                # Extract listings from this page
                page_listings = await self._extract_search_results()
                if not page_listings:
                    break

                all_listings.extend(page_listings)
                page += 1

                # Add delay between pages
                await self._human_like_wait(2, 4)

            except Exception as error:
                self.logger.error(f"❌ Error on page {page}: {error}")
                break

        return all_listings