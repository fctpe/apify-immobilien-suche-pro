# Immobiliensuche Pro - Deutsche Immobilienportale

Fortschrittlicher Immobilien-Aggregator für deutsche Portale mit verbesserter Anti-Erkennung. Durchsucht ImmobilienScout24, Immonet & Immowelt mit AWS WAF-Umgehung.

## 🚀 Funktionen

- **Portal-übergreifende Suche**: Durchsucht mehrere deutsche Immobilienportale gleichzeitig
- **Verbesserte Anti-Erkennung**: Umgeht AWS WAF und andere Anti-Bot-Systeme mit 75% Erfolgsrate
- **Intelligente Duplikaterkennung**: Filtert identische Anzeigen von verschiedenen Portalen heraus
- **Normalisierte Daten**: Vereinheitlichte Preisangaben (kalt/warm/Kaufpreis) und benutzerfreundliche Ausgabe
- **Änderungsverfolgung**: Erkennt neue Anzeigen und Preisupdates
- **Webhook-Benachrichtigungen**: Automatische Benachrichtigungen bei Änderungen
- **Schnellsuche-Vorlagen**: Vorkonfigurierte Suchprofile für häufige Anwendungsfälle

## 📊 Unterstützte Portale

- **ImmobilienScout24** - Deutschlands größtes Immobilienportal
- **Immonet** - Umfassende Immobiliensuche
- **Immowelt** - Regionale und überregionale Angebote

## 🏠 Anwendungsfälle

- **Studenten**: Günstige Zimmer und WG-Plätze finden
- **Berufseinsteiger**: Passende erste Wohnung in Ballungsräumen
- **Familien**: Mehrräumige Wohnungen und Häuser
- **Investoren**: Kapitalanlagen und Renditeobjekte
- **Immobilienprofis**: Marktanalyse und Preisvergleiche

## ⚡ Schnellstart

### 1. Einfache Konfiguration mit Vorlagen

Wählen Sie eine Schnellsuche-Vorlage aus:

```json
{
  "quickSearch": "Berufseinsteiger",
  "searchBuilders": [
    {
      "regions": ["Berlin"],
      "dealType": "rent",
      "priceMax": 1500,
      "sizeMin": 50,
      "roomsMin": 2
    }
  ],
  "maxResults": 100
}
```

### 2. Erweiterte Suche konfigurieren

```json
{
  "quickSearch": "Benutzerdefiniert",
  "searchBuilders": [
    {
      "regions": ["München", "Hamburg"],
      "dealType": "rent",
      "propertyTypes": ["apartment"],
      "priceMax": 2000,
      "priceMin": 800,
      "sizeMin": 60,
      "roomsMin": 2,
      "roomsMax": 4,
      "features": ["balcony", "elevator", "parking"],
      "furnished": "any",
      "postedSinceDays": 7
    }
  ],
  "maxResults": 500,
  "removeDuplicates": true,
  "trackingMode": false
}
```

## 📝 Eingabe-Parameter

### Schnellsuche-Vorlagen
- **Studentenzimmer**: Günstige Zimmer bis 600€
- **Berufseinsteiger**: 1-2 Zimmer Wohnungen bis 1.500€
- **Familienwohnung**: 3+ Zimmer für Familien
- **Luxusimmobilie**: Hochwertige Objekte ab 3.000€
- **Kapitalanlage**: Renditeobjekte für Investoren
- **Benutzerdefiniert**: Individuelle Konfiguration

### Suchkriterien

| Parameter | Beschreibung | Beispiel |
|-----------|--------------|----------|
| `regions` | Städte oder Gebiete | `["Berlin", "München"]` |
| `dealType` | Miete oder Kauf | `"rent"` oder `"sale"` |
| `propertyTypes` | Immobilientypen | `["apartment", "house"]` |
| `priceMax` | Maximales Budget (€) | `1500` |
| `sizeMin` | Mindestgröße (m²) | `60` |
| `roomsMin` | Mindestanzahl Zimmer | `2` |
| `features` | Gewünschte Ausstattung | `["balcony", "parking"]` |

### Verfügbare Ausstattungsmerkmale
- `balcony` - Balkon
- `garden` - Garten
- `parking` - Parkplatz
- `elevator` - Aufzug
- `pets_allowed` - Haustiere erlaubt
- `dishwasher` - Spülmaschine
- `washing_machine` - Waschmaschine

## 📤 Ausgabe-Format

Die Daten werden in einem benutzerfreundlichen, flachen Format ausgegeben:

```json
{
  "source": "immoscout24",
  "sourceId": "123456789",
  "url": "https://www.immobilienscout24.de/expose/123456789",
  "title": "Moderne 3-Zimmer-Wohnung in Berlin-Mitte",
  "description": "Helle Wohnung mit Balkon und Einbauküche...",
  "propertyType": "Wohnung",
  "dealType": "Miete",
  "address": "Unter den Linden 1, 10117 Berlin",
  "price": 1200.0,
  "size": 85.5,
  "rooms": 3,
  "floor": 2,
  "yearBuilt": 1995,
  "condition": "renoviert",
  "pricePerSqm": 14.04,
  "features": ["Balkon", "Aufzug", "Parkplatz"],
  "images": ["https://...", "https://..."],
  "contactName": "Max Mustermann",
  "contactPhone": "+49 30 12345678",
  "contactAgency": "Immobilien Mustermann GmbH",
  "postedDate": "2024-01-15",
  "extractedDate": "2024-01-22T09:15:00Z"
}
```

## ⚙️ Erweiterte Optionen

### Performance-Einstellungen
```json
{
  "advancedOptions": {
    "concurrency": 2,
    "debug": false,
    "headless": true
  }
}
```

- `concurrency`: Parallele Browser-Sitzungen (1-5)
- `debug`: Detaillierte Protokollierung aktivieren
- `headless`: Browser im Hintergrund ausführen

### Duplikaterkennung
```json
{
  "removeDuplicates": true
}
```

Filtert identische Immobilien von verschiedenen Portalen basierend auf Adresse und Grunddaten.

### Änderungsverfolgung
```json
{
  "trackingMode": true
}
```

Aktiviert Benachrichtigungen über:
- Neue Immobilienanzeigen
- Preisänderungen bei bestehenden Anzeigen
- Offline genommene Immobilien

## 🔗 Experten-Modus: Direkte URLs

Für erweiterte Nutzer können direkte Such-URLs von ImmobilienScout24 verwendet werden:

```json
{
  "searchUrls": [
    {
      "url": "https://www.immobilienscout24.de/Suche/de/berlin/berlin/wohnung-mieten?price=-1500&livingspace=50-&numberofrooms=2.0-"
    }
  ]
}
```

## 💰 Preismodell

**Pay-per-Event**: Sie zahlen nur für erfolgreiche Datenextraktionen
- Kosteneffizient für gelegentliche Nutzung
- Skaliert automatisch mit Ihrem Bedarf
- Transparente Abrechnung pro gefundener Immobilie

## 📈 Performance

- **Anti-Erkennung**: 75% Erfolgsrate bei AWS WAF-geschützten Seiten
- **Geschwindigkeit**: Bis zu 100 Immobilien pro Minute (je nach Konfiguration)
- **Zuverlässigkeit**: Automatische Wiederholung bei temporären Fehlern
- **Datenqualität**: Normalisierte und validierte Ausgabedaten

## 🛠️ Technische Details

### Verwendete Technologien
- **nodriver**: Moderne Browser-Automatisierung mit Anti-Erkennung
- **Python**: Robuste Datenverarbeitung und -validation
- **Apify SDK**: Skalierbare Cloud-Ausführung
- **Intelligente Proxies**: Geografisch verteilte IP-Rotation

### Anti-Erkennung Features
- Browser-Fingerprint-Verschleierung
- Menschliche Navigationsmuster
- Dynamische Wartezeiten
- User-Agent-Rotation
- Cookie-Management

## 📞 Support

Bei Fragen oder Problemen wenden Sie sich an:
- **E-Mail**: kontakt@barrierefix.de
- **GitHub**: Erstellen Sie ein Issue für Bugberichte oder Feature-Requests

## 🔄 Versionshinweise

### Version 2.0
- Vereinfachte Ausgabestruktur für bessere Spreadsheet-Kompatibilität
- Komplett deutsche Benutzeroberfläche
- Verbesserte Schnellsuche-Vorlagen
- Erweiterte Anti-Erkennung mit 75% Erfolgsrate

### Entwickelt von Barrierefix
Spezialisiert auf fortschrittliche Web-Scraping-Lösungen für den deutschen Markt.

---

## 📋 Lizenz

Dieses Tool ist für den professionellen Einsatz konzipiert und unterliegt den Nutzungsbedingungen der jeweiligen Immobilienportale. Nutzer sind verpflichtet, die Terms of Service der durchsuchten Websites zu beachten.