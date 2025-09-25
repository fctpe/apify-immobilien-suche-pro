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

                # Create crawler and extract listings
                crawler = ImmobilienScout24Crawler(
                    headless=self.headless,
                    debug=self.debug,
                    concurrency=self.concurrency,
                    proxy_country=self.input.proxyCountry
                )

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
                # Process each portal in the builder
                portals = builder.portals or ['immoscout24']  # Default to ImmobilienScout24

                for portal in portals:
                    if portal != 'immoscout24':
                        self.logger.warning(f"⚠️ Portal {portal} not yet implemented, skipping")
                        continue

                    # Create crawler and build search
                    crawler = ImmobilienScout24Crawler(
                        headless=self.headless,
                        debug=self.debug,
                        concurrency=self.concurrency,
                        proxy_country=self.input.proxyCountry
                    )

                    async with crawler:
                        listings = await crawler.scrape_search_builder(builder)
                        await self._process_listings(listings, portal)

            except Exception as error:
                self.logger.error(f"❌ Failed to process search builder: {error}")
                self.stats['failed_extractions'] += 1

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
        except ValidationError as error:
            logging.error(f"❌ Invalid input configuration: {error}")
            await Actor.fail("Invalid input configuration. Please check your input parameters.")
            return

        # Create and run actor
        actor = ImmobilienProActor(input_data)
        await actor.initialize()
        await actor.run()


if __name__ == "__main__":
    asyncio.run(main())