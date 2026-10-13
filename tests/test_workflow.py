import pytest

from src.planner.contracts import JSONValue, Plan, PlanStatus, PlanStep, StepStatus
from src.tools.product_tools import ProductNotFoundError, ProductTools
from src.workflow.executor import ToolExecutor
from src.workflow.runner import WorkflowRunner


class FakeExecutor:
	def __init__(self, fail_on: str | None = None) -> None:
		self.calls: list[str] = []
		self.fail_on = fail_on

	def execute(self, step: PlanStep) -> JSONValue:
		self.calls.append(step.step_id)
		if step.step_id == self.fail_on:
			raise RuntimeError("simulated tool failure")
		return {"step_id": step.step_id, "ok": True}


def make_step(step_id: str, tool_name: str = "search_products", **tool_input) -> PlanStep:
	if not tool_input:
		tool_input = {"category": "running_shoes"}
	return PlanStep(
		step_id=step_id,
		objective=f"Run {tool_name}",
		tool_name=tool_name,
		tool_input=tool_input,
	)


def test_product_tools_search_fixture_by_category_budget_and_stock():
	tools = ProductTools()

	products = tools.search_products(
		category="running_shoes", max_price_inr=5000, in_stock_only=True
	)

	assert [product["id"] for product in products] == ["P1001"]


def test_product_tools_lookup_price_and_inventory():
	tools = ProductTools()

	assert tools.get_product("P1001")["name"] == "PaceRun Flex"
	assert tools.get_product_price("P1001")["price_inr"] == 4299
	assert tools.check_inventory("P1002")["in_stock"] is False


def test_product_tools_raise_for_unknown_product():
	with pytest.raises(ProductNotFoundError, match="P9999"):
		ProductTools().get_product("P9999")


def test_executor_dispatches_only_registered_tools():
	step = make_step(
		"step-1",
		"search_products",
		category="running_shoes",
		max_price_inr=5000,
		in_stock_only=True,
	)

	result = ToolExecutor().execute(step)

	assert [product["id"] for product in result] == ["P1001"]


def test_executor_rejects_unknown_tool():
	step = make_step("step-1", "unregistered_tool", category="running_shoes")

	with pytest.raises(ValueError, match="Unsupported tool"):
		ToolExecutor().execute(step)


def test_runner_completes_plan_and_stores_each_observation():
	executor = FakeExecutor()
	plan = Plan(goal="Find a shoe", steps=[make_step("step-1"), make_step("step-2")])

	result = WorkflowRunner(executor).run(plan)

	assert result.status is PlanStatus.COMPLETED
	assert [step.status for step in result.steps] == [StepStatus.COMPLETED, StepStatus.COMPLETED]
	assert result.steps[0].result == {"step_id": "step-1", "ok": True}
	assert executor.calls == ["step-1", "step-2"]


def test_runner_marks_failure_and_stops_before_later_steps():
	executor = FakeExecutor(fail_on="step-2")
	plan = Plan(
		goal="Find a shoe",
		steps=[make_step("step-1"), make_step("step-2"), make_step("step-3")],
	)

	result = WorkflowRunner(executor).run(plan)

	assert result.status is PlanStatus.FAILED
	assert result.steps[0].status is StepStatus.COMPLETED
	assert result.steps[1].status is StepStatus.FAILED
	assert "simulated tool failure" in result.steps[1].error
	assert result.steps[2].status is StepStatus.PENDING
	assert executor.calls == ["step-1", "step-2"]


def test_runner_rejects_invalid_plan_before_calling_executor():
	executor = FakeExecutor()
	plan = Plan(goal=" ", steps=[make_step("step-1")])

	with pytest.raises(ValueError, match="goal cannot be blank"):
		WorkflowRunner(executor).run(plan)

	assert plan.status is PlanStatus.PENDING
	assert executor.calls == []
