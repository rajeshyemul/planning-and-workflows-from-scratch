from typing import Any

from src.planner.contracts import Plan


def find_best_candidate(plan: Plan) -> dict[str, Any] | None:
	"""Choose the lowest-priced product satisfying an executed search step."""
	candidates: list[dict[str, Any]] = []
	unavailable_product_ids = {
		step.result.get("product_id")
		for step in plan.steps
		if step.tool_name == "check_inventory"
		and isinstance(step.result, dict)
		and step.result.get("in_stock") is False
	}
	for step in plan.steps:
		if step.tool_name != "search_products" or not isinstance(step.result, list):
			continue
		category = step.tool_input["category"]
		max_price = step.tool_input.get("max_price_inr")
		in_stock_only = step.tool_input.get("in_stock_only", False)
		for product in step.result:
			if not isinstance(product, dict) or product.get("category") != category:
				continue
			if product.get("id") in unavailable_product_ids:
				continue
			price = product.get("price_inr")
			if not isinstance(price, int) or (max_price is not None and price > max_price):
				continue
			if in_stock_only and product.get("stock_quantity", 0) <= 0:
				continue
			candidates.append(product)
	if not candidates:
		return None
	return min(candidates, key=lambda product: product["price_inr"])