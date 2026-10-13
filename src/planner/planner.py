import json
import re
from collections.abc import Callable
from typing import Any, Protocol, cast

from src.llm.client import LLMClient
from src.planner.contracts import JSONValue, Plan, PlanStep
from src.planner.prompts import build_plan_prompt, build_replan_prompt
from src.validation.plan_validator import validate_plan

_PRODUCT_ID_PATTERN = re.compile(r"\bP\d+\b", re.IGNORECASE)
_LOOKUP_TOOLS = {"get_product", "get_product_price", "check_inventory"}


class Planner(Protocol):
	def plan(self, goal: str) -> Plan:
		"""Return a validated plan for the user goal."""
		...

	def create_plan(self, goal: str) -> Plan:
		"""Alias used by callers that prefer the explicit create-plan name."""
		...


class PlanningError(ValueError):
	"""Raised when a model response cannot be converted into a valid plan."""


class LLMPlanner:
	"""Convert an LLM response into a validated Plan instance."""

	def __init__(
		self,
		client: LLMClient,
		validator: Callable[[Plan], None] | None = None,
	) -> None:
		self._client = client
		self._validator = validator or validate_plan

	def plan(self, goal: str) -> Plan:
		return self.create_plan(goal)

	def create_plan(self, goal: str) -> Plan:
		if not goal or not goal.strip():
			raise PlanningError("goal cannot be blank")

		prompt = build_plan_prompt(goal)
		try:
			response = self._client.complete(prompt)
		except Exception as exc:  # pragma: no cover - exercised through tests
			raise PlanningError(f"Planner provider error: {exc}") from exc

		payload = self._coerce_response(response)
		plan = self._build_plan(goal, payload, self._product_ids_from_text(goal))
		try:
			self._validator(plan)
		except ValueError as exc:
			raise PlanningError(f"Generated plan is invalid: {exc}") from exc
		return plan

	def replan(
		self,
		*,
		goal: str,
		previous_plan: Plan,
		completed_steps: list[PlanStep],
		observation: object,
		reason: str,
	) -> Plan:
		"""Ask the model for replacement work, never for run-state metadata."""
		prompt = build_replan_prompt(
			goal=goal,
			previous_plan=json.dumps(previous_plan.to_dict(), ensure_ascii=False),
			completed_steps=json.dumps(
				[step.to_dict() for step in completed_steps], ensure_ascii=False
			),
			observation=json.dumps(observation, ensure_ascii=False, default=str),
			reason=reason,
		)
		try:
			response = self._client.complete(prompt)
		except Exception as exc:
			raise PlanningError(f"Planner provider error during replanning: {exc}") from exc
		known_product_ids = self._product_ids_from_text(goal)
		known_product_ids.update(self._product_ids_from_results(completed_steps))
		known_product_ids.update(self._product_ids_from_results([observation]))
		plan = self._build_plan(
			goal,
			self._coerce_response(response),
			known_product_ids,
		)
		try:
			self._validator(plan)
		except ValueError as exc:
			raise PlanningError(f"Generated replacement plan is invalid: {exc}") from exc
		return plan

	def _coerce_response(self, response: str | dict) -> dict[str, Any]:
		if isinstance(response, dict):
			return response
		if isinstance(response, str):
			try:
				parsed = json.loads(response)
			except json.JSONDecodeError as exc:
				raise PlanningError(f"Malformed model response: {exc.msg}") from exc
			if not isinstance(parsed, dict):
				raise PlanningError("Model response is not a dictionary payload")
			return parsed
		if hasattr(response, "choices"):
			choices = response.choices
			if not choices:
				raise PlanningError("Model response did not include any choices")
			message = choices[0].message
			content = getattr(message, "content", None)
			if isinstance(content, str):
				return self._coerce_response(content)
			raise PlanningError("Model response did not contain usable content")
		raise PlanningError("Unsupported model response format")

	def _build_plan(
		self,
		goal: str,
		payload: dict[str, Any],
		known_product_ids: set[str] | None = None,
	) -> Plan:
		if "plan" in payload and isinstance(payload["plan"], dict):
			payload = payload["plan"]

		if "steps" not in payload or not isinstance(payload["steps"], list):
			raise PlanningError("Model response must include a steps list")

		steps: list[PlanStep] = []
		for index, raw_step in enumerate(payload["steps"], start=1):
			if not isinstance(raw_step, dict):
				raise PlanningError(f"Step {index} is not an object")
			step_id = raw_step.get("step_id")
			objective = raw_step.get("objective")
			tool_name = raw_step.get("tool_name")
			tool_input = raw_step.get("tool_input", {})
			if not isinstance(step_id, str) or not step_id.strip():
				raise PlanningError(f"Step {index} is missing a valid step_id")
			if not isinstance(objective, str) or not objective.strip():
				raise PlanningError(f"Step {index} is missing a valid objective")
			if not isinstance(tool_name, str) or not tool_name.strip():
				raise PlanningError(f"Step {index} is missing a valid tool_name")
			if not isinstance(tool_input, dict):
				raise PlanningError(f"Step {step_id!r} tool_input must be a dictionary")
			if tool_name in _LOOKUP_TOOLS:
				product_id = tool_input.get("product_id")
				if (
					not isinstance(product_id, str)
					or product_id.upper() not in (known_product_ids or set())
				):
					raise PlanningError(
						f"Step {step_id!r} references product ID {product_id!r} "
						"that was not provided by the goal or prior observations"
					)
			steps.append(
				PlanStep(
					step_id=step_id,
					objective=objective,
					tool_name=tool_name,
					tool_input=cast(dict[str, JSONValue], dict(tool_input)),
				)
			)

		return Plan(goal=goal, steps=steps)

	@staticmethod
	def _product_ids_from_text(text: str) -> set[str]:
		return {product_id.upper() for product_id in _PRODUCT_ID_PATTERN.findall(text)}

	@classmethod
	def _product_ids_from_results(cls, values: object) -> set[str]:
		found: set[str] = set()
		if isinstance(values, dict):
			for key, value in values.items():
				if key in {"id", "product_id"} and isinstance(value, str):
					found.update(cls._product_ids_from_text(value))
				else:
					found.update(cls._product_ids_from_results(value))
		elif isinstance(values, (list, tuple)):
			for value in values:
				found.update(cls._product_ids_from_results(value))
		return found


class DeterministicPlanner:
	"""Create a simple valid plan without requiring an external model."""

	def __init__(self, *, category: str = "running_shoes") -> None:
		self.category = category

	def plan(self, goal: str) -> Plan:
		if not goal or not goal.strip():
			raise PlanningError("goal cannot be blank")

		lower_goal = goal.lower()
		category = self.category
		if "walking" in lower_goal:
			category = "walking_shoes"
		elif "running" in lower_goal:
			category = "running_shoes"

		max_price = None
		budget_matches = __import__("re").findall(r"(?:₹|rs|inr)?\s*([\d,]+)", goal, flags=__import__("re").IGNORECASE)
		if budget_matches:
			for value in reversed(budget_matches):
				number = int(value.replace(",", ""))
				if number > 0:
					max_price = number

		tool_input: dict[str, JSONValue] = {"category": category}
		if max_price is not None:
			tool_input["max_price_inr"] = max_price
		tool_input["in_stock_only"] = "in stock" in lower_goal or "available" in lower_goal

		return Plan(
			goal=goal,
			steps=[
				PlanStep(
					step_id="step-1",
					objective="Search for products that match the goal constraints",
					tool_name="search_products",
					tool_input=tool_input,
				)
			],
		)
