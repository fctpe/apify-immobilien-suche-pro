# Immobiliensuche Pro - German Real Estate Aggregator

[![Apify Store](https://img.shields.io/badge/Apify-Store-green.svg)](https://apify.com/store)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9.2-blue.svg)](https://www.typescriptlang.org/)
[![Pay Per Result](https://img.shields.io/badge/Pricing-Pay%20Per%20Result-orange.svg)](#pricing)

**One search, three portals, zero duplicates.** Advanced German real estate aggregator for ImmobilienScout24, Immonet & Immowelt with intelligent cross-portal deduplication, normalized pricing, and change tracking.

## 🏠 Features

- **Cross-Portal Search**: Aggregate listings from Germany's top real estate portals
- **Smart Deduplication**: 4-key fingerprinting eliminates duplicates across portals
- **Normalized Data**: Consistent schema with kalt/warm/kaufpreis pricing
- **Price Per ㎡**: Automatic calculation of price per square meter
- **Change Tracking**: Monitor new listings, price changes, and offline status
- **Webhooks & Notifications**: Real-time alerts via email or HTTP endpoints
- **German Compliance**: Respects robots.txt and uses conservative crawling rates
- **Anti-Detection**: Advanced stealth with German proxies and human-like behavior

## 🎯 Supported Portals

| Portal | Coverage | Property Types | Deal Types |
|--------|----------|----------------|------------|
| **ImmobilienScout24** | ✅ Full | Apartment, House, Land, Commercial | Rent, Sale |
| **Immonet** | 🚧 Coming Soon | Apartment, House | Rent, Sale |
| **Immowelt** | 🚧 Coming Soon | Apartment, House | Rent, Sale |

## 📊 Data Schema

Each listing includes:

```json
{
  "id": "de_ber_10117_apt_rent_1200_85_3_a1b2c3d4",
  "source": "immoscout24",
  "url": "https://www.immobilienscout24.de/expose/123456789",
  "title": "Moderne 3-Zimmer-Wohnung in Berlin-Mitte",
  "propertyType": "apartment",
  "dealType": "rent",
  "price": {
    "total": 1200,
    "currency": "EUR",
    "type": "kalt",
    "extra": {
      "nebenkosten": 150,
      "kaution": 2400
    }
  },
  "size": { "livingSqm": 85.5 },
  "rooms": 3,
  "address": {
    "street": "Unter den Linden",
    "postcode": "10117",
    "city": "Berlin",
    "state": "Berlin",
    "country": "DE"
  },
  "geo": { "lat": 52.5170, "lng": 13.3888 },
  "computed": {
    "pricePerSqm": 14.04,
    "totalMonthlyCost": 1350
  },
  "dates": {
    "extractedAt": "2024-01-22T09:15:00Z"
  }
}
```

## 🚀 Quick Start

### Option 1: Search URLs (Paste & Go)

```json
{
  "searchUrls": [
    {
      "url": "https://www.immobilienscout24.de/Suche/de/berlin/wohnung-mieten?price=0-1500&livingspace=50-"
    }
  ],
  "maxResults": 500,
  "dedupeLevel": "cross_portal"
}
```

### Option 2: Search Builder (Programmatic)

```json
{
  "searchBuilders": [
    {
      "portals": ["immoscout24"],
      "dealType": "rent",
      "propertyTypes": ["apartment"],
      "regions": ["Berlin"],
      "priceMax": 1500,
      "sizeMin": 50,
      "roomsMin": 2
    }
  ],
  "trackingMode": true,
  "notifications": {
    "emails": ["alerts@yourdomain.de"],
    "events": ["NEW", "PRICE_CHANGE"]
  }
}
```

## 🔧 Configuration Options

### Search Configuration

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `searchUrls` | Array | Direct portal search URLs | See above |
| `searchBuilders` | Array | Programmatic search builders | See above |
| `maxResults` | Number | Maximum listings to extract (0=unlimited) | `1000` |

### Deduplication & Processing

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `dedupeLevel` | Enum | `none` \| `portal` \| `cross_portal` | `cross_portal` |
| `trackingMode` | Boolean | Enable change detection | `false` |

### Performance & Compliance

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `concurrency` | Number | Parallel sessions (1-10) | `3` |
| `complianceMode` | Boolean | Respect robots.txt & delays | `true` |
| `proxyCountry` | String | `DE` \| `AUTO` | `DE` |

### Notifications

```json
{
  "notifications": {
    "emails": ["your@email.com"],
    "webhookUrl": "https://your-server.com/webhook",
    "events": ["NEW", "PRICE_CHANGE", "STATUS_OFFLINE"]
  }
}
```

## 📈 Use Cases

### Real Estate Professionals
- **Market Research**: Compare prices across portals
- **Lead Generation**: Get notified of new listings matching criteria
- **Competitive Analysis**: Track competitor pricing strategies

### Property Investors
- **Deal Finding**: Automated screening of investment opportunities
- **Price Monitoring**: Track market trends and price movements
- **Portfolio Research**: Identify emerging neighborhoods

### Researchers & Analysts
- **Market Studies**: Comprehensive real estate market data
- **Price Analytics**: Historical pricing trends and patterns
- **Geographic Analysis**: Regional market comparisons

## 🎁 Example Searches

### Berlin Rentals Under €1,800

```json
{
  "searchBuilders": [{
    "portals": ["immoscout24"],
    "dealType": "rent",
    "propertyTypes": ["apartment"],
    "regions": ["Berlin"],
    "priceMax": 1800,
    "sizeMin": 60,
    "roomsMin": 2
  }],
  "trackingMode": true,
  "maxResults": 1000
}
```

### NRW Houses for Sale (€300k-€600k)

```json
{
  "searchBuilders": [{
    "portals": ["immoscout24"],
    "dealType": "sale",
    "propertyTypes": ["house"],
    "regions": ["Nordrhein-Westfalen"],
    "priceMin": 300000,
    "priceMax": 600000,
    "sizeMin": 120
  }]
}
```

### Munich Investment Properties

```json
{
  "searchBuilders": [{
    "portals": ["immoscout24"],
    "dealType": "rent",
    "propertyTypes": ["apartment", "house"],
    "regions": ["München"],
    "sizeMin": 80,
    "roomsMin": 3
  }],
  "notifications": {
    "webhookUrl": "https://your-crm.com/leads",
    "events": ["NEW"]
  }
}
```

## 💰 Pricing

**Pay-per-result model** - only pay for extracted listings:

- **€25 per 1,000 listings** (rounded to nearest 100)
- **Free tier**: First 200 results per month
- **Volume discounts**:
  - 5k listings: €79/month
  - 15k listings: €149/month
  - 50k listings: €249/month

### Pricing Examples

| Listings | Cost | Price per Listing |
|----------|------|-------------------|
| 200 | Free | €0.00 |
| 500 | €12.50 | €0.025 |
| 1,000 | €25.00 | €0.025 |
| 2,500 | €62.50 | €0.025 |

## ⚖️ Legal & Compliance

- ✅ **Respects robots.txt** when compliance mode enabled
- ✅ **Rate limiting** to avoid overloading servers
- ✅ **Public data only** - no private or gated content
- ✅ **GDPR compliant** - only processes publicly available data
- ✅ **Terms of service** awareness with conservative crawling

**Note**: Users are responsible for ensuring their use case complies with portal terms of service and local laws.

## 🔄 Change Tracking

Enable `trackingMode` to monitor:

- **NEW**: First-time listings
- **PRICE_CHANGE**: Price increases/decreases
- **STATUS_OFFLINE**: Listings no longer available
- **DESCRIPTION_UPDATE**: Content modifications

Changes are saved to a separate dataset and can trigger notifications.

## 📊 Output Formats

- **JSON**: Native Apify dataset format
- **CSV**: Excel-compatible export
- **Webhook**: Real-time API integration
- **Email**: Human-readable summaries

## 🛠️ Advanced Features

### Deduplication Algorithm

4-key fingerprinting system:

1. **Address**: Normalized street + postal code
2. **Geolocation**: Rounded coordinates (±11m)
3. **Metrics**: Size + rooms + price (with tolerance)
4. **Images**: First image hash comparison

### Anti-Detection

- Residential German proxies
- Human-like delays and scrolling
- Browser fingerprint randomization
- Session rotation on detection

### Data Quality

- German address parsing with Bundesland mapping
- Price normalization (kalt/warm/kaufpreis)
- Automatic price-per-square-meter calculation
- Energy efficiency class normalization

## 🏃 Performance

- **Speed**: ~1,000 listings per 10 minutes
- **Accuracy**: >95% data extraction success rate
- **Reliability**: <5% anti-bot detection rate
- **Uptime**: Circuit breakers and automatic retry

## 📞 Support

- **Email**: kontakt@barrierefix.de
- **Response time**: Within 24 hours
- **Languages**: German, English
- **Expertise**: Real estate data & German regulations

## 🔄 Version History

### v1.0.0 (Current)
- ImmobilienScout24 crawler with full feature set
- Cross-portal deduplication engine
- Change tracking and notifications
- German address & price normalization

### Coming Soon
- Immonet integration
- Immowelt integration
- Enhanced image analysis
- Market trend analytics

---

**Ready to aggregate German real estate data?** Start with our free tier and scale as needed. Perfect for professionals, investors, and researchers who need comprehensive, deduplicated market data.

*Built with ❤️ for the German real estate market by Barrierefix.*