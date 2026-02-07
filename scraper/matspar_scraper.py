"""
CookWise - Matspar.se Scraper (Proof of Concept)
Uses Matspar.se's internal API to get price comparison data
across ICA, Willys, Coop, and Hemköp.
"""

import json
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_BASE = "https://api.matspar.se"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}

# Supplier ID -> Store chain name (discovered from /suppliers endpoint)
SUPPLIER_MAP = {
    "17": "ICA",
    "13": "Coop",
    "15": "Willys",
    "16": "Hemköp",
    "11": "MatHem",
    "18": "Citygross",
}

# Grocery categories to scrape (from /categories endpoint)
CATEGORY_SLUGS = [
    "kategori/frukt-gront",
    "kategori/mejeri-ost-agg",
    "kategori/kott-fagel-chark",
    "kategori/fisk-skaldjur",
    "kategori/brod-bageri",
    "kategori/skafferi",
    "kategori/dryck",
]


def api_get(endpoint: str) -> dict:
    """GET request to Matspar API."""
    url = f"{API_BASE}/{endpoint}"
    req = Request(url, headers=HEADERS)
    resp = urlopen(req, timeout=15)
    return json.loads(resp.read().decode("utf-8"))


def api_post_slug(slug: str) -> dict:
    """POST to /slug endpoint to get page data."""
    url = f"{API_BASE}/slug"
    body = json.dumps({"slug": slug}).encode("utf-8")
    req = Request(url, data=body, headers=HEADERS)
    resp = urlopen(req, timeout=15)
    return json.loads(resp.read().decode("utf-8"))


def parse_product(raw: dict, category: str = "") -> dict:
    """Convert a raw Matspar product dict to our format."""
    # Prices are in öre (cents), convert to kr
    base_price = raw.get("price", 0)
    base_price_kr = base_price / 100 if base_price else None

    # Extract per-chain prices from the `prices` field (supplier-level)
    chain_prices = {}
    for supplier_id, price_ore in raw.get("prices", {}).items():
        chain_name = SUPPLIER_MAP.get(supplier_id, f"Store-{supplier_id}")
        chain_prices[chain_name] = price_ore / 100 if price_ore else None

    # Extract per-chain promos
    chain_promos = {}
    promo_data = raw.get("promo", {})
    if isinstance(promo_data, dict):
        for supplier_id, promo in promo_data.items():
            if isinstance(promo, dict):
                chain_name = SUPPLIER_MAP.get(supplier_id, f"Store-{supplier_id}")
                promo_price = promo.get("price", 0)
                chain_promos[chain_name] = {
                    "price": promo_price / 100 if promo_price else None,
                    "type": promo.get("type", ""),
                }

    # Build store list with prices
    stores = []
    for chain, price in chain_prices.items():
        store_entry = {"chain": chain, "price": price}
        if chain in chain_promos:
            store_entry["promo_price"] = chain_promos[chain]["price"]
            store_entry["promo_type"] = chain_promos[chain]["type"]
        stores.append(store_entry)

    return {
        "product_name": raw.get("name", ""),
        "brand": raw.get("brand", ""),
        "weight": raw.get("weight_pretty", ""),
        "source": "matspar.se",
        "product_id": raw.get("productid"),
        "slug": raw.get("slug", ""),
        "base_price": base_price_kr,
        "median_price": raw.get("median_price", 0) / 100 if raw.get("median_price") else None,
        "stores": stores,
        "category": category,
        "scraped_at": datetime.now().isoformat(),
    }


def scrape_matspar_search(query: str) -> list:
    """Search for products via the /slug API with search parameter."""
    print(f"\n[Matspar] Searching for '{query}'...")
    try:
        result = api_post_slug(f"/?q={query}")
        payload = result.get("payload", [])
        if isinstance(payload, list):
            products = [parse_product(p) for p in payload if p.get("name")]
            print(f"[Matspar] Search '{query}': {len(products)} products")
            return products
    except Exception as e:
        print(f"[Matspar] Search failed for '{query}': {e}")
    return []


def scrape_matspar_category(category_slug: str) -> list:
    """Scrape products from a category via the /slug API."""
    print(f"[Matspar] Fetching category: {category_slug}...")
    try:
        result = api_post_slug(f"/{category_slug}")
        payload = result.get("payload", {})

        products = []
        category_name = category_slug.replace("kategori/", "").replace("-", " ").title()

        if isinstance(payload, dict):
            # Category pages nest products under sub-category IDs
            categories = payload.get("categories", {})
            for cat_id, cat_data in categories.items():
                if isinstance(cat_data, dict):
                    for raw in cat_data.get("products", []):
                        if raw.get("name"):
                            products.append(parse_product(raw, category_name))

            # Also check top-level products
            for raw in payload.get("products", []):
                if raw.get("name"):
                    products.append(parse_product(raw, category_name))

        elif isinstance(payload, list):
            for raw in payload:
                if isinstance(raw, dict) and raw.get("name"):
                    products.append(parse_product(raw, category_name))

        # Deduplicate by product_id
        seen = set()
        unique = []
        for p in products:
            pid = p.get("product_id")
            if pid and pid not in seen:
                seen.add(pid)
                unique.append(p)

        print(f"[Matspar]   -> {len(unique)} products in {category_name}")
        return unique

    except HTTPError as e:
        print(f"[Matspar]   -> HTTP {e.code} for {category_slug}")
        return []
    except Exception as e:
        print(f"[Matspar]   -> Failed for {category_slug}: {e}")
        return []


def scrape_matspar_suppliers() -> dict:
    """Get the supplier (store chain) mapping."""
    print("[Matspar] Fetching supplier list...")
    try:
        suppliers = api_get("suppliers")
        grocery_stores = {}
        for sid, info in suppliers.items():
            if info.get("type") == "store" and "grocery" in info.get("categories", []):
                grocery_stores[sid] = {
                    "supplier_id": sid,
                    "name": info.get("longname", info.get("name", "")),
                    "active": info.get("active", False),
                }
        print(f"[Matspar] Found {len(grocery_stores)} grocery suppliers")
        return grocery_stores
    except Exception as e:
        print(f"[Matspar] Supplier fetch failed: {e}")
        return {}


def run_matspar_scraper() -> dict:
    """Main entry point for Matspar scraping test."""
    results = {
        "scraper": "matspar",
        "scraped_at": datetime.now().isoformat(),
        "products": [],
        "categories_scraped": [],
        "suppliers": {},
    }

    # Step 1: Get supplier info
    results["suppliers"] = scrape_matspar_suppliers()

    # Step 2: Scrape common grocery searches (quick wins)
    search_terms = ["mjölk", "bröd", "kyckling", "potatis", "ris"]
    for term in search_terms:
        try:
            products = scrape_matspar_search(term)
            results["products"].extend(products)
        except Exception as e:
            print(f"[Matspar] Search '{term}' failed: {e}")

    # Step 3: Scrape categories
    for cat_slug in CATEGORY_SLUGS[:4]:  # Limit for PoC
        try:
            cat_products = scrape_matspar_category(cat_slug)
            results["products"].extend(cat_products)
            results["categories_scraped"].append(cat_slug)
        except Exception as e:
            print(f"[Matspar] Category {cat_slug} failed: {e}")

    # Deduplicate by product_id
    seen = set()
    unique = []
    for p in results["products"]:
        pid = p.get("product_id")
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)
        elif not pid:
            unique.append(p)
    results["products"] = unique

    return results


if __name__ == "__main__":
    results = run_matspar_scraper()
    print("\n" + "=" * 60)
    print("MATSPAR SCRAPER RESULTS")
    print("=" * 60)
    print(f"Products found: {len(results['products'])}")
    print(f"Categories scraped: {results['categories_scraped']}")
    print(f"Suppliers: {list(results['suppliers'].values())}")

    if results["products"]:
        print("\n--- SAMPLE PRODUCTS ---")
        for p in results["products"][:15]:
            stores_str = ", ".join(
                f"{s['chain']}:{s['price']:.2f}kr" + (f"(promo:{s['promo_price']:.2f})" if 'promo_price' in s else "")
                for s in p.get("stores", [])[:4]
            )
            print(f"  {p['product_name']} ({p.get('brand', '')}) - {p.get('weight', '')}")
            print(f"    Base: {p['base_price']}kr | Stores: {stores_str}")

    # Save results
    output_path = "/Users/mdasifiqbalahmed/Documents/Projects/CookWise/scraper/tests/matspar_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_path}")
