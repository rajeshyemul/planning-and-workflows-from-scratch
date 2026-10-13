import json

import pytest

from src.planner.contracts import Plan, PlanStatus, PlanStep, StepStatus


def make_step(step_id: str, tool_name: str = "search_products") -> PlanStep:
	return PlanStep(
		step_id=step_id,
		objective=f"Run {tool_name}",
		tool_name=tool_name,
		tool_input={"category": "running_shoes"},
	)


def test_plan_and_step_have_pending_defaults_and_zero_replans():
	first_step = make_step("step-1")
	plan = Plan(goal="Find an in-stock shoe under ₹5,000", steps=[first_step])

	assert plan.status is PlanStatus.PENDING
	assert plan.replan_count == 0
	assert first_step.status is StepStatus.PENDING


def test_plan_preserves_step_order_and_each_plan_has_its_own_steps_list():
	first = make_step("step-1", "search_products")
	second = make_step("step-2", "check_inventory")
	first_plan = Plan(goal="Find a shoe", steps=[first, second])
	second_plan = Plan(goal="Find another shoe", steps=[])

	assert first_plan.steps == [first, second]
	assert first_plan.steps[0].step_id == "step-1"
	assert first_plan.steps[1].step_id == "step-2"
	assert first_plan.steps is not second_plan.steps


def test_step_can_hold_json_compatible_input_result_and_error_fields():
	step = make_step("step-1")
	step.result = {"products": [{"id": "P1001", "in_stock": True}]}
	step.error = None

	serialized = json.dumps(step.to_dict())

	assert json.loads(serialized)["result"] == {
		"products": [{"id": "P1001", "in_stock": True}]
	}


def test_plan_serializes_with_status_values_and_ordered_steps():
	plan = Plan(goal="Find a shoe", steps=[make_step("step-1"), make_step("step-2")])

	serialized = json.dumps(plan.to_dict())
	restored = json.loads(serialized)

	assert restored["status"] == "pending"
	assert [step["step_id"] for step in restored["steps"]] == ["step-1", "step-2"]


def test_plan_rejects_negative_replan_count():
	with pytest.raises(ValueError, match="replan_count cannot be negative"):
		Plan(goal="Find a shoe", steps=[], replan_count=-1)


def test_step_allows_only_declared_status_transitions():
	step = make_step("step-1")

	step.transition_to(StepStatus.RUNNING)
	step.transition_to(StepStatus.COMPLETED)

	assert step.status is StepStatus.COMPLETED
	with pytest.raises(ValueError, match="Invalid step transition"):
		step.transition_to(StepStatus.PENDING)


def test_plan_allows_replanning_transition_and_resume():
	plan = Plan(goal="Find a shoe", steps=[make_step("step-1")])

	plan.transition_to(PlanStatus.RUNNING)
	plan.transition_to(PlanStatus.NEEDS_REPLAN)
	plan.replan_count += 1
	plan.transition_to(PlanStatus.RUNNING)

	assert plan.status is PlanStatus.RUNNING
	assert plan.replan_count == 1


def test_transition_rejects_status_from_the_wrong_enum():
	step = make_step("step-1")

	with pytest.raises(TypeError, match="matching status type"):
		step.transition_to(PlanStatus.RUNNING)  # type: ignore[arg-type]


def test_valid_search_plan_passes_validation():
	from src.validation.plan_validator import validate_plan

	plan = Plan(
		goal="Find an in-stock running shoe under ₹5,000",
		steps=[
			PlanStep(
				step_id="step-1",
				objective="Search for running shoes under budget",
				tool_name="search_products",
				tool_input={
					"category": "running_shoes",
					"max_price_inr": 5000,
					"in_stock_only": True,
				},
			)
		],
	)

	assert validate_plan(plan) is None


@pytest.mark.parametrize(
	("goal", "steps", "message"),
	[
		("   ", [make_step("step-1")], "goal cannot be blank"),
		("Find a shoe", [], "at least one step"),
	],
)
def test_rejects_blank_goal_or_empty_plan(goal, steps, message):
	from src.validation.plan_validator import PlanValidationError, validate_plan

	with pytest.raises(PlanValidationError, match=message):
		validate_plan(Plan(goal=goal, steps=steps))


def test_rejects_duplicate_step_ids():
	from src.validation.plan_validator import PlanValidationError, validate_plan

	plan = Plan(goal="Find a shoe", steps=[make_step("duplicate"), make_step("duplicate")])

	with pytest.raises(PlanValidationError, match="duplicate step ID"):
		validate_plan(plan)


def test_rejects_unsupported_tools():
	from src.validation.plan_validator import PlanValidationError, validate_plan

	step = make_step("step-1", "delete_database")
	plan = Plan(goal="Find a shoe", steps=[step])

	with pytest.raises(PlanValidationError, match="unsupported tool"):
		validate_plan(plan)


@pytest.mark.parametrize(
	"tool_input",
	[
		{},
		{"category": "running_shoes", "unexpected": "value"},
		{"category": "running_shoes", "max_price_inr": True},
		{"category": "running_shoes", "max_price_inr": -1},
		{"category": "running shoes"},
		{"category": "   "},
	],
)
def test_rejects_invalid_tool_inputs(tool_input):
	from src.validation.plan_validator import PlanValidationError, validate_plan

	step = make_step("step-1")
	step.tool_input = tool_input
	plan = Plan(goal="Find a shoe", steps=[step])

	with pytest.raises(PlanValidationError):
		validate_plan(plan)


def test_rejects_plan_that_exceeds_step_limit():
	from src.validation.plan_validator import MAX_PLAN_STEPS, PlanValidationError, validate_plan

	plan = Plan(
		goal="Find a shoe",
		steps=[make_step(f"step-{index}") for index in range(MAX_PLAN_STEPS + 1)],
	)

	with pytest.raises(PlanValidationError, match="more than"):
		validate_plan(plan)
