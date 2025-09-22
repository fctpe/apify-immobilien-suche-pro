import { Actor } from 'apify';
import { PlaywrightCrawler, ProxyConfiguration } from 'crawlee';
import { z } from 'zod';
import { DateTime } from 'luxon';

import { ActorInput, RealEstateListing, ChangeEvent, StateSnapshot } from './types';
import { ImmobilienScout24Crawler } from './crawlers/immoscout24';
import { CrossPortalDeduplicator } from './deduplication/fingerprinting';
import { StealthManager } from './anti-detection/stealth';

const InputSchema = z.object({
  searchUrls: z.array(z.object({
    url: z.string().url()
  })).optional().default([]),
  searchBuilders: z.array(z.object({
    portals: z.array(z.enum(['immoscout24', 'immonet', 'immowelt'])).default(['immoscout24']),
    dealType: z.enum(['rent', 'sale']).default('rent'),
    propertyTypes: z.array(z.enum(['apartment', 'house', 'land', 'commercial'])).default(['apartment']),
    regions: z.array(z.string()).min(1),
    radiusKm: z.number().min(0).max(200).optional().default(0),
    priceMin: z.number().min(0).optional().default(0),
    priceMax: z.number().min(0).optional().default(0),
    sizeMin: z.number().min(0).optional().default(0),
    roomsMin: z.number().min(0).optional().default(0),
    roomsMax: z.number().min(0).optional().default(0),
    postedSinceDays: z.number().min(0).optional().default(0)
  })).optional().default([]),
  maxResults: z.number().min(0).optional().default(1000),
  trackingMode: z.boolean().optional().default(false),
  notifications: z.object({
    emails: z.array(z.string().email()).optional().default([]),
    webhookUrl: z.string().url().optional(),
    events: z.array(z.enum(['NEW', 'PRICE_CHANGE', 'STATUS_OFFLINE', 'DESCRIPTION_UPDATE'])).optional().default(['NEW', 'PRICE_CHANGE'])
  }).optional().default({ emails: [], events: ['NEW', 'PRICE_CHANGE'] }),
  dedupeLevel: z.enum(['none', 'portal', 'cross_portal']).optional().default('cross_portal'),
  concurrency: z.number().min(1).max(10).optional().default(3),
  proxyCountry: z.string().optional().default('DE'),
  complianceMode: z.boolean().optional().default(true),
  debug: z.boolean().optional().default(false)
});

type ValidatedInput = z.infer<typeof InputSchema>;

class ImmobiliensuchePro {
  private input: ValidatedInput;
  private crawler: PlaywrightCrawler;
  private deduplicator: CrossPortalDeduplicator;
  private extractedListings: RealEstateListing[] = [];
  private changeEvents: ChangeEvent[] = [];

  constructor(input: ValidatedInput) {
    this.input = input;
    this.deduplicator = new CrossPortalDeduplicator();
    this.crawler = this.createCrawler();
  }

  private createCrawler(): PlaywrightCrawler {
    const proxyConfiguration = new ProxyConfiguration({});

    return new PlaywrightCrawler({
      proxyConfiguration,
      maxConcurrency: this.input.concurrency,
      headless: true,
      browserPoolOptions: {
        useFingerprints: true,
        fingerprintOptions: {
          fingerprintGeneratorOptions: {
            browsers: ['chrome'],
            devices: ['desktop'],
            locales: ['de-DE', 'en-US'],
            operatingSystems: ['windows', 'macos', 'linux']
          }
        }
      },
      launchContext: {
        launchOptions: {
          args: [
            '--no-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--disable-features=VizDisplayCompositor',
            '--disable-ipc-flooding-protection'
          ]
        }
      },
      preNavigationHooks: [
        async ({ page }) => {
          await StealthManager.setupStealth(page, {
            locale: 'de-DE,de;q=0.9,en;q=0.8',
            timezone: 'Europe/Berlin'
          });
        }
      ],
      requestHandler: async ({ page, request }) => {
        await this.handleRequest(page, request);
      },
      failedRequestHandler: async ({ request }) => {
        console.error(`Request failed: ${request.url}`);
      }
    });
  }

  private async handleRequest(page: any, request: any): Promise<void> {
    const url = request.url;

    if (url.includes('immobilienscout24.de')) {
      await this.handleImmobilienScout24(page, request);
    } else {
      console.warn(`Unsupported portal: ${url}`);
    }
  }

  private async handleImmobilienScout24(page: any, request: any): Promise<void> {
    const crawler = new ImmobilienScout24Crawler();
    const options = {
      maxResults: this.input.maxResults,
      complianceMode: this.input.complianceMode,
      debug: this.input.debug,
      proxyCountry: this.input.proxyCountry
    };

    try {
      const listings = await crawler.crawl({ page }, options);

      for (const listing of listings) {
        const processedListing = this.processListing(listing);
        if (processedListing) {
          this.extractedListings.push(processedListing);

          if (this.input.debug) {
            console.log(`Extracted: ${processedListing.title} - ${processedListing.price.total}€`);
          }
        }
      }

    } catch (error: any) {
      console.error(`ImmobilienScout24 crawling failed:`, error.message);
      throw error;
    }
  }

  private processListing(listing: RealEstateListing): RealEstateListing | null {
    try {
      if (this.input.dedupeLevel === 'cross_portal') {
        return this.deduplicator.addListing(listing);
      } else if (this.input.dedupeLevel === 'portal') {
        return listing;
      } else {
        return listing;
      }
    } catch (error: any) {
      console.warn(`Failed to process listing ${listing.id}:`, error.message);
      return null;
    }
  }

  async initialize(): Promise<void> {
    const dataset = await Actor.openDataset('listings');
    const changeDataset = await Actor.openDataset('changes');

    console.log('🏠 Immobiliensuche Pro initialized');
    console.log(`📋 Configuration: ${this.input.maxResults} max results, ${this.input.concurrency} concurrency`);
    console.log(`🔄 Deduplication: ${this.input.dedupeLevel}, Tracking: ${this.input.trackingMode}`);

    if (this.input.complianceMode) {
      console.log('⚖️  Compliance mode enabled - using conservative crawling');
    }
  }

  async run(): Promise<void> {
    try {
      await this.generateSearchRequests();

      await this.crawler.run();

      if (this.input.trackingMode) {
        await this.detectChanges();
      }

      await this.saveResults();
      await this.sendNotifications();

      const stats = this.deduplicator.getStats();
      console.log(`✅ Completed: ${this.extractedListings.length} listings extracted`);
      console.log(`🎯 Deduplication: ${stats.duplicatesFound} duplicates found across ${stats.uniqueFingerprints} unique properties`);

      if (this.changeEvents.length > 0) {
        console.log(`📊 Changes detected: ${this.changeEvents.length} events`);
      }

    } catch (error: any) {
      console.error('❌ Crawling failed:', error.message);
      throw error;
    }
  }

  private async generateSearchRequests(): Promise<void> {
    const requests: string[] = [];

    for (const urlConfig of this.input.searchUrls) {
      requests.push(urlConfig.url);
    }

    for (const builder of this.input.searchBuilders) {
      if (builder.portals.includes('immoscout24')) {
        const crawler = new ImmobilienScout24Crawler();
        const urls = crawler.buildSearchUrl(builder);
        requests.push(...urls);
      }
    }

    if (requests.length === 0) {
      throw new Error('No search URLs or builders provided');
    }

    console.log(`🔍 Generated ${requests.length} search requests`);

    for (const url of requests) {
      await this.crawler.addRequests([{ url }]);
    }
  }

  private async detectChanges(): Promise<void> {
    if (!this.input.trackingMode) return;

    const kvStore = await Actor.openKeyValueStore('state');
    const stateSnapshot: StateSnapshot = await kvStore.getValue('listings_snapshot') || {};

    const currentSnapshot: StateSnapshot = {};

    for (const listing of this.extractedListings) {
      const key = listing.id;
      const currentState = {
        price: listing.price.total,
        status: 'active' as const,
        lastSeen: DateTime.now().toISO(),
        checksum: this.generateListingChecksum(listing)
      };

      currentSnapshot[key] = currentState;

      const previousState = stateSnapshot[key];

      if (!previousState) {
        this.changeEvents.push({
          type: 'NEW',
          canonicalId: listing.id,
          after: listing,
          detectedAt: DateTime.now().toISO(),
          source: listing.source
        });
      } else if (previousState.price !== currentState.price) {
        this.changeEvents.push({
          type: 'PRICE_CHANGE',
          canonicalId: listing.id,
          before: { price: { total: previousState.price, currency: 'EUR', type: 'kalt' } },
          after: { price: listing.price },
          detectedAt: DateTime.now().toISO(),
          source: listing.source
        });
      } else if (previousState.checksum !== currentState.checksum) {
        this.changeEvents.push({
          type: 'DESCRIPTION_UPDATE',
          canonicalId: listing.id,
          after: listing,
          detectedAt: DateTime.now().toISO(),
          source: listing.source
        });
      }
    }

    for (const [id, prevState] of Object.entries(stateSnapshot)) {
      if (!currentSnapshot[id]) {
        this.changeEvents.push({
          type: 'STATUS_OFFLINE',
          canonicalId: id,
          before: { id },
          detectedAt: DateTime.now().toISO(),
          source: 'unknown'
        });
      }
    }

    await kvStore.setValue('listings_snapshot', currentSnapshot);
  }

  private generateListingChecksum(listing: RealEstateListing): string {
    const hashInput = [
      listing.title,
      listing.description || '',
      listing.price.total,
      listing.size?.livingSqm || 0,
      JSON.stringify(listing.features || [])
    ].join('|');

    let hash = 0;
    for (let i = 0; i < hashInput.length; i++) {
      const char = hashInput.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
  }

  private async saveResults(): Promise<void> {
    const dataset = await Actor.openDataset('listings');
    await dataset.pushData(this.extractedListings);

    if (this.changeEvents.length > 0) {
      const changeDataset = await Actor.openDataset('changes');
      await dataset.pushData(this.changeEvents);
    }
  }

  private async sendNotifications(): Promise<void> {
    if (!this.input.notifications || this.changeEvents.length === 0) return;

    const relevantEvents = this.changeEvents.filter(event =>
      this.input.notifications!.events!.includes(event.type)
    );

    if (relevantEvents.length === 0) return;

    const summary = this.generateNotificationSummary(relevantEvents);

    if (this.input.notifications.webhookUrl) {
      await this.sendWebhook(this.input.notifications.webhookUrl, {
        summary,
        events: relevantEvents,
        timestamp: DateTime.now().toISO()
      });
    }

    if (this.input.notifications.emails?.length) {
      console.log(`📧 Email notifications would be sent to: ${this.input.notifications.emails.join(', ')}`);
      console.log(`📊 Summary: ${summary}`);
    }
  }

  private generateNotificationSummary(events: ChangeEvent[]): string {
    const counts = events.reduce((acc, event) => {
      acc[event.type] = (acc[event.type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    const parts = Object.entries(counts).map(([type, count]) => `${count} ${type.toLowerCase()}`);
    return `Found ${parts.join(', ')} in German real estate listings`;
  }

  private async sendWebhook(url: string, payload: any): Promise<void> {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'Immobiliensuche-Pro/1.0'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        console.warn(`Webhook failed: ${response.status} ${response.statusText}`);
      } else {
        console.log('✅ Webhook notification sent successfully');
      }
    } catch (error: any) {
      console.error('❌ Webhook notification failed:', error.message);
    }
  }
}

Actor.main(async () => {
  const rawInput = await Actor.getInput();

  let input: ValidatedInput;
  try {
    input = InputSchema.parse(rawInput || {});
  } catch (error: any) {
    console.error('❌ Invalid input configuration:', error.message);
    console.error('📋 Validation errors:', JSON.stringify(error.errors, null, 2));
    throw new Error('Invalid input configuration - please check your settings');
  }

  if (input.searchUrls.length === 0 && input.searchBuilders.length === 0) {
    throw new Error('Either searchUrls or searchBuilders must be provided');
  }

  const actor = new ImmobiliensuchePro(input);
  await actor.initialize();
  await actor.run();
});