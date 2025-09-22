export interface RealEstateListing {
  id: string;
  source: 'immoscout24' | 'immonet' | 'immowelt';
  sourceId?: string;
  url: string;
  title: string;
  description?: string;
  propertyType: 'apartment' | 'house' | 'land' | 'commercial';
  dealType: 'rent' | 'sale';
  price: {
    total: number;
    currency: string;
    type: 'kalt' | 'warm' | 'kaufpreis';
    extra?: {
      nebenkosten?: number;
      kaution?: number;
      provision?: number;
      hausgeld?: number;
    };
  };
  size?: {
    livingSqm?: number;
    plotSqm?: number;
  };
  rooms?: number;
  floor?: number;
  yearBuilt?: number;
  condition?: string;
  address: {
    raw?: string;
    street?: string;
    houseNo?: string;
    postcode?: string;
    city?: string;
    state?: string;
    country: string;
  };
  geo?: {
    lat: number;
    lng: number;
  };
  features?: string[];
  images?: string[];
  contact?: {
    name?: string;
    phone?: string;
    agency?: string;
  };
  energy?: {
    efficiencyClass?: string;
    consumption?: number;
    heatingType?: string;
  };
  dates: {
    postedAt?: string;
    updatedAt?: string;
    extractedAt: string;
  };
  computed?: {
    pricePerSqm?: number;
    totalMonthlyCost?: number;
  };
  dedupe?: {
    fingerprints: string[];
    alternativeSources?: Array<{
      source: string;
      sourceId?: string;
      url: string;
    }>;
  };
  raw?: any;
}

export interface SearchBuilder {
  portals: Array<'immoscout24' | 'immonet' | 'immowelt'>;
  dealType: 'rent' | 'sale';
  propertyTypes: Array<'apartment' | 'house' | 'land' | 'commercial'>;
  regions: string[];
  radiusKm?: number;
  priceMin?: number;
  priceMax?: number;
  sizeMin?: number;
  roomsMin?: number;
  roomsMax?: number;
  postedSinceDays?: number;
}

export interface ActorInput {
  searchUrls?: Array<{ url: string }>;
  searchBuilders?: SearchBuilder[];
  maxResults?: number;
  trackingMode?: boolean;
  notifications?: {
    emails?: string[];
    webhookUrl?: string;
    events?: Array<'NEW' | 'PRICE_CHANGE' | 'STATUS_OFFLINE' | 'DESCRIPTION_UPDATE'>;
  };
  dedupeLevel?: 'none' | 'portal' | 'cross_portal';
  concurrency?: number;
  proxyCountry?: string;
  complianceMode?: boolean;
  debug?: boolean;
}

export interface ChangeEvent {
  type: 'NEW' | 'PRICE_CHANGE' | 'STATUS_OFFLINE' | 'DESCRIPTION_UPDATE';
  canonicalId: string;
  before?: Partial<RealEstateListing>;
  after?: Partial<RealEstateListing>;
  detectedAt: string;
  source: string;
}

export interface CrawlerOptions {
  maxResults?: number;
  complianceMode: boolean;
  debug: boolean;
  proxyCountry: string;
}

export interface DedupeFingerprint {
  addressKey: string;
  geoKey?: string;
  metricsKey: string;
  imageKey?: string;
}

export interface PortalCrawler {
  name: string;
  crawl(searchParams: any, options: CrawlerOptions): Promise<RealEstateListing[]>;
  buildSearchUrl?(builder: SearchBuilder): string[];
}

export interface StateSnapshot {
  [canonicalId: string]: {
    price: number;
    status: 'active' | 'offline';
    lastSeen: string;
    checksum: string;
  };
}