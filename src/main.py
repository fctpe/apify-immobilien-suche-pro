"""
Main actor implementation for Immobiliensuche Pro Python.
Enhanced anti-detection using nodriver for bypassing AWS WAF.
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from apify import Actor
from pydantic import BaseModel, ValidationError
import coloredlogs

from types_def import ActorInput, PropertyListing
from crawler import ImmobilienScout24Crawler
from immowelt_crawler import ImmoweltCrawler
from utils import setup_logging, validate_urls, normalize_property_data


class ImmobilienProActor:
    """Main actor class for German real estate scraping with nodriver."""

    def __init__(self, input_data: ActorInput):
        self.input = input_data
        self.logger = logging.getLogger(__name__)
        self.stats = {
            'total_processed': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'duplicates_removed': 0,
            'start_time': datetime.now(timezone.utc)
        }
        self.seen_listings: set = set()

        # Handle advanced options with backward compatibility
        self._setup_advanced_options()

    def _setup_advanced_options(self):
        """Setup advanced options with backward compatibility."""
        # Use advanced options if provided, otherwise fall back to legacy fields
        if self.input.advancedOptions:
            self.debug = self.input.advancedOptions.debug
            self.headless = self.input.advancedOptions.headless
            self.concurrency = self.input.advancedOptions.concurrency
        else:
            # Backward compatibility with legacy fields
            self.debug = self.input.debug
            self.headless = self.input.headless
            self.concurrency = self.input.concurrency

        # Handle deduplication setting
        if self.input.removeDuplicates is not None:
            self.dedupe_level = 'cross_portal' if self.input.removeDuplicates else 'none'
        else:
            self.dedupe_level = self.input.dedupeLevel

    async def initialize(self) -> None:
        """Initialize actor with logging and state restoration."""
        setup_logging(self.debug)
        self.logger.info("🚀 Initializing Immobiliensuche Pro Python Actor")
        self.logger.info(f"🔧 Configuration: {self.input.dict()}")

        # Restore state if tracking mode is enabled
        if self.input.trackingMode:
            state = await Actor.get_value("STATE") or {}
            self.seen_listings = set(state.get('seen_listings', []))
            self.logger.info(f"📊 Restored {len(self.seen_listings)} seen listings from state")

    async def run(self) -> None:
        """Main execution logic."""
        try:
            self.logger.info("🔍 Starting real estate data extraction")

            # Process search URLs if provided
            if self.input.searchUrls:
                await self._process_search_urls()

            # Process search builders if provided
            if self.input.searchBuilders:
                await self._process_search_builders()

            # Save final statistics
            await self._save_statistics()

            self.logger.info("✅ Actor execution completed successfully")

        except Exception as error:
            self.logger.error(f"❌ Actor execution failed: {error}")
            raise

    async def _process_search_urls(self) -> None:
        """Process direct search URLs."""
        self.logger.info(f"🌐 Processing {len(self.input.searchUrls)} search URLs")

        for i, url_config in enumerate(self.input.searchUrls):
            self.logger.info(f"🔗 Processing URL {i+1}/{len(self.input.searchUrls)}: {url_config.url}")

            try:
                # Validate URL
                if not validate_urls([url_config.url]):
                    self.logger.warning(f"⚠️ Skipping invalid URL: {url_config.url}")
                    continue

                # Determine portal from URL
                portal = self._detect_portal(url_config.url)
                if not portal:
                    self.logger.warning(f"⚠️ Unsupported portal for URL: {url_config.url}")
                    continue

                # Create appropriate crawler based on portal
                if portal == 'immoscout24':
                    crawler = ImmobilienScout24Crawler(
                        headless=self.headless,
                        debug=self.debug,
                        concurrency=self.concurrency,
                        proxy_country=self.input.proxyCountry
                    )
                elif portal == 'immowelt':
                    crawler = ImmoweltCrawler(
                        headless=self.headless,
                        debug=self.debug,
                        concurrency=self.concurrency,
                        proxy_country=self.input.proxyCountry
                    )
                else:
                    self.logger.warning(f"⚠️ Unsupported portal: {portal}")
                    continue

                async with crawler:
                    listings = await crawler.scrape_search_url(url_config.url, self.input.maxResults)
                    await self._process_listings(listings, portal)

            except Exception as error:
                self.logger.error(f"❌ Failed to process URL {url_config.url}: {error}")
                self.stats['failed_extractions'] += 1

    async def _process_search_builders(self) -> None:
        """Process programmatically built searches."""
        self.logger.info(f"🔨 Processing {len(self.input.searchBuilders)} search builders")

        for i, builder in enumerate(self.input.searchBuilders):
            self.logger.info(f"🏗️ Processing search builder {i+1}/{len(self.input.searchBuilders)}")

            try:
                # Process each portal in the builder and collect all listings
                portals = getattr(builder, 'portals', None) or ['immoscout24', 'immowelt']  # Default to both portals
                all_listings = []

                # Calculate maxResults per portal if multiple portals
                max_results_per_portal = self.input.maxResults
                if len(portals) > 1:
                    max_results_per_portal = max(1, self.input.maxResults // len(portals))
                    self.logger.info(f"🔢 Splitting {self.input.maxResults} results across {len(portals)} portals: {max_results_per_portal} each")

                for portal in portals:
                    if portal == 'immoscout24':
                        crawler = ImmobilienScout24Crawler(
                            headless=self.headless,
                            debug=self.debug,
                            concurrency=self.concurrency,
                            proxy_country=self.input.proxyCountry
                        )
                    elif portal == 'immowelt':
                        crawler = ImmoweltCrawler(
                            headless=self.headless,
                            debug=self.debug,
                            concurrency=self.concurrency,
                            proxy_country=self.input.proxyCountry
                        )
                    else:
                        self.logger.warning(f"⚠️ Portal {portal} not supported, skipping")
                        continue

                    async with crawler:
                        listings = await crawler.scrape_search_builder(builder, max_results_per_portal)
                        if listings:
                            all_listings.extend(listings)
                            self.logger.info(f"📊 Collected {len(listings)} listings from {portal}")

                # Now process all listings together (merge, sort, dedupe, save)
                if all_listings:
                    await self._process_merged_listings(all_listings)
                else:
                    self.logger.warning("⚠️ No listings collected from any portal")

            except Exception as error:
                self.logger.error(f"❌ Failed to process search builder: {error}")
                # Add more detailed error information
                import traceback
                self.logger.debug(f"Full traceback: {traceback.format_exc()}")
                self.stats['failed_extractions'] += 1

    async def _process_merged_listings(self, all_listings: List[PropertyListing]) -> None:
        """Process merged listings from multiple portals with sorting and deduplication."""
        if not all_listings:
            self.logger.warning("⚠️ No listings to process")
            return

        self.logger.info(f"🔀 Processing {len(all_listings)} merged listings from all portals")

        # Apply deduplication first
        deduplicated_listings = await self._deduplicate_listings(all_listings)
        self.logger.info(f"🔄 After deduplication: {len(deduplicated_listings)} listings")

        # Sort by posted date (newest first)
        sorted_listings = await self._sort_listings_by_date(deduplicated_listings)

        # Apply maxResults limit
        if len(sorted_listings) > self.input.maxResults:
            sorted_listings = sorted_listings[:self.input.maxResults]
            self.logger.info(f"🔢 Limited to {self.input.maxResults} most recent listings")

        # Save to dataset
        dataset = await Actor.open_dataset()

        for listing in sorted_listings:
            try:
                # Normalize and enhance data
                normalized_listing = normalize_property_data(listing, listing.source)

                # Save to dataset
                await dataset.push_data(normalized_listing)
                self.stats['successful_extractions'] += 1

                # Track if enabled
                if self.input.trackingMode:
                    self.seen_listings.add(f"{listing.source}_{listing.sourceId}")

            except Exception as error:
                self.logger.error(f"❌ Failed to save listing {listing.sourceId}: {error}")
                self.stats['failed_extractions'] += 1

        self.logger.info(f"💾 Saved {len(sorted_listings)} listings to dataset")

    async def _sort_listings_by_date(self, listings: List[PropertyListing]) -> List[PropertyListing]:
        """Sort listings by posted date (newest first)."""
        try:
            from datetime import datetime

            def get_sort_key(listing):
                """Get sorting key for a listing - use posted date or extraction date as fallback."""
                if listing.postedDate:
                    try:
                        # Try to parse various date formats
                        date_str = listing.postedDate

                        # Handle ISO format (YYYY-MM-DD)
                        if '-' in date_str and len(date_str.split('-')[0]) == 4:
                            return datetime.fromisoformat(date_str.split('T')[0])

                        # Handle German format (DD.MM.YYYY)
                        if '.' in date_str:
                            parts = date_str.split('.')
                            if len(parts) == 3:
                                return datetime(int(parts[2]), int(parts[1]), int(parts[0]))

                        # Handle other formats with dateutil if available
                        try:
                            from dateutil import parser as date_parser
                            return date_parser.parse(date_str, fuzzy=True)
                        except (ImportError, ValueError):
                            pass

                    except (ValueError, IndexError) as e:
                        self.logger.debug(f"⚠️ Could not parse posted date '{listing.postedDate}' for listing {listing.sourceId}: {e}")

                # Fallback to extraction date
                try:
                    return datetime.fromisoformat(listing.extractedDate.split('T')[0])
                except (ValueError, AttributeError):
                    # Ultimate fallback to current time
                    return datetime.now()

            # Sort by date (newest first)
            sorted_listings = sorted(listings, key=get_sort_key, reverse=True)

            # Log sorting info
            for i, listing in enumerate(sorted_listings[:5]):  # Log first 5 for debugging
                date_used = listing.postedDate or listing.extractedDate
                self.logger.debug(f"📅 #{i+1}: {listing.title[:50]}... - Date: {date_used}")

            self.logger.info(f"📅 Sorted {len(sorted_listings)} listings by date (newest first)")
            return sorted_listings

        except Exception as error:
            self.logger.warning(f"⚠️ Error sorting listings by date: {error}")
            # Return original order as fallback
            return listings

    async def _process_listings(self, listings: List[PropertyListing], source_portal: str) -> None:
        """Process and save extracted listings."""
        if not listings:
            self.logger.warning("⚠️ No listings extracted")
            return

        self.logger.info(f"📊 Processing {len(listings)} listings from {source_portal}")

        # Apply deduplication
        deduplicated_listings = await self._deduplicate_listings(listings)

        # Save to dataset
        dataset = await Actor.open_dataset()

        for listing in deduplicated_listings:
            try:
                # Normalize and enhance data
                normalized_listing = normalize_property_data(listing, source_portal)

                # Save to dataset
                await dataset.push_data(normalized_listing)
                self.stats['successful_extractions'] += 1

                # Track if enabled
                if self.input.trackingMode:
                    self.seen_listings.add(f"{listing.source}_{listing.sourceId}")

            except Exception as error:
                self.logger.error(f"❌ Failed to save listing {listing.sourceId}: {error}")
                self.stats['failed_extractions'] += 1

        self.logger.info(f"💾 Saved {len(deduplicated_listings)} listings to dataset")

    async def _deduplicate_listings(self, listings: List[PropertyListing]) -> List[PropertyListing]:
        """Apply deduplication based on configured level."""
        if self.input.dedupeLevel == 'none':
            return listings

        original_count = len(listings)
        deduplicated = []
        seen_ids = set()

        for listing in listings:
            # Generate deduplication key based on level
            if self.dedupe_level == 'portal':
                dedup_key = f"{listing.source}_{listing.sourceId}"
            elif self.dedupe_level == 'cross_portal':
                dedup_key = f"{listing.source}_{listing.sourceId}"  # Use source+sourceId for cross-portal deduplication
            else:  # none
                dedup_key = f"{listing.source}_{listing.sourceId}_{id(listing)}"  # Make each listing unique

            if dedup_key not in seen_ids:
                seen_ids.add(dedup_key)
                deduplicated.append(listing)
            else:
                self.stats['duplicates_removed'] += 1

        removed_count = original_count - len(deduplicated)
        if removed_count > 0:
            self.logger.info(f"🔄 Removed {removed_count} duplicate listings")

        return deduplicated

    def _detect_portal(self, url: str) -> Optional[str]:
        """Detect which portal a URL belongs to."""
        if 'immobilienscout24.de' in url:
            return 'immoscout24'
        elif 'immonet.de' in url:
            return 'immonet'
        elif 'immowelt.de' in url:
            return 'immowelt'
        return None

    async def _save_statistics(self) -> None:
        """Save execution statistics."""
        end_time = datetime.now(timezone.utc)
        duration = (end_time - self.stats['start_time']).total_seconds()

        final_stats = {
            **self.stats,
            'end_time': end_time,
            'duration_seconds': duration,
            'success_rate': (
                self.stats['successful_extractions'] /
                max(self.stats['total_processed'], 1) * 100
            )
        }

        await Actor.set_value('STATS', final_stats)

        # Save state for tracking mode
        if self.input.trackingMode:
            state = {
                'seen_listings': list(self.seen_listings),
                'last_run': end_time.isoformat()
            }
            await Actor.set_value('STATE', state)

        self.logger.info(f"📈 Final Statistics: {final_stats}")


async def main() -> None:
    """Main entry point for the actor."""
    async with Actor:
        # Get and validate input
        raw_input = await Actor.get_input() or {}

        try:
            input_data = ActorInput(**raw_input)
            logging.info(f"✅ Input validation successful. QuickSearch: {input_data.quickSearch}")
        except ValidationError as error:
            logging.error(f"❌ Invalid input configuration: {error}")
            await Actor.fail()
            return

        # Create and run actor
        actor = ImmobilienProActor(input_data)
        await actor.initialize()
        await actor.run()


if __name__ == "__main__":
    asyncio.run(main())