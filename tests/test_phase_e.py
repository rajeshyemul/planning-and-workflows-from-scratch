import pytest

from main import run_goal
from src.planner.contracts import Plan, PlanStatus, PlanStep


def test_run_goal_returns_successful_result_for_in_stock_budget_match():
	result = run_goal("Find an in-stock running shoe under ₹5,000")

	assert result.status == "completed"
	assert result.answer["product_id"] == "P1001"
	assert result.answer["price_inr"] == 4299


def test_run_goal_returns_no_match_when_no_product_meets_constraints():
	result = run_goal("Find an in-stock running shoe under ₹2,000")

	assert result.status == "no_match"
	assert "No eligible product" in result.answer["message"]


def test_default_planner_creates_valid_search_plan_for_deterministic_mode():
	plan = run_goal("Find a running shoe under ₹5,000 in stock").plan

	assert isinstance(plan, Plan)
	assert plan.status in {PlanStatus.PENDING, PlanStatus.COMPLETED}
	assert plan.steps[0].tool_name == "search_products"


def test_run_goal_replans_after_unavailable_candidate_and_returns_alternative():
	class InventoryFirstPlanner:
		def plan(self, goal: str) -> Plan:
			return Plan(
				goal=goal,
				steps=[
					PlanStep(
						step_id="search-candidates",
						objective="Search within the structured category and budget constraints",
						tool_name="search_products",
						tool_input={
							"category": "running_shoes",
							"max_price_inr": 5000,
							"in_stock_only": False,
						},
					),
					PlanStep(
						step_id="check-first-candidate",
						objective="Check the first candidate's availability",
						tool_name="check_inventory",
						tool_input={"product_id": "P1002"},
					)
				],
			)

	result = run_goal("Find an in-stock running shoe under ₹5,000", planner=InventoryFirstPlanner())

	assert result.status == "completed"
	assert result.plan.replan_count == 1
	assert result.answer["product_id"] == "P1001"
	assert result.plan.steps[1].result["in_stock"] is False
	assert result.plan.steps[2].tool_input == {
		"category": "running_shoes",
		"max_price_inr": 5000,
		"in_stock_only": True,
	}
	assert result.plan.steps[2].result[0]["id"] == "P1001"
