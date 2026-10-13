from src.planner.contracts import Plan


MAX_PLAN_STEPS = 10
SUPPORTED_PRODUCT_CATEGORIES = {"running_shoes", "walking_shoes"}

TOOL_INPUT_RULES: dict[str, dict[str, dict[str, type]]] = {
    "search_products": {
        "required": {"category": str},
        "optional": {"max_price_inr": int, "in_stock_only": bool},
    },
    "get_product": {"required": {"product_id": str}, "optional": {}},
    "get_product_price": {"required": {"product_id": str}, "optional": {}},
    "check_inventory": {"required": {"product_id": str}, "optional": {}},
}


class PlanValidationError(ValueError):
    """Raised when a plan is malformed or requests unsupported work."""


def _validate_tool_input(step_id: str, tool_name: str, tool_input: dict) -> None:
    rules = TOOL_INPUT_RULES[tool_name]
    required = rules["required"]
    optional = rules["optional"]

    missing = required.keys() - tool_input.keys()
    if missing:
        raise PlanValidationError(
            f"Step {step_id!r} is missing required input(s): {', '.join(sorted(missing))}"
        )

    allowed = required.keys() | optional.keys()
    unexpected = tool_input.keys() - allowed
    if unexpected:
        raise PlanValidationError(
            f"Step {step_id!r} has unexpected input(s): {', '.join(sorted(unexpected))}"
        )

    for key, expected_type in (required | optional).items():
        if key not in tool_input:
            continue
        value = tool_input[key]
        if type(value) is not expected_type:
            raise PlanValidationError(
                f"Step {step_id!r} input {key!r} must be {expected_type.__name__}"
            )
        if isinstance(value, str) and not value.strip():
            raise PlanValidationError(f"Step {step_id!r} input {key!r} cannot be blank")
        if key == "category" and value not in SUPPORTED_PRODUCT_CATEGORIES:
            raise PlanValidationError(
                f"Step {step_id!r} input 'category' must be one of: "
                f"{', '.join(sorted(SUPPORTED_PRODUCT_CATEGORIES))}"
            )
        if key == "max_price_inr" and isinstance(value, int) and value < 0:
            raise PlanValidationError("max_price_inr cannot be negative")


def validate_plan(plan: Plan) -> None:
    """Raise PlanValidationError unless the plan is safe to execute."""
    if not isinstance(plan, Plan):
        raise PlanValidationError("plan must be a Plan instance")
    if not plan.goal.strip():
        raise PlanValidationError("goal cannot be blank")
    if not plan.steps:
        raise PlanValidationError("plan must contain at least one step")
    if len(plan.steps) > MAX_PLAN_STEPS:
        raise PlanValidationError(f"plan cannot contain more than {MAX_PLAN_STEPS} steps")

    seen_step_ids: set[str] = set()
    for step in plan.steps:
        if not step.step_id.strip():
            raise PlanValidationError("step ID cannot be blank")
        if step.step_id in seen_step_ids:
            raise PlanValidationError(f"duplicate step ID: {step.step_id}")
        seen_step_ids.add(step.step_id)
        if not step.objective.strip():
            raise PlanValidationError(f"step {step.step_id!r} objective cannot be blank")
        if step.tool_name not in TOOL_INPUT_RULES:
            raise PlanValidationError(f"unsupported tool: {step.tool_name}")
        if not isinstance(step.tool_input, dict):
            raise PlanValidationError(f"step {step.step_id!r} tool_input must be a dictionary")
        _validate_tool_input(step.step_id, step.tool_name, step.tool_input)