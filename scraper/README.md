# CookWise Scraper - PoC Test Results

## Legal / Terms of Service

### Matspar.se

- **ToS page**: https://www.matspar.se/anvandarvillkor
- **Cookie policy**: https://www.matspar.se/cookie-policy
- **Company**: Matspar i Sverige AB, org nr 559007-6351, Stationsgatan 2, Sundbyberg
- **robots.txt**: Permissive (`Allow: /`), only blocks `/checkout`, `/kundvagn`, `/tack`, `/mina-sidor`
- **Key ToS clause (Intellectual Property)**: "You may only use Website content for your own use of Services and may not use content in violation of applicable law or these terms. You may use such content only for the purpose of using Services."
- **No explicit mention** of API usage, automated access, scraping, or developer licensing
- **No public API** is offered - the endpoints we use are internal/undocumented
- **Conclusion**: Using their data in a separate product is **not legal** under their current ToS. For any public or commercial use, contact them to request permission or a data licensing agreement first

### ICA.se

- No specific API terms checked yet. ICA has an official developer program worth exploring for production use.

---

## What Works

### Matspar.se API (Best Source - covers ICA, Coop, Willys, Hemköp)

Internal REST API at `https://api.matspar.se`. No auth needed for reads.

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/suppliers` | GET | Store chains: ICA(17), Coop(13), Willys(15), Hemköp(16), MatHem(11) |
| `/categories` | GET | 743 product categories with paths |
| `/warehouses` | GET | 4786 individual store locations |
| `/slug` | POST `{"slug": "/kategori/frukt-gront"}` | Products with per-store prices and promos |

- Prices are in **öre** (divide by 100 for kr)
- `prices` field = per-chain prices (keys: `"17"`=ICA, `"13"`=Coop, `"15"`=Willys, `"16"`=Hemköp)
- `promo` field = per-chain promo info (types: `FIXED`, `X_FOR_FIXED`)
- `w_prices` / `w_promo` = per-individual-warehouse prices/promos
- Category products are nested: `payload.categories.{catId}.products[]` (not `payload.products`)
- Correct category slugs: `frukt-gront`, `mejeri-ost-agg`, `kott-fagel-chark`, `fisk-skaldjur`, `brod-bageri`, `skafferi`, `dryck`

### ICA.se HTML Scraping

- **Stores**: `https://www.ica.se/butiker/{city}/` - 15 stores found in Karlskrona
- **Offers**: `https://www.ica.se/erbjudanden/{slug}-{storeId}/` - 23 offers from Maxi ICA
- Slug = last URL segment without store ID (e.g. `maxi-ica-stormarknad-karlskrona`)
- Store name comes from URL slug, not link text (link text is generic CTA)

### Willys Store API (stores only)

- `https://www.willys.se/axfood/rest/store?q=karlskrona` - Returns store locations with coordinates. No auth needed.

---

## What Doesn't Work

| Tried | Result | Why |
|-------|--------|-----|
| Matspar `/search` POST | 400 csrf_token_invalid | Needs CSRF token from `POST /csrf` first |
| Matspar `/slug` with `/?q=mjolk` | Empty results | Search needs CSRF flow |
| Matspar homepage `__INITIAL_STATE__` | Products array empty | Products loaded client-side after page load |
| Matspar `__PAGEDATA__` | Doesn't exist | Correct var is `__INITIAL_STATE__` |
| Willys product/campaign APIs | 400/404 | Need session auth cookies |
| Willys HTML scraping | No data | Fully JS-rendered |
| Coop.se (all approaches) | No data | Fully JS-rendered, no API found |
| Old Matspar category slugs | 404 | `frukt-och-gront` wrong, correct is `frukt-gront` |

---

## Files

- `ica_scraper.py` - ICA stores + offers
- `matspar_scraper.py` - Matspar API scraper (multi-store prices)
- `run_test.py` - Full test runner, maps to CookWise data model
- `tests/` - JSON output from last run

```bash
pip install beautifulsoup4 lxml
python scraper/run_test.py    # runs everything
```
