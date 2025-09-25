"""
Type definitions for the Immobiliensuche Pro Python actor.
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator


class SearchUrl(BaseModel):
    """Search URL configuration."""
    url: str = Field(..., description="Portal search URL")


class SearchBuilder(BaseModel):
    """User-friendly search builder configuration."""
    portals: Optional[List[str]] = Field(default=['immoscout24'], description="Target portals")
    dealType: str = Field(..., description="rent or sale")
    propertyTypes: Optional[List[str]] = Field(default=None, description="Property types to search")
    regions: List[str] = Field(..., description="Cities or regions to search")
    radiusKm: Optional[int] = Field(default=10, description="Search radius in kilometers")
    priceMin: Optional[int] = Field(default=None, description="Minimum price in EUR")
    priceMax: Optional[int] = Field(default=None, description="Maximum price in EUR")
    sizeMin: Optional[int] = Field(default=None, description="Minimum size in sqm")
    roomsMin: Optional[int] = Field(default=None, description="Minimum number of rooms")
    roomsMax: Optional[int] = Field(default=None, description="Maximum number of rooms")
    furnished: Optional[str] = Field(default=None, description="furnished, unfurnished, partly_furnished")
    features: Optional[List[str]] = Field(default=[], description="Desired features like balcony, parking, etc.")
    postedSinceDays: Optional[int] = Field(default=None, description="Posted within last N days")


class AdvancedOptions(BaseModel):
    """Advanced technical options."""
    concurrency: Optional[int] = Field(default=1, description="Browser concurrency")
    debug: Optional[bool] = Field(default=False, description="Debug mode")
    headless: Optional[bool] = Field(default=True, description="Headless browser mode")


class ActorInput(BaseModel):
    """Main actor input configuration."""
    quickSearch: Optional[str] = Field(default="Young Professional", description="Quick search template")
    searchUrls: Optional[List[SearchUrl]] = Field(default=[], description="Direct search URLs")
    searchBuilders: Optional[List[SearchBuilder]] = Field(default=[], description="Search builders")
    maxResults: Optional[int] = Field(default=100, description="Maximum results to extract")
    trackingMode: Optional[bool] = Field(default=False, description="Enable change tracking")
    removeDuplicates: Optional[bool] = Field(default=True, description="Remove duplicate listings")
    advancedOptions: Optional[AdvancedOptions] = Field(default=None, description="Advanced technical options")

    # Legacy fields for backward compatibility
    dedupeLevel: Optional[str] = Field(default='cross_portal', description="Deduplication level")
    concurrency: Optional[int] = Field(default=1, description="Browser concurrency")
    proxyCountry: Optional[str] = Field(default='DE', description="Proxy country")
    complianceMode: Optional[bool] = Field(default=True, description="Compliance mode")
    debug: Optional[bool] = Field(default=False, description="Debug mode")
    headless: Optional[bool] = Field(default=True, description="Headless browser mode")

    @validator('dedupeLevel')
    def validate_dedupe_level(cls, v):
        if v and v not in ['none', 'portal', 'cross_portal']:
            raise ValueError('dedupeLevel must be one of: none, portal, cross_portal')
        return v

    @validator('proxyCountry')
    def validate_proxy_country(cls, v):
        if v and v not in ['DE', 'AUTO']:
            raise ValueError('proxyCountry must be DE or AUTO')
        return v

    @validator('quickSearch')
    def validate_quick_search(cls, v):
        valid_templates = ["Student Room", "Young Professional", "Family Apartment", "Luxury Home", "Investment Property", "Custom"]
        if v and v not in valid_templates:
            raise ValueError(f'quickSearch must be one of: {valid_templates}')
        return v


class PriceInfo(BaseModel):
    """Price information structure."""
    total: Optional[float] = None
    currency: str = 'EUR'
    type: Optional[str] = None  # kalt, warm, kaufpreis
    extra: Optional[Dict[str, float]] = None


class SizeInfo(BaseModel):
    """Property size information."""
    livingSqm: Optional[float] = None
    plotSqm: Optional[float] = None


class AddressInfo(BaseModel):
    """Address information structure."""
    raw: Optional[str] = None
    street: Optional[str] = None
    houseNo: Optional[str] = None
    postcode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = 'DE'


class GeoInfo(BaseModel):
    """Geographic coordinates."""
    lat: Optional[float] = None
    lng: Optional[float] = None


class ContactInfo(BaseModel):
    """Contact information."""
    name: Optional[str] = None
    phone: Optional[str] = None
    agency: Optional[str] = None


class EnergyInfo(BaseModel):
    """Energy efficiency information."""
    efficiencyClass: Optional[str] = None
    consumption: Optional[float] = None
    heatingType: Optional[str] = None


class DateInfo(BaseModel):
    """Listing date information."""
    postedAt: Optional[str] = None
    updatedAt: Optional[str] = None
    extractedAt: str = Field(default_factory=lambda: datetime.now().isoformat())


class ComputedMetrics(BaseModel):
    """Computed metrics for analysis."""
    pricePerSqm: Optional[float] = None
    totalMonthlyCost: Optional[float] = None


class DedupeInfo(BaseModel):
    """Deduplication metadata."""
    fingerprints: List[str] = []
    alternativeSources: List[Dict[str, str]] = []


class PropertyListing(BaseModel):
    """Simplified property listing structure for better readability."""
    # Required fields
    source: str = Field(..., description="Source portal")
    sourceId: str = Field(..., description="Portal-specific ID")
    url: str = Field(..., description="Listing URL")
    title: str = Field(..., description="Property title")
    dealType: str = Field(..., description="rent or sale")
    propertyType: str = Field(..., description="apartment, house, etc.")

    # Core property details (simplified)
    description: Optional[str] = None
    address: Optional[str] = None  # Single formatted address string
    price: Optional[float] = None  # Just the number, always EUR
    size: Optional[float] = None   # Living space in sqm
    rooms: Optional[int] = None
    floor: Optional[int] = None
    yearBuilt: Optional[int] = None
    condition: Optional[str] = None

    # Computed metrics (flattened)
    pricePerSqm: Optional[float] = None

    # Additional information
    features: List[str] = []
    images: List[str] = []

    # Contact info (flattened)
    contactName: Optional[str] = None
    contactPhone: Optional[str] = None
    contactAgency: Optional[str] = None

    # Dates (simplified)
    postedDate: Optional[str] = None
    extractedDate: str = Field(default_factory=lambda: datetime.now().isoformat())


class ScrapingResult(BaseModel):
    """Result from a scraping operation."""
    success: bool
    listings: List[PropertyListing] = []
    error: Optional[str] = None
    stats: Dict[str, Any] = {}


class BrowserConfig(BaseModel):
    """Browser configuration for nodriver."""
    headless: bool = True
    user_data_dir: Optional[str] = None
    proxy: Optional[str] = None
    window_size: tuple = (1920, 1080)
    user_agent: Optional[str] = None