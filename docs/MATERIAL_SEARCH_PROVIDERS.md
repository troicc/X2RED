# Simplified-Chinese material discovery and extraction

X2RED's **原料库** treats search and article extraction as two independent,
replaceable provider chains. RSS, Atom and sitemap inputs remain available only
through the deprecated compatibility API; they are not shown in the primary UI.

## Search provider auto priority

1. `serpapi_baidu`
2. `dataforseo_baidu`
3. `firecrawl`
4. `brave`
5. `jina`
6. `tavily`
7. `gdelt`

Only configured commercial providers are called. Every attempt is returned as
`skipped`, `failed`, `empty` or `ok`, so failover is visible in the material UI.
GDELT requires no key and is deliberately last because it is a Chinese-news
index, not a general Simplified-Chinese web index.

## Search configuration

```env
X2RED_MATERIAL_SEARCH_PROVIDER=auto

X2RED_SERPAPI_API_KEY=
X2RED_DATAFORSEO_LOGIN=
X2RED_DATAFORSEO_PASSWORD=

X2RED_FIRECRAWL_API_KEY=
X2RED_BRAVE_SEARCH_API_KEY=
X2RED_JINA_API_KEY=
X2RED_TAVILY_API_KEY=
```

SerpApi and DataForSEO use Baidu results. Firecrawl Search, Brave Search, Jina
Search and Tavily provide independent commercial fallbacks with Chinese queries
and China-region preferences where their APIs support them.

## Article extraction auto priority

1. Firecrawl Scrape, when `X2RED_FIRECRAWL_API_KEY` is configured;
2. Jina Reader;
3. ordinary public HTML plus Trafilatura;
4. local Playwright only when explicitly enabled.

```env
X2RED_MATERIAL_EXTRACT_PROVIDER=auto
X2RED_FIRECRAWL_API_KEY=
X2RED_FIRECRAWL_BASE_URL=https://api.firecrawl.dev
X2RED_JINA_API_KEY=
X2RED_JINA_READER_BASE_URL=https://r.jina.ai
```

Jina Reader can be used at its unauthenticated low-rate limit. Supplying a Jina
key raises the provider limit. Firecrawl is skipped automatically when no key is
configured.

The local Playwright fallback is retained only for compatibility and is disabled
by default:

```env
X2RED_MATERIAL_BROWSER_ENABLED=false
```

## Safety and provenance

Before any extractor is called, X2RED:

- permits only public HTTP/HTTPS URLs;
- rejects localhost, private, link-local and reserved addresses;
- checks the target site's `robots.txt`;
- applies a per-host request interval.

Provider-reported final URLs and image URLs are validated again before storage.
Imported records keep the canonical URL, extraction engine, failed/successful
attempts, capture time and a default `limited_quote` rights state.

The extraction chain does not attempt to solve login walls, paywalls or
CAPTCHAs and does not reuse a personal browser session.
