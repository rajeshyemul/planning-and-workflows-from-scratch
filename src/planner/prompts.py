PLAN_PROMPT_TEMPLATE = """You are creating a structured product-search plan.

Goal: {goal}

Return valid JSON with exactly this schema:
{{
  "steps": [
    {{
      "step_id": "string",
      "objective": "string",
      "tool_name": "one supported tool name",
      "tool_input": {{}}
    }}
  ]
}}

Rules:
- Use only these tools: search_products, get_product, get_product_price, check_inventory.
- For product discovery, make exactly one search_products step unless the user explicitly includes a product ID.
- Never invent product IDs, placeholders, or lookup steps for products that have not been returned by a tool.
- For search_products, use the exact category identifier running_shoes or walking_shoes, set in_stock_only to true only when the goal requests availability, and include max_price_inr when the goal states a budget.
- search_products requires category (string) and in_stock_only (boolean); max_price_inr is an optional integer.
- get_product, get_product_price, and check_inventory each require product_id (string).
- Keep tool_input aligned with the selected tool.
- Only include the minimum required fields for each tool.
- Use step IDs like step-1, step-2, step-3.
- Do not include markdown fences, commentary, or extra keys.
- Ensure the output is JSON parseable.
"""

REPLAN_PROMPT_TEMPLATE = """Revise the remaining steps of a product-search plan.

Original user goal (authoritative): {goal}
Reason replanning was triggered: {reason}
Latest observation: {observation}
Completed step IDs and results (preserve these; do not repeat their work): {completed}
Previous plan: {previous_plan}

Return only valid JSON with this shape:
{{
  "steps": [
    {{
      "step_id": "new-unique-step-id",
      "objective": "short explanation",
      "tool_name": "one supported tool name",
      "tool_input": {{}}
    }}
  ]
}}

Use only search_products, get_product, get_product_price, and check_inventory.
Return only remaining work. Do not include completed steps or execution metadata.
Do not include markdown fences or commentary.
"""


def build_plan_prompt(goal: str) -> str:
    """Build a prompt requesting a structured plan in the exact contract shape."""
    if not goal or not goal.strip():
        raise ValueError("goal cannot be blank")
    return PLAN_PROMPT_TEMPLATE.format(goal=goal)


def build_replan_prompt(
  goal: str,
  previous_plan: str,
  completed_steps: str,
  observation: str,
  reason: str,
) -> str:
  """Build a prompt that asks only for validated remaining work."""
  if not goal or not goal.strip():
    raise ValueError("goal cannot be blank")
  return REPLAN_PROMPT_TEMPLATE.format(
    goal=goal,
    previous_plan=previous_plan,
    completed=completed_steps,
    observation=observation,
    reason=reason,
  )
