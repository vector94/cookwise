"""
CookWise - ICA Store Scraper (Proof of Concept)
Scrapes store locations and weekly offers from ICA.se
"""

import json
import re
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}


def fetch_url(url: str) -> str:
    req = Request(url, headers=HEADERS)
    resp = urlopen(req, timeout=15)
    return resp.read().decode("utf-8")


def scrape_ica_stores(city: str = "karlskrona") -> list[dict]:
    """Scrape ICA store locations for a given city."""
    print(f"\n[ICA] Fetching stores in {city}...")
    url = f"https://www.ica.se/butiker/{city}/"
    html = fetch_url(url)
    soup = BeautifulSoup(html, "lxml")

    stores = []
    seen_ids = set()

    # ICA embeds store data in script tags or structured HTML
    # Look for store cards - links to individual store pages
    store_links = soup.find_all("a", href=re.compile(r"/butiker/.+-\d+/$"))

    for link in store_links:
        href = link.get("href", "")
        # Extract store ID from URL pattern like /butiker/maxi-ica-stormarknad-karlskrona-1004028/
        store_id_match = re.search(r"-(\d+)/$", href)
        store_id = store_id_match.group(1) if store_id_match else None

        if not store_id or store_id in seen_ids:
            continue
        seen_ids.add(store_id)

        # Extract the last path segment as slug (href may have nested paths like /butiker/maxi/karlskrona/maxi-ica-...-1004028/)
        last_segment = href.rstrip("/").rsplit("/", 1)[-1]
        # Remove the trailing store ID: "maxi-ica-stormarknad-karlskrona-1004028" -> "maxi-ica-stormarknad-karlskrona"
        slug = re.sub(r"-\d+$", "", last_segment)
        # Convert slug to readable name: "maxi-ica-stormarknad-karlskrona" -> "Maxi ICA Stormarknad Karlskrona"
        store_name = slug.replace("-", " ").title() if slug else link.get_text(strip=True)

        # Try to get address from sibling/parent elements
        parent = link.find_parent("div") or link.find_parent("li")
        address = ""
        if parent:
            address_el = parent.find(string=re.compile(r"vägen|gatan|torget|väg", re.I))
            if address_el:
                address = address_el.strip()

        stores.append({
            "store_id": store_id,
            "store_name": store_name,
            "chain": "ICA",
            "address": address,
            "city": city.capitalize(),
            "url": f"https://www.ica.se{href}",
            "slug": slug,
        })

    print(f"[ICA] Found {len(stores)} stores")
    return stores


def scrape_ica_offers(store_name_slug: str, store_id: str) -> list[dict]:
    """Scrape current weekly offers for a specific ICA store."""
    print(f"\n[ICA] Fetching offers for store {store_id} ({store_name_slug})...")

    url = f"https://www.ica.se/erbjudanden/{store_name_slug}-{store_id}/"
    html = fetch_url(url)

    offers = []

    # Strategy 1: Look for __INITIAL_DATA__ or __NEXT_DATA__ JSON
    initial_data_match = re.search(
        r'window\.__INITIAL_DATA__\s*=\s*({.*?});?\s*</script>',
        html, re.DOTALL
    )
    next_data_match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )

    json_data = None
    if initial_data_match:
        try:
            json_data = json.loads(initial_data_match.group(1))
            print("[ICA] Found __INITIAL_DATA__ embedded JSON")
        except json.JSONDecodeError:
            pass
    elif next_data_match:
        try:
            json_data = json.loads(next_data_match.group(1))
            print("[ICA] Found __NEXT_DATA__ embedded JSON")
        except json.JSONDecodeError:
            pass

    if json_data:
        offers = extract_offers_from_json(json_data, store_id)

    # Strategy 2: Parse HTML structure directly
    if not offers:
        print("[ICA] Falling back to HTML parsing...")
        offers = extract_offers_from_html(html, store_id)

    print(f"[ICA] Found {len(offers)} offers")
    return offers


def extract_offers_from_json(data: dict, store_id: str) -> list[dict]:
    """Recursively search JSON data for offer/product information."""
    offers = []

    def search_dict(d, depth=0):
        if depth > 10:
            return
        if isinstance(d, dict):
            # Look for product-like objects
            has_price = any(k in d for k in ["price", "salePrice", "currentPrice",
                                              "priceValue", "savePrice", "offerPrice"])
            has_name = any(k in d for k in ["name", "productName", "title", "heading"])

            if has_price and has_name:
                name = d.get("name") or d.get("productName") or d.get("title") or d.get("heading", "")
                offer = {
                    "product_name": str(name),
                    "store_id": store_id,
                    "chain": "ICA",
                    "regular_price": d.get("regularPrice") or d.get("originalPrice"),
                    "sale_price": d.get("price") or d.get("salePrice") or d.get("currentPrice"),
                    "discount_text": d.get("savePrice") or d.get("promotionText") or d.get("offerCondition", ""),
                    "valid_from": d.get("validFrom") or d.get("startDate"),
                    "valid_to": d.get("validTo") or d.get("endDate"),
                    "image_url": d.get("image") or d.get("imageUrl") or d.get("imageURL", ""),
                    "category": d.get("category") or d.get("categoryName", ""),
                    "scraped_at": datetime.now().isoformat(),
                }
                if offer["product_name"]:
                    offers.append(offer)

            for v in d.values():
                search_dict(v, depth + 1)
        elif isinstance(d, list):
            for item in d:
                search_dict(item, depth + 1)

    search_dict(data)
    return offers


def extract_offers_from_html(html: str, store_id: str) -> list[dict]:
    """Parse offers from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")
    offers = []

    # Look for offer/product cards - ICA uses various class patterns
    product_patterns = [
        {"class": re.compile(r"offer|product|campaign|deal", re.I)},
        {"data-testid": re.compile(r"offer|product", re.I)},
    ]

    seen_names = set()
    for pattern in product_patterns:
        cards = soup.find_all(["div", "article", "li", "a"], attrs=pattern)
        for card in cards:
            text = card.get_text(separator=" | ", strip=True)
            # Extract price patterns like "29,90" or "2 för 50"
            price_match = re.search(r'(\d+[,:]\d{2})\s*(?:kr)?', text)
            multi_match = re.search(r'(\d+)\s*(?:för|st)\s*(\d+[,:.]?\d*)\s*kr', text, re.I)

            name_parts = text.split("|")
            name = name_parts[0].strip() if name_parts else ""

            if len(name) < 3 or len(name) > 100 or name in seen_names:
                continue

            seen_names.add(name)

            offer = {
                "product_name": name,
                "store_id": store_id,
                "chain": "ICA",
                "regular_price": None,
                "sale_price": None,
                "discount_text": "",
                "scraped_at": datetime.now().isoformat(),
            }

            if multi_match:
                qty = multi_match.group(1)
                price = multi_match.group(2).replace(",", ".")
                offer["discount_text"] = f"{qty} för {price} kr"
                offer["sale_price"] = f"{price} kr"
            elif price_match:
                price = price_match.group(1).replace(",", ".")
                offer["sale_price"] = f"{price} kr"

            if offer["sale_price"]:
                offers.append(offer)

    return offers


def run_ica_scraper():
    """Main entry point for ICA scraping test."""
    results = {
        "scraper": "ica",
        "scraped_at": datetime.now().isoformat(),
        "stores": [],
        "offers": [],
    }

    # Step 1: Get stores
    try:
        stores = scrape_ica_stores("karlskrona")
        results["stores"] = stores
    except Exception as e:
        print(f"[ICA] Store scraping failed: {e}")
        # Use known store as fallback
        stores = [{"store_id": "1004028", "store_name": "Maxi ICA Stormarknad Karlskrona"}]

    # Step 2: Get offers from first store (prefer Maxi for better selection)
    if stores:
        # Try to find Maxi store first (bigger store = more offers)
        store = stores[0]
        for s in stores:
            if "maxi" in s.get("store_name", "").lower():
                store = s
                break

        slug = store.get("slug", "")
        if not slug:
            slug = "maxi-ica-stormarknad-karlskrona"
        store_id = store["store_id"]

        try:
            offers = scrape_ica_offers(slug, store_id)
            results["offers"] = offers
        except HTTPError as e:
            print(f"[ICA] Offers scraping failed (HTTP {e.code}), trying known URL...")
            try:
                offers = scrape_ica_offers("maxi-ica-stormarknad-karlskrona", "1004028")
                results["offers"] = offers
            except Exception as e2:
                print(f"[ICA] Fallback also failed: {e2}")
        except Exception as e:
            print(f"[ICA] Offers scraping failed: {e}")

    return results


if __name__ == "__main__":
    results = run_ica_scraper()
    print("\n" + "=" * 60)
    print("ICA SCRAPER RESULTS")
    print("=" * 60)
    print(f"Stores found: {len(results['stores'])}")
    print(f"Offers found: {len(results['offers'])}")

    if results["stores"]:
        print("\n--- STORES ---")
        for s in results["stores"][:5]:
            print(f"  {s['store_name']} (ID: {s['store_id']})")

    if results["offers"]:
        print("\n--- SAMPLE OFFERS ---")
        for o in results["offers"][:10]:
            print(f"  {o['product_name']}")
            print(f"    Sale: {o['sale_price']} | Discount: {o['discount_text']}")

    # Save results
    output_path = "/Users/mdasifiqbalahmed/Documents/Projects/CookWise/scraper/tests/ica_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_path}")
