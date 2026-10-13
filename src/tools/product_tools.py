import json
from pathlib import Path
from typing import TypedDict


class Product(TypedDict):
    id: str
    name: str
    category: str
    price_inr: int
    stock_quantity: int


class ProductNotFoundError(LookupError):
    """Raised when a requested product ID is absent from the catalog."""


def load_products() -> list[Product]:
    """Load and return product records from the repository's JSON fixture."""
    data_path = Path(__file__).resolve().parents[2] / "data" / "products.json"
    with data_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("Product catalog must contain a JSON list")
    return payload


class ProductTools:
    """Deterministic product operations over an injected or fixture catalog."""

    def __init__(self, products: list[Product] | None = None) -> None:
        self._products = load_products() if products is None else products

    def get_all_products(self) -> list[Product]:
        return list(self._products)

    def search_products(
        self,
        category: str,
        max_price_inr: int | None = None,
        in_stock_only: bool = False,
    ) -> list[Product]:
        """Find products matching category, optional budget, and stock criteria."""
        matches = [product for product in self._products if product["category"] == category]
        if max_price_inr is not None:
            matches = [product for product in matches if product["price_inr"] <= max_price_inr]
        if in_stock_only:
            matches = [product for product in matches if product["stock_quantity"] > 0]
        return matches

    def get_product(self, product_id: str) -> Product:
        """Return a product by ID or raise ProductNotFoundError."""
        for product in self._products:
            if product["id"] == product_id:
                return product
        raise ProductNotFoundError(f"Product not found: {product_id}")

    def get_product_price(self, product_id: str) -> dict[str, str | int]:
        """Return the product's ID, name, and price in INR."""
        product = self.get_product(product_id)
        return {
            "product_id": product["id"],
            "name": product["name"],
            "price_inr": product["price_inr"],
        }

    def check_inventory(self, product_id: str) -> dict[str, str | int | bool]:
        """Return product availability and the current quantity."""
        product = self.get_product(product_id)
        quantity = product["stock_quantity"]
        return {
            "product_id": product["id"],
            "name": product["name"],
            "stock_quantity": quantity,
            "in_stock": quantity > 0,
        }


# Module-level functions are convenient for direct use and small examples.
def get_all_products() -> list[Product]:
    return ProductTools().get_all_products()


def search_products(
    category: str,
    max_price_inr: int | None = None,
    in_stock_only: bool = False,
) -> list[Product]:
    return ProductTools().search_products(category, max_price_inr, in_stock_only)


def get_product(product_id: str) -> Product:
    return ProductTools().get_product(product_id)


def get_product_price(product_id: str) -> dict[str, str | int]:
    return ProductTools().get_product_price(product_id)


def check_inventory(product_id: str) -> dict[str, str | int | bool]:
    return ProductTools().check_inventory(product_id)