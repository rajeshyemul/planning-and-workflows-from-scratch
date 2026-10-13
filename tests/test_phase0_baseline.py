import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "data" / "products.json"


def test_catalog_fixture_is_valid_and_covers_baseline_cases():
    products = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    assert isinstance(products, list)
    assert products
    assert all(
        {"id", "name", "category", "price_inr", "stock_quantity"}.issubset(product)
        for product in products
    )

    running_shoes = [
        product for product in products if product["category"] == "running_shoes"
    ]
    assert any(
        product["price_inr"] < 5000 and product["stock_quantity"] > 0
        for product in running_shoes
    )
    assert any(
        product["stock_quantity"] == 0 for product in running_shoes
    )
    assert any(product["price_inr"] > 5000 for product in running_shoes)
