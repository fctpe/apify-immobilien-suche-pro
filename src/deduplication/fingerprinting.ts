import { createHash } from 'crypto';
import { RealEstateListing, DedupeFingerprint } from '../types';
import { GermanAddressParser } from '../utils/normalization';

export class ListingFingerprinter {
  static generateFingerprints(listing: RealEstateListing): DedupeFingerprint {
    return {
      addressKey: this.generateAddressKey(listing.address),
      geoKey: this.generateGeoKey(listing.geo),
      metricsKey: this.generateMetricsKey(listing),
      imageKey: this.generateImageKey(listing.images)
    };
  }

  private static generateAddressKey(address: RealEstateListing['address']): string {
    return GermanAddressParser.generateAddressKey(address);
  }

  private static generateGeoKey(geo?: RealEstateListing['geo']): string | undefined {
    if (!geo?.lat || !geo?.lng) return undefined;

    const roundedLat = Math.round(geo.lat * 10000) / 10000;
    const roundedLng = Math.round(geo.lng * 10000) / 10000;

    return `${roundedLat}_${roundedLng}`;
  }

  private static generateMetricsKey(listing: RealEstateListing): string {
    const price = Math.round((listing.price?.total || 0) / 50) * 50;
    const size = Math.round((listing.size?.livingSqm || 0) / 5) * 5;
    const rooms = Math.round((listing.rooms || 0) * 2) / 2;

    return `${price}_${size}_${rooms}`;
  }

  private static generateImageKey(images?: string[]): string | undefined {
    if (!images || images.length === 0) return undefined;

    const firstImageUrl = images[0];
    if (!firstImageUrl) return undefined;

    return createHash('sha1')
      .update(firstImageUrl)
      .digest('hex')
      .substring(0, 8);
  }

  static isMatch(fingerprint1: DedupeFingerprint, fingerprint2: DedupeFingerprint): boolean {
    if (fingerprint1.addressKey && fingerprint2.addressKey) {
      if (fingerprint1.addressKey === fingerprint2.addressKey) {
        return this.compareMetrics(fingerprint1.metricsKey, fingerprint2.metricsKey);
      }
    }

    if (fingerprint1.geoKey && fingerprint2.geoKey) {
      if (fingerprint1.geoKey === fingerprint2.geoKey) {
        return this.compareMetrics(fingerprint1.metricsKey, fingerprint2.metricsKey);
      }
    }

    if (fingerprint1.imageKey && fingerprint2.imageKey) {
      if (fingerprint1.imageKey === fingerprint2.imageKey) {
        return this.compareMetrics(fingerprint1.metricsKey, fingerprint2.metricsKey, 0.15);
      }
    }

    return false;
  }

  private static compareMetrics(metrics1: string, metrics2: string, threshold: number = 0.1): boolean {
    const [price1, size1, rooms1] = metrics1.split('_').map(Number);
    const [price2, size2, rooms2] = metrics2.split('_').map(Number);

    const priceMatch = this.isWithinThreshold(price1, price2, threshold);
    const sizeMatch = size1 === 0 || size2 === 0 || this.isWithinThreshold(size1, size2, 0.05);
    const roomsMatch = rooms1 === 0 || rooms2 === 0 || Math.abs(rooms1 - rooms2) <= 0.5;

    return priceMatch && sizeMatch && roomsMatch;
  }

  private static isWithinThreshold(value1: number, value2: number, threshold: number): boolean {
    if (value1 === 0 || value2 === 0) return true;

    const diff = Math.abs(value1 - value2);
    const avg = (value1 + value2) / 2;
    return diff / avg <= threshold;
  }

  static generateListingHash(listing: RealEstateListing): string {
    const hashInput = [
      listing.title,
      listing.price?.total || 0,
      listing.size?.livingSqm || 0,
      listing.rooms || 0,
      listing.address.street || '',
      listing.address.postcode || '',
      listing.description?.substring(0, 100) || ''
    ].join('|');

    return createHash('sha256')
      .update(hashInput)
      .digest('hex')
      .substring(0, 16);
  }
}

export class CrossPortalDeduplicator {
  private seenFingerprints: Map<string, RealEstateListing[]> = new Map();

  addListing(listing: RealEstateListing): RealEstateListing {
    const fingerprints = ListingFingerprinter.generateFingerprints(listing);
    const fingerprintKey = this.createFingerprintKey(fingerprints);

    listing.dedupe = {
      fingerprints: [fingerprintKey],
      alternativeSources: []
    };

    const existingListings = this.seenFingerprints.get(fingerprintKey) || [];

    for (const existingListing of existingListings) {
      if (existingListing.source !== listing.source) {
        const existingFingerprints = ListingFingerprinter.generateFingerprints(existingListing);

        if (ListingFingerprinter.isMatch(fingerprints, existingFingerprints)) {
          listing.dedupe.alternativeSources!.push({
            source: existingListing.source,
            sourceId: existingListing.sourceId,
            url: existingListing.url
          });

          if (!existingListing.dedupe) {
            existingListing.dedupe = { fingerprints: [], alternativeSources: [] };
          }

          existingListing.dedupe.alternativeSources!.push({
            source: listing.source,
            sourceId: listing.sourceId,
            url: listing.url
          });

          if (this.shouldMergeListings(existingListing, listing)) {
            return this.mergeListings(existingListing, listing);
          }
        }
      }
    }

    existingListings.push(listing);
    this.seenFingerprints.set(fingerprintKey, existingListings);

    return listing;
  }

  private createFingerprintKey(fingerprints: DedupeFingerprint): string {
    return [
      fingerprints.addressKey,
      fingerprints.geoKey || 'nogeo',
      fingerprints.metricsKey,
      fingerprints.imageKey || 'noimg'
    ].join('|');
  }

  private shouldMergeListings(existing: RealEstateListing, newListing: RealEstateListing): boolean {
    const priorityOrder = ['immoscout24', 'immonet', 'immowelt'];
    const existingPriority = priorityOrder.indexOf(existing.source);
    const newPriority = priorityOrder.indexOf(newListing.source);

    return newPriority < existingPriority;
  }

  private mergeListings(primary: RealEstateListing, secondary: RealEstateListing): RealEstateListing {
    const merged = { ...primary };

    if (!merged.images?.length && secondary.images?.length) {
      merged.images = secondary.images;
    }

    if (!merged.description && secondary.description) {
      merged.description = secondary.description;
    }

    if (!merged.contact?.phone && secondary.contact?.phone) {
      merged.contact = { ...merged.contact, ...secondary.contact };
    }

    if (!merged.geo && secondary.geo) {
      merged.geo = secondary.geo;
    }

    if (!merged.energy && secondary.energy) {
      merged.energy = secondary.energy;
    }

    merged.dedupe = merged.dedupe || { fingerprints: [], alternativeSources: [] };
    merged.dedupe.alternativeSources = merged.dedupe.alternativeSources || [];

    if (!merged.dedupe.alternativeSources.some(s => s.source === secondary.source)) {
      merged.dedupe.alternativeSources.push({
        source: secondary.source,
        sourceId: secondary.sourceId,
        url: secondary.url
      });
    }

    return merged;
  }

  getStats(): { totalListings: number; uniqueFingerprints: number; duplicatesFound: number } {
    const totalListings = Array.from(this.seenFingerprints.values())
      .reduce((sum, listings) => sum + listings.length, 0);

    const duplicatesFound = Array.from(this.seenFingerprints.values())
      .filter(listings => listings.length > 1)
      .reduce((sum, listings) => sum + (listings.length - 1), 0);

    return {
      totalListings,
      uniqueFingerprints: this.seenFingerprints.size,
      duplicatesFound
    };
  }
}