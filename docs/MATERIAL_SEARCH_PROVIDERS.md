# Simplified-Chinese material search providers

X2RED's material library uses a provider chain rather than treating RSS as the primary discovery mechanism.

## Auto priority

1. `serpapi_baidu`
2. `dataforseo_baidu`
3. `tavily`
4. `brave`
5. `gdelt`

Only configured providers are called. Every attempt is returned to the UI as `skipped`, `failed`, `empty` or `ok` so provider fallback is visible rather than silent.

## SerpApi Baidu

```env
X2RED_SERPAPI_API_KEY=your-key
```

The adapter calls the Baidu engine with Simplified-Chinese filtering and up to 50 organic results.

## DataForSEO Baidu

```env
X2RED_DATAFORSEO_LOGIN=your-login
X2RED_DATAFORSEO_PASSWORD=your-password
```

The adapter uses the live advanced Baidu organic endpoint, `zh_CN`, China location code `2156`, desktop/macOS and `get_website_url=true`. DataForSEO documents that direct URL resolution materially increases the task price, so this provider is second in the default order.

## Tavily

```env
X2RED_TAVILY_API_KEY=your-key
X2RED_TAVILY_SEARCH_DEPTH=basic
```

The adapter uses the China country preference, general topic and optional day/week/month/year time range.

## Brave Search

```env
X2RED_BRAVE_SEARCH_API_KEY=your-key
```

The adapter requests China-region results with Simplified-Chinese search and interface language.

## Browser extraction fallback

```env
X2RED_MATERIAL_BROWSER_ENABLED=true
X2RED_MATERIAL_BROWSER_TIMEOUT_SECONDS=40
X2RED_MATERIAL_BROWSER_WAIT_MS=1800
```

Article import first uses ordinary HTTP and Trafilatura. When the extracted article body is too short, X2RED starts a new headless Chromium context with no saved login state or cookies, renders the public page, and extracts again.

Every browser request is checked against the public-address gate. Navigation to localhost, private, link-local or reserved networks is aborted. Article navigation also uses the hardened robots redirect checks.

The browser fallback does not solve login walls, paywalls or CAPTCHAs. Those pages remain unimportable unless the publisher exposes a public article URL.
