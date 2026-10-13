import pytest

from src.planner.contracts import Plan, PlanStatus, PlanStep, StepStatus
from src.workflow.runner import WorkflowRunner


class FakeReplanner:
	def __init__(self, plan: Plan) -> None:
		self.plan = plan
		self.calls: list[dict] = []

	def replan(self, *, goal: str, previous_plan: Plan, completed_steps: list[PlanStep], observation: object, reason: str) -> Plan:
		self.calls.append({
			"goal": goal,
			"previous_plan": previous_plan.goal,
			"completed_count": len(completed_steps),
			"observation": observation,
			"reason": reason,
		})
		return self.plan


class FakeExecutor:
	def __init__(self, payload: object) -> None:
		self.payload = payload

	def execute(self, step: PlanStep) -> object:
		return self.payload


def test_replanner_preserves_completed_steps_when_building_a_replacement_plan():
	from src.validation.plan_validator import validate_plan
	from src.workflow.runner import DefaultReplanner

	prior_plan = Plan(
		goal="Find a valid shoe",
		steps=[
			PlanStep("step-1", "Search for options", "search_products", {"category": "running_shoes"}),
			PlanStep("step-2", "Check remaining options", "check_inventory", {"product_id": "P1002"}),
		],
	)
	prior_plan.steps[0].transition_to(StepStatus.RUNNING)
	prior_plan.steps[0].transition_to(StepStatus.COMPLETED)
	prior_plan.steps[0].result = {"products": [{"id": "P1001"}]}

	replanner = DefaultReplanner()
	replacement = replanner.replan(
		goal=prior_plan.goal,
		previous_plan=prior_plan,
		completed_steps=[prior_plan.steps[0]],
		observation={"product_id": "P1002", "in_stock": False},
		reason="out_of_stock",
	)

	validate_plan(replacement)
	assert replacement.goal == prior_plan.goal
	assert replacement.steps[0].step_id == "step-1"
	assert replacement.steps[0].status is StepStatus.COMPLETED
	assert replacement.steps[1].step_id == "replan-1"
	assert replacement.steps[1].tool_input["in_stock_only"] is True
	assert replacement.replan_count == 0


def test_runner_replans_when_observation_indicates_out_of_stock():
	replacement_plan = Plan(
		goal="Find a valid shoe",
		steps=[
			PlanStep("replan-1", "Search again", "search_products", {"category": "running_shoes", "in_stock_only": True})
		],
	)
	replanner = FakeReplanner(replacement_plan)

	class ReplanningExecutor:
		def __init__(self) -> None:
			self.calls: list[str] = []

		def execute(self, step: PlanStep) -> object:
			self.calls.append(step.tool_name)
			if step.tool_name == "check_inventory":
				return {"product_id": "P1002", "in_stock": False}
			return [{"id": "P1001", "category": "running_shoes", "price_inr": 4299, "stock_quantity": 12}]

	executor = ReplanningExecutor()
	runner = WorkflowRunner(executor, replanner=replanner, max_replans=3)
	plan = Plan(
		goal="Find a valid shoe",
		steps=[PlanStep("step-1", "Check inventory", "check_inventory", {"product_id": "P1002"})],
	)

	result = runner.run(plan)

	assert result.status is PlanStatus.COMPLETED
	assert result.replan_count == 1
	assert result.last_observation == {"product_id": "P1002", "in_stock": False}
	assert replanner.calls and replanner.calls[0]["reason"] == "out_of_stock"
	assert executor.calls == ["check_inventory", "search_products"]
	assert result.steps[-1].result[0]["id"] == "P1001"


def test_runner_preserves_multiple_completed_steps_during_replanning():
	class ReplannerReturningOnlyNewWork:
		def replan(self, *, goal, previous_plan, completed_steps, observation, reason):
			assert [step.step_id for step in completed_steps] == ["search", "price", "inventory"]
			return Plan(
				goal=goal,
				steps=[PlanStep(
					"alternative-search",
					"Search for an in-stock alternative",
					"search_products",
					{"category": "running_shoes", "max_price_inr": 5000, "in_stock_only": True},
				)],
			)

	class MultiStepExecutor:
		def __init__(self) -> None:
			self.calls: list[str] = []

		def execute(self, step: PlanStep):
			self.calls.append(step.step_id)
			if step.step_id == "inventory":
				return {"product_id": "P1002", "in_stock": False}
			if step.step_id == "alternative-search":
				return [{"id": "P1001", "category": "running_shoes", "price_inr": 4299, "stock_quantity": 12}]
			if step.step_id == "search":
				return [{"id": "P1001", "category": "running_shoes", "price_inr": 4299, "stock_quantity": 12}]
			return {"product_id": "P1002", "price_inr": 4799}

	plan = Plan(
		goal="Find an in-stock running shoe under ₹5,000",
		steps=[
			PlanStep("search", "Search candidate shoes", "search_products", {
				"category": "running_shoes", "max_price_inr": 5000, "in_stock_only": False,
			}),
			PlanStep("price", "Check candidate price", "get_product_price", {"product_id": "P1002"}),
			PlanStep("inventory", "Check candidate stock", "check_inventory", {"product_id": "P1002"}),
		],
	)
	executor = MultiStepExecutor()

	result = WorkflowRunner(executor, replanner=ReplannerReturningOnlyNewWork()).run(plan)

	assert result.status is PlanStatus.COMPLETED
	assert result.replan_count == 1
	assert [step.step_id for step in result.steps] == ["search", "price", "inventory", "alternative-search"]
	assert [step.status for step in result.steps[:3]] == [StepStatus.COMPLETED] * 3
	assert result.steps[0].result[0]["id"] == "P1001"
	assert result.steps[1].result["price_inr"] == 4799
	assert result.steps[2].result["in_stock"] is False
	assert executor.calls == ["search", "price", "inventory", "alternative-search"]


def test_runner_rejects_invalid_replacement_plan_and_stops_replanning():
	class InvalidReplanner:
		def replan(self, *, goal: str, previous_plan: Plan, completed_steps: list[PlanStep], observation: object, reason: str) -> Plan:
			return Plan(goal="Find a valid shoe", steps=[])

	runner = WorkflowRunner(
		FakeExecutor({"in_stock": False}),
		replanner=InvalidReplanner(),
		max_replans=2,
	)
	plan = Plan(goal="Find a valid shoe", steps=[PlanStep("step-1", "Check inventory", "check_inventory", {"product_id": "P1002"})])

	with pytest.raises(ValueError, match="replacement plan"):
		runner.run(plan)


def test_runner_stops_after_replan_limit_is_reached():
	class LoopingReplanner:
		def replan(self, *, goal: str, previous_plan: Plan, completed_steps: list[PlanStep], observation: object, reason: str) -> Plan:
			return Plan(
				goal=goal,
				steps=[PlanStep("replan-1", "Check inventory", "check_inventory", {"product_id": "P1001"})],
			)

	runner = WorkflowRunner(FakeExecutor({"in_stock": False}), replanner=LoopingReplanner(), max_replans=1)
	plan = Plan(goal="Find a valid shoe", steps=[PlanStep("step-1", "Check inventory", "check_inventory", {"product_id": "P1002"})])

	result = runner.run(plan)

	assert result.status is PlanStatus.FAILED
	assert "replan limit" in result.last_error.lower()
