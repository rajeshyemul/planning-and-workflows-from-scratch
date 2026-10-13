from src.planner.contracts import Plan, PlanStatus, PlanStep, StepStatus
from src.workflow.runner import WorkflowRunner


def test_runner_stops_after_tool_failure_without_executing_later_steps():
	class FailingExecutor:
		def __init__(self) -> None:
			self.calls: list[str] = []

		def execute(self, step: PlanStep):
			self.calls.append(step.step_id)
			if step.step_id == "step-2":
				raise RuntimeError("catalog unavailable")
			return {"ok": True}

	executor = FailingExecutor()
	plan = Plan(
		goal="Find a shoe",
		steps=[
			PlanStep("step-1", "Search", "search_products", {"category": "running_shoes"}),
			PlanStep("step-2", "Check", "check_inventory", {"product_id": "P1001"}),
			PlanStep("step-3", "Search again", "search_products", {"category": "running_shoes"}),
		],
	)

	result = WorkflowRunner(executor).run(plan)

	assert result.status is PlanStatus.FAILED
	assert result.steps[0].status is StepStatus.COMPLETED
	assert result.steps[1].status is StepStatus.FAILED
	assert result.steps[2].status is StepStatus.PENDING
	assert executor.calls == ["step-1", "step-2"]


def test_runner_fails_when_replanning_repeats_the_same_pending_action():
	class RepeatingReplanner:
		def replan(self, *, goal, previous_plan, completed_steps, observation, reason):
			return Plan(
				goal=goal,
				steps=[PlanStep(
					f"replan-{previous_plan.replan_count + 1}",
					"Search an alternative",
					"search_products",
					{"category": "running_shoes", "in_stock_only": True},
				)],
			)

	class InvalidatingExecutor:
		def execute(self, step: PlanStep):
			if step.tool_name == "check_inventory":
				return {"product_id": "P1002", "in_stock": False}
			return {"eligible": False}

	plan = Plan(
		goal="Find an in-stock shoe",
		steps=[PlanStep("initial-check", "Check stock", "check_inventory", {"product_id": "P1002"})],
	)
	result = WorkflowRunner(
		InvalidatingExecutor(), replanner=RepeatingReplanner(), max_replans=4
	).run(plan)

	assert result.status is PlanStatus.FAILED
	assert "no progress" in result.last_error
