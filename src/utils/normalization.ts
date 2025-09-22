import { DateTime } from 'luxon';
import { RealEstateListing } from '../types';

export class GermanAddressParser {
  private static readonly BUNDESLAENDER: Record<string, string> = {
    'Baden-Württemberg': 'Baden-Württemberg',
    'Bayern': 'Bayern',
    'Berlin': 'Berlin',
    'Brandenburg': 'Brandenburg',
    'Bremen': 'Bremen',
    'Hamburg': 'Hamburg',
    'Hessen': 'Hessen',
    'Mecklenburg-Vorpommern': 'Mecklenburg-Vorpommern',
    'Niedersachsen': 'Niedersachsen',
    'Nordrhein-Westfalen': 'Nordrhein-Westfalen',
    'Rheinland-Pfalz': 'Rheinland-Pfalz',
    'Saarland': 'Saarland',
    'Sachsen': 'Sachsen',
    'Sachsen-Anhalt': 'Sachsen-Anhalt',
    'Schleswig-Holstein': 'Schleswig-Holstein',
    'Thüringen': 'Thüringen'
  };

  private static readonly PLZ_TO_STATE: Record<string, string> = {
    '0': 'Sachsen',
    '1': 'Berlin',
    '2': 'Schleswig-Holstein',
    '3': 'Niedersachsen',
    '4': 'Nordrhein-Westfalen',
    '5': 'Nordrhein-Westfalen',
    '6': 'Hessen',
    '7': 'Baden-Württemberg',
    '8': 'Bayern',
    '9': 'Bayern'
  };

  static parseAddress(rawAddress: string): RealEstateListing['address'] {
    const address: RealEstateListing['address'] = {
      raw: rawAddress,
      country: 'DE'
    };

    const plzCityMatch = rawAddress.match(/(\d{5})\s+([^,\n]+)/);
    if (plzCityMatch) {
      address.postcode = plzCityMatch[1];
      address.city = this.normalizeCity(plzCityMatch[2].trim());
      address.state = this.getStateFromPLZ(address.postcode);
    }

    const streetMatch = rawAddress.match(/^([^,\n]+?)(?:\s+(\d+[a-zA-Z]?))?(?:,|\s+\d{5})/);
    if (streetMatch) {
      address.street = streetMatch[1].trim();
      if (streetMatch[2]) {
        address.houseNo = streetMatch[2];
      }
    }

    return address;
  }

  private static normalizeCity(city: string): string {
    return city
      .replace(/\s+/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  private static getStateFromPLZ(plz: string): string {
    const firstDigit = plz.charAt(0);
    return this.PLZ_TO_STATE[firstDigit] || '';
  }

  static generateAddressKey(address: RealEstateListing['address']): string {
    const parts = [
      address.street?.toLowerCase().replace(/\s+/g, ''),
      address.houseNo?.toLowerCase(),
      address.postcode,
      address.city?.toLowerCase().replace(/\s+/g, '')
    ].filter(Boolean);

    return parts.join('|');
  }
}

export class GermanNumberParser {
  static parsePrice(priceStr: string): number {
    if (!priceStr) return 0;

    const cleaned = priceStr
      .replace(/[€\s]/g, '')
      .replace(/\./g, '')
      .replace(',', '.');

    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
  }

  static parseArea(areaStr: string): number {
    if (!areaStr) return 0;

    const cleaned = areaStr
      .replace(/[m²\s]/g, '')
      .replace(',', '.');

    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
  }

  static parseRooms(roomsStr: string): number {
    if (!roomsStr) return 0;

    const cleaned = roomsStr.replace(',', '.');
    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
  }
}

export class GermanDateParser {
  static parseRelativeDate(dateStr: string, referenceDate?: DateTime): string {
    const now = referenceDate || DateTime.now().setZone('Europe/Berlin');

    if (dateStr.includes('vor')) {
      const dayMatch = dateStr.match(/vor\s+(\d+)\s+Tag/i);
      if (dayMatch) {
        const daysAgo = parseInt(dayMatch[1]);
        return now.minus({ days: daysAgo }).toISO() || now.toISO() || DateTime.now().toISO();
      }

      const weekMatch = dateStr.match(/vor\s+(\d+)\s+Woche/i);
      if (weekMatch) {
        const weeksAgo = parseInt(weekMatch[1]);
        return now.minus({ weeks: weeksAgo }).toISO() || now.toISO() || DateTime.now().toISO();
      }

      if (dateStr.includes('heute') || dateStr.includes('Heute')) {
        return now.toISO() || DateTime.now().toISO();
      }

      if (dateStr.includes('gestern') || dateStr.includes('Gestern')) {
        return now.minus({ days: 1 }).toISO() || now.toISO() || DateTime.now().toISO();
      }
    }

    const germanDateMatch = dateStr.match(/(\d{1,2})\.(\d{1,2})\.(\d{4})/);
    if (germanDateMatch) {
      const day = parseInt(germanDateMatch[1]);
      const month = parseInt(germanDateMatch[2]);
      const year = parseInt(germanDateMatch[3]);

      const parsed = DateTime.fromObject({ year, month, day }, { zone: 'Europe/Berlin' });
      return parsed.isValid ? (parsed.toISO() || now.toISO() || DateTime.now().toISO()) : (now.toISO() || DateTime.now().toISO());
    }

    return now.toISO() || DateTime.now().toISO();
  }
}

export class PropertyNormalizer {
  private static readonly PROPERTY_TYPE_MAPPING: Record<string, RealEstateListing['propertyType']> = {
    'wohnung': 'apartment',
    'apartment': 'apartment',
    'eigentumswohnung': 'apartment',
    'mietwohnung': 'apartment',
    'haus': 'house',
    'house': 'house',
    'einfamilienhaus': 'house',
    'reihenhaus': 'house',
    'villa': 'house',
    'grundstück': 'land',
    'land': 'land',
    'bauland': 'land',
    'gewerbe': 'commercial',
    'commercial': 'commercial',
    'büro': 'commercial',
    'laden': 'commercial'
  };

  private static readonly FEATURES_MAPPING: Record<string, string> = {
    'balkon': 'balcony',
    'terrasse': 'terrace',
    'garten': 'garden',
    'aufzug': 'elevator',
    'fahrstuhl': 'elevator',
    'parkplatz': 'parking',
    'garage': 'garage',
    'keller': 'basement',
    'klimaanlage': 'air_conditioning',
    'fußbodenheizung': 'floor_heating',
    'einbauküche': 'fitted_kitchen',
    'möbliert': 'furnished',
    'haustiere': 'pets_allowed',
    'wg': 'shared_flat'
  };

  static normalizePropertyType(rawType: string): RealEstateListing['propertyType'] {
    const normalized = rawType.toLowerCase().trim();
    return this.PROPERTY_TYPE_MAPPING[normalized] || 'apartment';
  }

  static normalizeFeatures(rawFeatures: string[]): string[] {
    return rawFeatures
      .map(feature => {
        const normalized = feature.toLowerCase().trim();
        return this.FEATURES_MAPPING[normalized] || feature.toLowerCase();
      })
      .filter((feature, index, array) => array.indexOf(feature) === index);
  }

  static normalizePriceType(rawPrice: string, dealType: string): { type: 'kalt' | 'warm' | 'kaufpreis'; amount: number } {
    const amount = GermanNumberParser.parsePrice(rawPrice);

    if (dealType === 'sale') {
      return { type: 'kaufpreis', amount };
    }

    const lowerPrice = rawPrice.toLowerCase();
    if (lowerPrice.includes('kalt') || lowerPrice.includes('netto')) {
      return { type: 'kalt', amount };
    }

    if (lowerPrice.includes('warm') || lowerPrice.includes('gesamt')) {
      return { type: 'warm', amount };
    }

    return { type: 'kalt', amount };
  }

  static computeMetrics(listing: RealEstateListing): RealEstateListing['computed'] {
    const computed: RealEstateListing['computed'] = {};

    if (listing.price?.total && listing.size?.livingSqm) {
      computed.pricePerSqm = Math.round((listing.price.total / listing.size.livingSqm) * 100) / 100;
    }

    if (listing.dealType === 'rent' && listing.price?.total) {
      let totalCost = listing.price.total;
      if (listing.price.extra?.nebenkosten && listing.price.type === 'kalt') {
        totalCost += listing.price.extra.nebenkosten;
      }
      computed.totalMonthlyCost = totalCost;
    }

    return computed;
  }

  static generateCanonicalId(listing: RealEstateListing): string {
    const parts = [
      'de',
      listing.address.city?.toLowerCase().substring(0, 3) || 'unk',
      listing.address.postcode || '00000',
      listing.propertyType.substring(0, 3),
      listing.dealType,
      Math.round(listing.price?.total || 0).toString(),
      Math.round(listing.size?.livingSqm || 0).toString(),
      Math.round(listing.rooms || 0).toString()
    ];

    const baseId = parts.join('_');

    return baseId + '_' + this.generateHash(baseId).substring(0, 8);
  }

  private static generateHash(input: string): string {
    let hash = 0;
    for (let i = 0; i < input.length; i++) {
      const char = input.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
  }
}