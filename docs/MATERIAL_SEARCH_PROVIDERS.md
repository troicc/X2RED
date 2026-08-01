# Simplified-Chinese material discovery and extraction

X2RED's **原料库** separates web discovery from article extraction. Each layer
uses a replaceable provider chain. RSS, Atom and sitemap inputs remain available
only through a deprecated compatibility endpoint and are not shown in the main
material-library interface.

## Search provider priority

1. `serpapi_baidu`
2. `dataforseo_baidu`
3. `firecrawl`
4. `brave`
5. `jina`
6. `tavily`
7. `gdelt`

Configured providers are called in order. Jina Search can also run without a key
at its public low-rate limit. Each attempt is returned to the UI as `skipped`,
`failed`, `empty` or `ok`. GDELT remains last because it is a Chinese-news index,
not a general Simplified-Chinese web index.

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

SerpApi and DataForSEO use Baidu results. Firecrawl, Brave, Jina and Tavily add
independent discovery sources with Chinese queries and regional preferences.

## Article extraction priority

1. Firecrawl Scrape when its key is configured;
2. Jina Reader;
3. public HTML plus Trafilatura;
4. local Playwright only when explicitly enabled.

```env
X2RED_MATERIAL_EXTRACT_PROVIDER=auto
X2RED_FIRECRAWL_API_KEY=
X2RED_FIRECRAWL_BASE_URL=https://api.firecrawl.dev
X2RED_JINA_API_KEY=
X2RED_JINA_READER_BASE_URL=https://r.jina.ai
X2RED_MATERIAL_BROWSER_ENABLED=false
```

Jina Reader can run at its public low-rate limit. A key increases the available
quota. Firecrawl is skipped automatically when its key is absent. The local
Playwright compatibility adapter is disabled by default.

## Validation and provenance

Before calling an extractor, X2RED permits only public HTTP/HTTPS targets,
rejects local and private network addresses, checks `robots.txt`, and applies a
per-host request interval. Provider-reported final URLs and image URLs are
validated again before storage.

Imported records retain the canonical URL, extraction engine, attempt history,
capture time and the default `limited_quote` rights state. The provider chain is
limited to publicly accessible pages and does not reuse a personal browser
session.
