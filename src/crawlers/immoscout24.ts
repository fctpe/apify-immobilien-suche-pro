import { Page } from 'playwright';
import { RealEstateListing, SearchBuilder, PortalCrawler, CrawlerOptions } from '../types';
import { GermanAddressParser, GermanNumberParser, PropertyNormalizer } from '../utils/normalization';
import { StealthManager, CircuitBreaker, RateLimitManager } from '../anti-detection/stealth';
import { DateTime } from 'luxon';

export class ImmobilienScout24Crawler implements PortalCrawler {
  name = 'immoscout24';
  private circuitBreaker = new CircuitBreaker(5, 120000);
  private rateLimiter = new RateLimitManager(20, 3000);

  async crawl(searchParams: any, options: CrawlerOptions): Promise<RealEstateListing[]> {
    return await this.circuitBreaker.execute(async () => {
      return await this.crawlInternal(searchParams, options);
    });
  }

  private async crawlInternal(searchParams: any, options: CrawlerOptions): Promise<RealEstateListing[]> {
    const { page } = searchParams;
    const { maxResults = 1000, debug = false } = options;

    const listings: RealEstateListing[] = [];
    let currentPage = 1;
    let hasMorePages = true;

    while (hasMorePages && listings.length < maxResults) {
      await this.rateLimiter.waitForSlot('immobilienscout24.de');

      try {
        const pageListings = await this.scrapePage(page, currentPage, debug);
        listings.push(...pageListings);

        if (debug) {
          console.log(`ImmobilienScout24: Page ${currentPage} - Found ${pageListings.length} listings`);
        }

        hasMorePages = await this.hasNextPage(page);
        if (hasMorePages) {
          await this.goToNextPage(page, currentPage + 1);
          currentPage++;
        }

        await StealthManager.humanLikeDelay(2000, 4000);

      } catch (error: any) {
        console.error(`Error scraping ImmobilienScout24 page ${currentPage}:`, error.message);

        if (error.message.includes('blocked') || error.message.includes('403')) {
          throw new Error('ImmobilienScout24: Access blocked - stopping crawl');
        }

        hasMorePages = false;
      }
    }

    return listings.slice(0, maxResults);
  }

  private async scrapePage(page: Page, pageNum: number, debug: boolean): Promise<RealEstateListing[]> {
    await page.waitForLoadState('networkidle', { timeout: 30000 });

    const listingElements = await page.locator('[data-item="result"]').all();

    if (listingElements.length === 0) {
      if (debug) {
        await page.screenshot({ path: `debug_immoscout24_page_${pageNum}.png` });
      }
      throw new Error('No listings found - possible detection');
    }

    const listings: RealEstateListing[] = [];

    for (const element of listingElements) {
      try {
        const listing = await this.extractListing(element, page);
        if (listing) {
          listings.push(listing);
        }
      } catch (error: any) {
        console.warn(`Failed to extract ImmobilienScout24 listing:`, error.message);
      }
    }

    return listings;
  }

  private async extractListing(element: any, page: Page): Promise<RealEstateListing | null> {
    try {
      const titleEl = await element.locator('[data-qa="result-list-entry-title"] a').first();
      const title = await titleEl.textContent();
      const url = await titleEl.getAttribute('href');

      if (!title || !url) {
        return null;
      }

      const fullUrl = url.startsWith('http') ? url : `https://www.immobilienscout24.de${url}`;

      const addressText = await element.locator('[data-qa="result-list-entry-address"]').textContent() || '';
      const priceText = await element.locator('[data-qa="result-list-entry-price"]').textContent() || '';
      const areaText = await element.locator('[data-qa="result-list-entry-area"]').textContent() || '';
      const roomsText = await element.locator('[data-qa="result-list-entry-rooms"]').textContent() || '';

      const dealType = this.extractDealType(fullUrl, title);
      const propertyType = PropertyNormalizer.normalizePropertyType(title);

      const priceInfo = PropertyNormalizer.normalizePriceType(priceText, dealType);
      const address = GermanAddressParser.parseAddress(addressText);

      const listing: RealEstateListing = {
        id: '', // Will be set later
        source: 'immoscout24',
        sourceId: this.extractSourceId(fullUrl),
        url: fullUrl,
        title: title.trim(),
        propertyType,
        dealType,
        price: {
          total: priceInfo.amount,
          currency: 'EUR',
          type: priceInfo.type
        },
        address,
        dates: {
          extractedAt: DateTime.now().toISO()
        }
      };

      if (areaText) {
        const livingArea = GermanNumberParser.parseArea(areaText);
        if (livingArea > 0) {
          listing.size = { livingSqm: livingArea };
        }
      }

      if (roomsText) {
        const rooms = GermanNumberParser.parseRooms(roomsText);
        if (rooms > 0) {
          listing.rooms = rooms;
        }
      }

      listing.computed = PropertyNormalizer.computeMetrics(listing);
      listing.id = PropertyNormalizer.generateCanonicalId(listing);

      return listing;

    } catch (error: any) {
      console.warn('Failed to extract ImmobilienScout24 listing:', error.message);
      return null;
    }
  }

  private extractDealType(url: string, title: string): 'rent' | 'sale' {
    if (url.includes('mieten') || title.toLowerCase().includes('miete')) {
      return 'rent';
    }
    if (url.includes('kaufen') || title.toLowerCase().includes('kauf')) {
      return 'sale';
    }
    return 'rent'; // Default fallback
  }

  private extractSourceId(url: string): string | undefined {
    const match = url.match(/expose\/(\d+)/);
    return match ? match[1] : undefined;
  }

  private async hasNextPage(page: Page): Promise<boolean> {
    try {
      const nextButton = page.locator('[data-qa="paging-next"]');
      return await nextButton.isVisible() && await nextButton.isEnabled();
    } catch {
      return false;
    }
  }

  private async goToNextPage(page: Page, targetPage: number): Promise<void> {
    try {
      const nextButton = page.locator('[data-qa="paging-next"]');

      if (await nextButton.isVisible()) {
        await StealthManager.humanLikeClick(page, '[data-qa="paging-next"]');
        await page.waitForLoadState('networkidle', { timeout: 30000 });
        await StealthManager.humanLikeDelay(1000, 3000);
      } else {
        throw new Error('Next page button not found');
      }
    } catch (error: any) {
      throw new Error(`Failed to navigate to page ${targetPage}: ${error.message}`);
    }
  }

  buildSearchUrl(builder: SearchBuilder): string[] {
    const baseUrl = 'https://www.immobilienscout24.de/Suche/de';
    const urls: string[] = [];

    for (const region of builder.regions) {
      for (const propertyType of builder.propertyTypes) {
        const params = new URLSearchParams();

        // Property type mapping
        if (propertyType === 'apartment') {
          params.set('objecttypes', 'apartment');
        } else if (propertyType === 'house') {
          params.set('objecttypes', 'house');
        }

        // Deal type
        const dealSegment = builder.dealType === 'rent' ? 'mieten' : 'kaufen';
        const typeSegment = propertyType === 'apartment' ? 'wohnung' : 'haus';

        // Price range
        if (builder.priceMin && builder.priceMin > 0) {
          params.set('price', builder.priceMin.toString());
        }
        if (builder.priceMax && builder.priceMax > 0) {
          params.set('pricetype', 'rentpermonth');
          params.set('pricemax', builder.priceMax.toString());
        }

        // Size
        if (builder.sizeMin && builder.sizeMin > 0) {
          params.set('livingspace', builder.sizeMin.toString());
        }

        // Rooms
        if (builder.roomsMin && builder.roomsMin > 0) {
          params.set('numberofrooms', builder.roomsMin.toString());
        }

        const regionSlug = region.toLowerCase().replace(/\s+/g, '-');
        const searchUrl = `${baseUrl}/${regionSlug}/${typeSegment}-${dealSegment}?${params.toString()}`;
        urls.push(searchUrl);
      }
    }

    return urls;
  }

  async enhanceWithDetails(listing: RealEstateListing, page: Page): Promise<RealEstateListing> {
    try {
      await this.rateLimiter.waitForSlot('immobilienscout24.de');
      await page.goto(listing.url, { waitUntil: 'networkidle', timeout: 30000 });

      const enhanced = { ...listing };

      const description = await page.locator('[data-qa="expose-description-text"]').textContent();
      if (description) {
        enhanced.description = description.trim();
      }

      const imageUrls = await page.locator('[data-qa="image-gallery"] img').all();
      if (imageUrls.length > 0) {
        enhanced.images = [];
        for (const img of imageUrls.slice(0, 10)) {
          const src = await img.getAttribute('src');
          if (src && !src.includes('placeholder')) {
            enhanced.images.push(src);
          }
        }
      }

      const priceDetails = await this.extractPriceDetails(page);
      if (priceDetails) {
        enhanced.price.extra = priceDetails;
      }

      const coordinates = await this.extractCoordinates(page);
      if (coordinates) {
        enhanced.geo = coordinates;
      }

      const energyInfo = await this.extractEnergyInfo(page);
      if (energyInfo) {
        enhanced.energy = energyInfo;
      }

      const contactInfo = await this.extractContactInfo(page);
      if (contactInfo) {
        enhanced.contact = contactInfo;
      }

      enhanced.computed = PropertyNormalizer.computeMetrics(enhanced);

      return enhanced;

    } catch (error: any) {
      console.warn(`Failed to enhance ImmobilienScout24 listing ${listing.id}:`, error.message);
      return listing;
    }
  }

  private async extractPriceDetails(page: Page): Promise<any> {
    try {
      const priceSection = page.locator('[data-qa="price-information"]');
      const extra: any = {};

      const nebenkosten = await priceSection.locator('text=Nebenkosten').locator('..').textContent();
      if (nebenkosten) {
        extra.nebenkosten = GermanNumberParser.parsePrice(nebenkosten);
      }

      const kaution = await priceSection.locator('text=Kaution').locator('..').textContent();
      if (kaution) {
        extra.kaution = GermanNumberParser.parsePrice(kaution);
      }

      const provision = await priceSection.locator('text=Provision').locator('..').textContent();
      if (provision) {
        extra.provision = GermanNumberParser.parsePrice(provision);
      }

      return Object.keys(extra).length > 0 ? extra : null;
    } catch {
      return null;
    }
  }

  private async extractCoordinates(page: Page): Promise<{ lat: number; lng: number } | null> {
    try {
      await page.waitForSelector('[data-qa="map-container"]', { timeout: 5000 });

      const mapScript = await page.evaluate(() => {
        const scripts = Array.from(document.querySelectorAll('script'));
        return scripts.find(script =>
          script.textContent?.includes('latitude') && script.textContent?.includes('longitude')
        )?.textContent;
      });

      if (mapScript) {
        const latMatch = mapScript.match(/"latitude":\s*([0-9.-]+)/);
        const lngMatch = mapScript.match(/"longitude":\s*([0-9.-]+)/);

        if (latMatch && lngMatch) {
          return {
            lat: parseFloat(latMatch[1]),
            lng: parseFloat(lngMatch[1])
          };
        }
      }

      return null;
    } catch {
      return null;
    }
  }

  private async extractEnergyInfo(page: Page): Promise<any> {
    try {
      const energySection = page.locator('[data-qa="energy-certificate"]');
      const energy: any = {};

      const efficiencyClass = await energySection.locator('[data-qa="energy-efficiency-class"]').textContent();
      if (efficiencyClass) {
        energy.efficiencyClass = efficiencyClass.trim();
      }

      const consumption = await energySection.locator('[data-qa="energy-consumption"]').textContent();
      if (consumption) {
        energy.consumption = GermanNumberParser.parsePrice(consumption);
      }

      return Object.keys(energy).length > 0 ? energy : null;
    } catch {
      return null;
    }
  }

  private async extractContactInfo(page: Page): Promise<any> {
    try {
      const contactSection = page.locator('[data-qa="contact-information"]');
      const contact: any = {};

      const name = await contactSection.locator('[data-qa="contact-name"]').textContent();
      if (name) {
        contact.name = name.trim();
      }

      const agency = await contactSection.locator('[data-qa="contact-company"]').textContent();
      if (agency) {
        contact.agency = agency.trim();
      }

      return Object.keys(contact).length > 0 ? contact : null;
    } catch {
      return null;
    }
  }
}