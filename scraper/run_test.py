"""
CookWise - Web Scraping Proof of Concept
Runs all scrapers and outputs data in CookWise data model format.

Maps scraped data to the entities from the SRS:
  - Store (store_id, store_name, latitude, longitude)
  - Sale_Item (sale_id, store_id, ingredient_id, sale_price, valid_from, valid_to)
  - Ingredient (ingredient_id, ingredient_name, category)
"""

import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from ica_scraper import run_ica_scraper
from matspar_scraper import run_matspar_scraper


def map_to_cookwise_model(ica_results: dict, matspar_results: dict) -> dict:
    """Map scraped data to CookWise SRS data model (DR1/DR2)."""

    cookwise_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "version": "PoC-0.1",
            "sources": ["ica.se", "matspar.se"],
        },
        "stores": [],
        "ingredients": [],
        "sale_items": [],
        "stats": {},
    }

    ingredient_counter = 1
    sale_counter = 1
    ingredient_map = {}  # name -> id

    # --- Map ICA Stores ---
    for store in ica_results.get("stores", []):
        cookwise_data["stores"].append({
            "store_id": f"ICA-{store['store_id']}",
            "store_name": store["store_name"],
            "chain": "ICA",
            "address": store.get("address", ""),
            "city": store.get("city", "Karlskrona"),
            "latitude": None,  # Would need geocoding API
            "longitude": None,
        })

    # --- Map ICA Offers to Sale Items ---
    for offer in ica_results.get("offers", []):
        product_name = offer["product_name"]

        # Create or reuse ingredient
        if product_name not in ingredient_map:
            ingredient_map[product_name] = f"ING-{ingredient_counter:04d}"
            cookwise_data["ingredients"].append({
                "ingredient_id": ingredient_map[product_name],
                "ingredient_name": product_name,
                "category": offer.get("category", "Uncategorized"),
                "source": "ica.se",
            })
            ingredient_counter += 1

        # Parse price
        sale_price = offer.get("sale_price")
        if isinstance(sale_price, str):
            import re
            price_match = re.search(r'(\d+[,.]?\d*)', str(sale_price))
            sale_price = float(price_match.group(1).replace(",", ".")) if price_match else None

        cookwise_data["sale_items"].append({
            "sale_id": f"SALE-{sale_counter:04d}",
            "store_id": f"ICA-{offer.get('store_id', '1004028')}",
            "ingredient_id": ingredient_map[product_name],
            "ingredient_name": product_name,
            "sale_price": sale_price,
            "regular_price": offer.get("regular_price"),
            "discount_text": offer.get("discount_text", ""),
            "valid_from": offer.get("valid_from"),
            "valid_to": offer.get("valid_to"),
            "source": "ica.se",
        })
        sale_counter += 1

    # --- Map Matspar Products ---
    for product in matspar_results.get("products", []):
        product_name = product["product_name"]

        # Create or reuse ingredient
        if product_name not in ingredient_map:
            ingredient_map[product_name] = f"ING-{ingredient_counter:04d}"
            cookwise_data["ingredients"].append({
                "ingredient_id": ingredient_map[product_name],
                "ingredient_name": product_name,
                "category": product.get("category", "Uncategorized"),
                "brand": product.get("brand", ""),
                "weight": product.get("weight", ""),
                "source": "matspar.se",
            })
            ingredient_counter += 1

        # Create sale items for each store chain
        stores = product.get("stores", [])
        for store_info in stores:
            chain = store_info.get("chain", "Unknown") if isinstance(store_info, dict) else str(store_info)
            sale_price = store_info.get("price") if isinstance(store_info, dict) else product.get("base_price")
            promo_price = store_info.get("promo_price") if isinstance(store_info, dict) else None

            cookwise_data["sale_items"].append({
                "sale_id": f"SALE-{sale_counter:04d}",
                "store_id": f"{chain.upper()}-GENERIC",
                "ingredient_id": ingredient_map[product_name],
                "ingredient_name": product_name,
                "sale_price": promo_price if promo_price else sale_price,
                "regular_price": sale_price if promo_price else None,
                "source": "matspar.se",
            })
            sale_counter += 1

    # --- Stats ---
    cookwise_data["stats"] = {
        "total_stores": len(cookwise_data["stores"]),
        "total_ingredients": len(cookwise_data["ingredients"]),
        "total_sale_items": len(cookwise_data["sale_items"]),
        "ica_offers": len(ica_results.get("offers", [])),
        "matspar_products": len(matspar_results.get("products", [])),
        "sources_used": ["ica.se", "matspar.se"],
    }

    return cookwise_data


def print_report(data: dict):
    """Print a human-readable summary report."""
    stats = data["stats"]

    print("\n" + "=" * 70)
    print("  COOKWISE WEB SCRAPING - PROOF OF CONCEPT RESULTS")
    print("=" * 70)
    print(f"  Generated: {data['metadata']['generated_at']}")
    print(f"  Sources:   {', '.join(stats['sources_used'])}")
    print()

    print("  DATA COLLECTED:")
    print(f"  {'Stores':.<40} {stats['total_stores']}")
    print(f"  {'Unique Ingredients':.<40} {stats['total_ingredients']}")
    print(f"  {'Sale Items':.<40} {stats['total_sale_items']}")
    print(f"  {'  from ICA.se':.<40} {stats['ica_offers']}")
    print(f"  {'  from Matspar.se':.<40} {stats['matspar_products']}")
    print()

    # Show stores
    if data["stores"]:
        print("  STORES FOUND:")
        for store in data["stores"][:8]:
            print(f"    - {store['store_name']} ({store['store_id']})")
        if len(data["stores"]) > 8:
            print(f"    ... and {len(data['stores']) - 8} more")
        print()

    # Show sample sale items
    if data["sale_items"]:
        print("  SAMPLE SALE ITEMS:")
        for item in data["sale_items"][:15]:
            price_str = f"{item['sale_price']} kr" if item['sale_price'] else item.get('discount_text', 'N/A')
            reg_str = f" (reg: {item['regular_price']} kr)" if item.get('regular_price') else ""
            print(f"    - {item['ingredient_name'][:45]:<45} {price_str}{reg_str}")
            print(f"      Store: {item['store_id']} | Source: {item['source']}")
        if len(data["sale_items"]) > 15:
            print(f"    ... and {len(data['sale_items']) - 15} more")
        print()

    # Feasibility assessment
    print("  FEASIBILITY ASSESSMENT:")
    print("  " + "-" * 50)

    ica_ok = stats["ica_offers"] > 0
    matspar_ok = stats["matspar_products"] > 0

    print(f"  ICA.se scraping:     {'WORKING' if ica_ok else 'FAILED'}")
    print(f"  Matspar.se scraping: {'WORKING' if matspar_ok else 'FAILED'}")
    print()

    if ica_ok or matspar_ok:
        print("  VERDICT: Web scraping IS FEASIBLE for CookWise prototype!")
        print("  Recommended approach:")
        if matspar_ok:
            print("    1. Use Matspar.se as primary data source (covers all 3 stores)")
        if ica_ok:
            print("    2. Use ICA.se directly for store-specific offers")
        print("    3. Add Willys/Coop via headless browser (Playwright) later")
    else:
        print("  VERDICT: Basic HTTP scraping insufficient.")
        print("  Next step: Try headless browser approach (Playwright)")

    print("=" * 70)


def main():
    print("CookWise Web Scraping PoC")
    print("Testing data extraction from Swedish grocery sources...\n")

    # Run ICA scraper
    print("=" * 40)
    print("PHASE 1: ICA.se")
    print("=" * 40)
    try:
        ica_results = run_ica_scraper()
    except Exception as e:
        print(f"ICA scraper crashed: {e}")
        ica_results = {"stores": [], "offers": []}

    # Run Matspar scraper
    print("\n" + "=" * 40)
    print("PHASE 2: Matspar.se")
    print("=" * 40)
    try:
        matspar_results = run_matspar_scraper()
    except Exception as e:
        print(f"Matspar scraper crashed: {e}")
        matspar_results = {"products": []}

    # Map to CookWise model
    print("\n" + "=" * 40)
    print("PHASE 3: Mapping to CookWise Data Model")
    print("=" * 40)
    cookwise_data = map_to_cookwise_model(ica_results, matspar_results)

    # Print report
    print_report(cookwise_data)

    # Save final output
    output_path = "/Users/mdasifiqbalahmed/Documents/Projects/CookWise/scraper/tests/cookwise_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cookwise_data, f, indent=2, ensure_ascii=False)
    print(f"\nFull data saved to: {output_path}")


if __name__ == "__main__":
    main()
