import { Page, BrowserContext } from 'playwright';
import { PlaywrightCrawler, SessionPool } from 'crawlee';

export interface StealthOptions {
  userAgent?: string;
  viewport?: { width: number; height: number };
  locale?: string;
  timezone?: string;
  randomDelay?: { min: number; max: number };
}

export class StealthManager {
  private static readonly USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
  ];

  private static readonly VIEWPORTS = [
    { width: 1920, height: 1080 },
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
    { width: 1536, height: 864 },
    { width: 1280, height: 720 }
  ];

  static async setupStealth(page: Page, options: StealthOptions = {}): Promise<void> {
    const userAgent = options.userAgent || this.getRandomUserAgent();
    const viewport = options.viewport || this.getRandomViewport();

    await page.route('**/*', async route => {
      const headers = await route.request().allHeaders();
      headers['user-agent'] = userAgent;
      await route.continue({ headers });
    });
    await page.setViewportSize(viewport);

    await page.setExtraHTTPHeaders({
      'Accept-Language': options.locale || 'de-DE,de;q=0.9,en;q=0.8',
      'Accept-Encoding': 'gzip, deflate, br',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
      'Sec-Fetch-Dest': 'document',
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-Site': 'none',
      'Upgrade-Insecure-Requests': '1'
    });

    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
      });

      Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
      });

      Object.defineProperty(navigator, 'languages', {
        get: () => ['de-DE', 'de', 'en-US', 'en'],
      });

      const originalQuery = window.navigator.permissions.query;
      window.navigator.permissions.query = (parameters: any) => (
        parameters.name === 'notifications' ?
          Promise.resolve({ state: (window as any).Notification?.permission || 'default' } as any) :
          originalQuery(parameters)
      );

      (window as any).chrome = {
        runtime: {},
      };
    });

    const timezone = options.timezone || 'Europe/Berlin';
    try {
      await (page as any).emulateTimezone(timezone);
    } catch {
      // Timezone emulation not available in this Playwright version
    }
  }

  static async humanLikeDelay(min: number = 100, max: number = 500): Promise<void> {
    const delay = Math.floor(Math.random() * (max - min + 1)) + min;
    await new Promise(resolve => setTimeout(resolve, delay));
  }

  static async humanLikeScroll(page: Page, scrollSteps: number = 3): Promise<void> {
    for (let i = 0; i < scrollSteps; i++) {
      const scrollAmount = Math.floor(Math.random() * 300) + 200;
      await page.mouse.wheel(0, scrollAmount);
      await this.humanLikeDelay(500, 1500);
    }
  }

  static async humanLikeClick(page: Page, selector: string): Promise<void> {
    const element = await page.locator(selector).first();
    const box = await element.boundingBox();

    if (box) {
      const x = box.x + box.width * (0.3 + Math.random() * 0.4);
      const y = box.y + box.height * (0.3 + Math.random() * 0.4);

      await page.mouse.move(x, y, { steps: Math.floor(Math.random() * 10) + 5 });
      await this.humanLikeDelay(50, 150);
      await page.mouse.click(x, y);
    } else {
      await element.click();
    }
  }

  private static getRandomUserAgent(): string {
    return this.USER_AGENTS[Math.floor(Math.random() * this.USER_AGENTS.length)];
  }

  private static getRandomViewport(): { width: number; height: number } {
    return this.VIEWPORTS[Math.floor(Math.random() * this.VIEWPORTS.length)];
  }
}

export class CircuitBreaker {
  private failureCount = 0;
  private lastFailureTime?: number;
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED';

  constructor(
    private failureThreshold: number = 5,
    private timeoutMs: number = 60000
  ) {}

  async execute<T>(operation: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      if (this.shouldAttemptReset()) {
        this.state = 'HALF_OPEN';
      } else {
        throw new Error('Circuit breaker is OPEN - too many failures');
      }
    }

    try {
      const result = await operation();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private shouldAttemptReset(): boolean {
    return !this.lastFailureTime ||
           (Date.now() - this.lastFailureTime) > this.timeoutMs;
  }

  private onSuccess(): void {
    this.failureCount = 0;
    this.state = 'CLOSED';
  }

  private onFailure(): void {
    this.failureCount++;
    this.lastFailureTime = Date.now();

    if (this.failureCount >= this.failureThreshold) {
      this.state = 'OPEN';
    }
  }

  getState(): string {
    return this.state;
  }
}

export class RetryManager {
  static async withRetry<T>(
    operation: () => Promise<T>,
    maxRetries: number = 3,
    baseDelay: number = 1000,
    maxDelay: number = 30000,
    exponentialBase: number = 2
  ): Promise<T> {
    let lastError: any;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await operation();
      } catch (error: any) {
        lastError = error;

        if (attempt === maxRetries) {
          break;
        }

        if (this.isNonRetryableError(error)) {
          throw error;
        }

        const delay = Math.min(
          baseDelay * Math.pow(exponentialBase, attempt),
          maxDelay
        );

        const jitterDelay = delay * (0.5 + Math.random() * 0.5);

        console.log(`Attempt ${attempt + 1} failed, retrying in ${jitterDelay}ms...`);
        await new Promise(resolve => setTimeout(resolve, jitterDelay));
      }
    }

    throw lastError;
  }

  private static isNonRetryableError(error: any): boolean {
    if (error.message?.includes('403') || error.message?.includes('Forbidden')) {
      return true;
    }

    if (error.message?.includes('404') || error.message?.includes('Not Found')) {
      return true;
    }

    if (error.message?.includes('blocked') || error.message?.includes('banned')) {
      return true;
    }

    return false;
  }
}

export class RateLimitManager {
  private lastRequestTime: Map<string, number> = new Map();
  private requestCounts: Map<string, number> = new Map();
  private windowStart: Map<string, number> = new Map();

  constructor(
    private requestsPerMinute: number = 30,
    private minDelayMs: number = 2000
  ) {}

  async waitForSlot(domain: string): Promise<void> {
    const now = Date.now();
    const lastRequest = this.lastRequestTime.get(domain) || 0;
    const timeSinceLastRequest = now - lastRequest;

    if (timeSinceLastRequest < this.minDelayMs) {
      const waitTime = this.minDelayMs - timeSinceLastRequest;
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }

    await this.enforceRateLimit(domain);
    this.lastRequestTime.set(domain, Date.now());
  }

  private async enforceRateLimit(domain: string): Promise<void> {
    const now = Date.now();
    const windowStart = this.windowStart.get(domain) || now;
    const requestCount = this.requestCounts.get(domain) || 0;

    if (now - windowStart >= 60000) {
      this.windowStart.set(domain, now);
      this.requestCounts.set(domain, 0);
      return;
    }

    if (requestCount >= this.requestsPerMinute) {
      const waitTime = 60000 - (now - windowStart);
      console.log(`Rate limit reached for ${domain}, waiting ${waitTime}ms`);
      await new Promise(resolve => setTimeout(resolve, waitTime));
      await this.enforceRateLimit(domain);
      return;
    }

    this.requestCounts.set(domain, requestCount + 1);
  }
}