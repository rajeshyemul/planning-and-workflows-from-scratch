import json
from typing import Protocol

from src.planner.contracts import JSONValue, Plan, PlanStatus, PlanStep, StepStatus
from src.validation.plan_validator import validate_plan


class StepExecutor(Protocol):
	def execute(self, step: PlanStep) -> JSONValue:
		"""Execute one validated step and return its observation."""


class Replanner(Protocol):
	def replan(
		self,
		*,
		goal: str,
		previous_plan: Plan,
		completed_steps: list[PlanStep],
		observation: object,
		reason: str,
	) -> Plan:
		"""Propose the remaining work after a changed observation."""


class DefaultReplanner:
	"""Deterministic educational replanner for the product-search example."""

	def replan(
		self,
		*,
		goal: str,
		previous_plan: Plan,
		completed_steps: list[PlanStep],
		observation: object,
		reason: str,
	) -> Plan:
		search_constraints: dict[str, JSONValue] = {
			"category": "running_shoes",
			"in_stock_only": True,
		}
		for step in previous_plan.steps:
			if step.tool_name == "search_products":
				search_constraints = dict(step.tool_input)
				search_constraints["in_stock_only"] = True
				break

		used_ids = {step.step_id for step in previous_plan.steps}
		step_id = f"replan-{previous_plan.replan_count + 1}"
		while step_id in used_ids:
			step_id = f"{step_id}-next"
		search_step = PlanStep(
			step_id=step_id,
			objective=f"Search for an in-stock alternative after {reason}",
			tool_name="search_products",
			tool_input=search_constraints,
		)
		return Plan(goal=goal, steps=[*completed_steps, search_step])


class WorkflowRunner:
	"""Execute plans sequentially, including validated and bounded replans."""

	def __init__(
		self,
		executor: StepExecutor,
		replanner: Replanner | None = None,
		max_replans: int = 3,
	) -> None:
		if max_replans < 0:
			raise ValueError("max_replans cannot be negative")
		self._executor = executor
		self._replanner = replanner or DefaultReplanner()
		self._max_replans = max_replans

	def _should_replan(self, observation: object) -> bool:
		if not isinstance(observation, dict):
			return False
		if observation.get("in_stock") is False or observation.get("out_of_stock") is True:
			return True
		status = observation.get("status")
		if isinstance(status, str) and status.lower() in {"out_of_stock", "failed", "needs_replan"}:
			return True
		return observation.get("eligible") is False

	def _replan_reason(self, observation: object) -> str:
		if isinstance(observation, dict):
			if observation.get("in_stock") is False or observation.get("out_of_stock") is True:
				return "out_of_stock"
			status = observation.get("status")
			if isinstance(status, str):
				return status.lower()
		return "observation_invalidated_plan"

	@staticmethod
	def _pending_signature(plan: Plan) -> str:
		actions = [
			{"tool_name": step.tool_name, "tool_input": step.tool_input}
			for step in plan.steps
			if step.status is StepStatus.PENDING
		]
		return json.dumps(actions, sort_keys=True, separators=(",", ":"))

	@staticmethod
	def _fail(plan: Plan, message: str) -> Plan:
		if plan.status in {PlanStatus.RUNNING, PlanStatus.NEEDS_REPLAN}:
			plan.transition_to(PlanStatus.FAILED)
		plan.last_error = message
		return plan

	def _replacement_plan(
		self,
		plan: Plan,
		observation: object,
		seen_signatures: set[str],
	) -> Plan:
		reason = self._replan_reason(observation)
		next_count = plan.replan_count + 1
		plan.last_observation = observation  # type: ignore[assignment]
		plan.last_error = reason
		plan.transition_to(PlanStatus.NEEDS_REPLAN)
		if next_count > self._max_replans:
			return self._fail(plan, f"replan limit reached: {self._max_replans}")

		completed_steps = [step for step in plan.steps if step.status is StepStatus.COMPLETED]
		try:
			replacement = self._replanner.replan(
				goal=plan.goal,
				previous_plan=plan,
				completed_steps=completed_steps,
				observation=observation,
				reason=reason,
			)
		except Exception as exc:
			self._fail(plan, f"replacement plan failed: {exc}")
			raise ValueError(f"replacement plan failed: {exc}") from exc

		if not isinstance(replacement, Plan):
			self._fail(plan, "replacement plan must be a Plan instance")
			raise ValueError("replacement plan must be a Plan instance")
		if replacement.goal != plan.goal:
			self._fail(plan, "replacement plan changed the original goal")
			raise ValueError("replacement plan changed the original goal")
		if replacement.status is not PlanStatus.PENDING:
			self._fail(plan, "replacement plan must be pending")
			raise ValueError("replacement plan must be pending")
		try:
			validate_plan(replacement)
		except Exception as exc:
			self._fail(plan, f"replacement plan is invalid: {exc}")
			raise ValueError(f"replacement plan is invalid: {exc}") from exc

		completed_by_id = {step.step_id: step for step in completed_steps}
		merged_steps = list(completed_steps)
		for step in replacement.steps:
			if step.step_id in completed_by_id:
				completed = completed_by_id[step.step_id]
				if (
					step.status is not StepStatus.COMPLETED
					or step.tool_name != completed.tool_name
					or step.tool_input != completed.tool_input
				):
					self._fail(plan, "replacement plan conflicts with preserved completed work")
					raise ValueError("replacement plan conflicts with preserved completed work")
				continue
			if step.status is not StepStatus.PENDING:
				self._fail(plan, "replacement steps must be pending")
				raise ValueError("replacement steps must be pending or preserved completed steps")
			merged_steps.append(step)
		if len(merged_steps) > len(replacement.steps):
			replacement.steps = merged_steps
		elif not any(step.status is StepStatus.PENDING for step in merged_steps):
			self._fail(plan, "replacement plan contains no pending work")
			raise ValueError("replacement plan contains no pending work")

		replacement.replan_count = next_count
		replacement.last_observation = observation  # type: ignore[assignment]
		replacement.last_error = reason
		replacement.current_step_id = next(
			(step.step_id for step in replacement.steps if step.status is StepStatus.PENDING),
			None,
		)
		signature = self._pending_signature(replacement)
		if not signature or signature in seen_signatures:
			return self._fail(plan, "replanning made no progress: repeated pending actions")
		seen_signatures.add(signature)
		return replacement

	def run(self, plan: Plan) -> Plan:
		"""Execute a plan and continue through valid replacements until terminal."""
		validate_plan(plan)
		if plan.status is not PlanStatus.PENDING:
			raise ValueError("Only a pending plan can be executed")
		if any(step.status is not StepStatus.PENDING for step in plan.steps):
			raise ValueError("All steps must be pending before plan execution")

		seen_signatures = {self._pending_signature(plan)}
		current_plan = plan
		while True:
			if current_plan.status in {PlanStatus.PENDING, PlanStatus.NEEDS_REPLAN}:
				current_plan.transition_to(PlanStatus.RUNNING)

			replacement: Plan | None = None
			for step in current_plan.steps:
				if step.status is StepStatus.COMPLETED:
					continue
				current_plan.current_step_id = step.step_id
				step.transition_to(StepStatus.RUNNING)
				try:
					step.result = self._executor.execute(step)
				except Exception as error:
					step.error = f"{type(error).__name__}: {error}"
					step.transition_to(StepStatus.FAILED)
					return self._fail(current_plan, step.error)
				step.transition_to(StepStatus.COMPLETED)
				if self._should_replan(step.result):
					replacement = self._replacement_plan(
						current_plan, step.result, seen_signatures
					)
					if replacement.status is PlanStatus.FAILED:
						return replacement
					break

			if replacement is None:
				current_plan.transition_to(PlanStatus.COMPLETED)
				current_plan.current_step_id = None
				return current_plan
			current_plan = replacement
