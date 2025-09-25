"""
Utility functions for the Immobiliensuche Pro Python actor.
"""

import hashlib
import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from datetime import datetime, timezone

import coloredlogs
from dateutil import parser as date_parser

from types_def import PropertyListing, PriceInfo, AddressInfo, ComputedMetrics


def setup_logging(debug: bool = False) -> None:
    """Setup colored logging with appropriate level."""
    level = logging.DEBUG if debug else logging.INFO

    coloredlogs.install(
        level=level,
        fmt='%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s',
        level_styles={
            'debug': {'color': 'cyan'},
            'info': {'color': 'green'},
            'warning': {'color': 'yellow'},
            'error': {'color': 'red', 'bold': True},
            'critical': {'color': 'red', 'bold': True, 'background': 'yellow'},
        }
    )

    # Reduce verbosity of external libraries
    logging.getLogger('nodriver').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('crawlee').setLevel(logging.INFO)


def validate_urls(urls: List[str]) -> bool:
    """Validate if URLs are from supported German real estate portals."""
    supported_domains = [
        'immobilienscout24.de',
        'immonet.de',
        'immowelt.de'
    ]

    for url in urls:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            if not any(supported in domain for supported in supported_domains):
                return False

        except Exception:
            return False

    return True


def generate_canonical_id(
    source: str,
    source_id: str,
    property_type: str,
    deal_type: str,
    location_key: str
) -> str:
    """Generate canonical ID for cross-portal deduplication."""
    # Create deterministic hash from key properties
    key_data = f"{location_key}_{property_type}_{deal_type}_{source_id}"
    hash_suffix = hashlib.md5(key_data.encode()).hexdigest()[:8]

    # Format: country_city_id_type_deal_hash
    return f"de_{location_key}_{source_id}_{property_type}_{deal_type}_{hash_suffix}"


def extract_location_key(address: Optional[str]) -> str:
    """Extract location key for canonical ID generation from address string."""
    if not address:
        return "unknown"

    # For simplified version, just use a hash of the address string
    # This provides consistent deduplication without needing structured data
    import hashlib
    return hashlib.md5(address.lower().encode()).hexdigest()[:8]


def normalize_property_data(listing: PropertyListing, source_portal: str) -> Dict[str, Any]:
    """Normalize property listing data for consistent output."""
    # Generate canonical ID for deduplication (no longer stored in model)
    location_key = extract_location_key(listing.address) if listing.address else ""
    canonical_id = generate_canonical_id(
        listing.source,
        listing.sourceId,
        listing.propertyType,
            listing.dealType,
            location_key
        )

    # pricePerSqm is already calculated directly in the simplified model
    # No need to compute derived metrics as they are now part of the flat structure

    # Ensure extraction timestamp - already handled by default in PropertyListing model
    # listing.extractedDate is automatically set by default_factory in the model

    return listing.dict(exclude_none=True)


def extract_price_from_text(text: str) -> Optional[float]:
    """Extract price from German text."""
    if not text:
        return None

    # Remove currency symbols and spaces
    clean_text = re.sub(r'[€\s]', '', text)

    # Handle German decimal separators
    clean_text = clean_text.replace('.', '').replace(',', '.')

    # Extract number
    match = re.search(r'(\d+(?:\.\d{1,2})?)', clean_text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return None


def extract_area_from_text(text: str) -> Optional[float]:
    """Extract area in square meters from German text."""
    if not text:
        return None

    # Look for patterns like "85,5 m²" or "85.5m²"
    pattern = r'(\d+(?:[,.]\d+)?)\s*m²?'
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        try:
            # Handle German decimal separator
            area_str = match.group(1).replace(',', '.')
            return float(area_str)
        except ValueError:
            pass

    return None


def extract_rooms_from_text(text: str) -> Optional[int]:
    """Extract number of rooms from German text."""
    if not text:
        return None

    # Look for patterns like "3 Zimmer" or "3-Zimmer"
    pattern = r'(\d+)(?:\s*[-.]?\s*(?:Zimmer|Zi\.?))'
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    return None


def parse_german_date(date_str: str) -> Optional[str]:
    """Parse German date strings to ISO format."""
    if not date_str:
        return None

    try:
        # Handle various German date formats
        date_str = date_str.strip()

        # Convert German month names
        german_months = {
            'januar': 'january', 'januar.': 'january',
            'februar': 'february', 'februar.': 'february', 'feb.': 'february',
            'märz': 'march', 'märz.': 'march', 'mär.': 'march',
            'april': 'april', 'april.': 'april', 'apr.': 'april',
            'mai': 'may', 'mai.': 'may',
            'juni': 'june', 'juni.': 'june', 'jun.': 'june',
            'juli': 'july', 'juli.': 'july', 'jul.': 'july',
            'august': 'august', 'august.': 'august', 'aug.': 'august',
            'september': 'september', 'september.': 'september', 'sep.': 'september',
            'oktober': 'october', 'oktober.': 'october', 'okt.': 'october',
            'november': 'november', 'november.': 'november', 'nov.': 'november',
            'dezember': 'december', 'dezember.': 'december', 'dez.': 'december'
        }

        date_str_lower = date_str.lower()
        for german, english in german_months.items():
            date_str_lower = date_str_lower.replace(german, english)

        # Parse the date
        parsed_date = date_parser.parse(date_str_lower, fuzzy=True)
        return parsed_date.isoformat()

    except Exception:
        return None


def normalize_property_type(raw_type: str) -> str:
    """Normalize property type to standard values."""
    if not raw_type:
        return 'unknown'

    raw_type = raw_type.lower().strip()

    # Apartment types
    if any(word in raw_type for word in ['wohnung', 'apartment', 'etw', 'eigentumswohnung']):
        return 'apartment'

    # House types
    if any(word in raw_type for word in ['haus', 'einfamilienhaus', 'reihenhaus', 'villa', 'doppelhaus']):
        return 'house'

    # Land
    if any(word in raw_type for word in ['grundstück', 'bauland', 'land']):
        return 'land'

    # Commercial
    if any(word in raw_type for word in ['büro', 'gewerbe', 'laden', 'praxis', 'commercial']):
        return 'commercial'

    return 'other'


def normalize_deal_type(raw_deal: str) -> str:
    """Normalize deal type to rent or sale."""
    if not raw_deal:
        return 'unknown'

    raw_deal = raw_deal.lower().strip()

    if any(word in raw_deal for word in ['miete', 'mieten', 'rent', 'vermietung']):
        return 'rent'

    if any(word in raw_deal for word in ['kauf', 'kaufen', 'verkauf', 'verkaufen', 'sale', 'eigentum']):
        return 'sale'

    return 'unknown'


def clean_html_text(html_text: str) -> str:
    """Clean HTML text content."""
    if not html_text:
        return ""

    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', html_text)

    # Normalize whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text)

    return clean_text.strip()


def extract_from_nodriver_result(data):
    """Extract values from nodriver's complex result structure"""
    if isinstance(data, list) and len(data) > 0:
        # Handle nested array structure from nodriver
        result_dict = {}
        for item in data:
            if isinstance(item, list) and len(item) == 2:
                key, value = item
                if isinstance(value, dict) and 'value' in value:
                    if value.get('type') == 'array':
                        # Extract array values
                        array_items = []
                        for array_item in value['value']:
                            if isinstance(array_item, dict) and 'value' in array_item:
                                array_items.append(array_item['value'])
                        result_dict[key] = array_items
                    else:
                        result_dict[key] = value['value']
        return result_dict
    elif isinstance(data, dict):
        return data
    return data


def build_deduplication_fingerprint(listing: PropertyListing) -> str:
    """Build fingerprint for deduplication."""
    key_parts = [
        listing.title.lower() if listing.title else "",
        str(listing.price.total) if listing.price and listing.price.total else "",
        str(listing.size.livingSqm) if listing.size and listing.size.livingSqm else "",
        str(listing.rooms) if listing.rooms else "",
        listing.address.postcode if listing.address and listing.address.postcode else ""
    ]

    combined = "_".join(filter(None, key_parts))
    return hashlib.md5(combined.encode()).hexdigest()


def get_user_agents() -> List[str]:
    """Get list of realistic user agents for rotation."""
    return [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    ]