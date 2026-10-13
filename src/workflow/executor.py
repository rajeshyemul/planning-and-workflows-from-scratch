from collections.abc import Callable
from typing import cast

from src.planner.contracts import JSONValue, PlanStep
from src.tools.product_tools import ProductTools


class ToolExecutor:
    """Dispatch validated plan steps only to explicitly registered tools."""

    def __init__(self, product_tools: ProductTools | None = None) -> None:
        tools = product_tools or ProductTools()
        self._handlers: dict[str, Callable[..., object]] = {
            "search_products": tools.search_products,
            "get_product": tools.get_product,
            "get_product_price": tools.get_product_price,
            "check_inventory": tools.check_inventory,
        }

    def execute(self, step: PlanStep) -> JSONValue:
        """Execute a step using its tool name and structured arguments."""
        handler = self._handlers.get(step.tool_name)
        if handler is None:
            raise ValueError(f"Unsupported tool: {step.tool_name}")
        result = handler(**step.tool_input)
        return cast(JSONValue, result)