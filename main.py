import json
import argparse
import os
from dataclasses import dataclass
from typing import Any

from src.llm.client import OllamaClient
from src.planner.contracts import Plan, PlanStatus
from src.planner.planner import DeterministicPlanner, LLMPlanner
from src.tools.product_tools import ProductTools
from src.workflow.completion import find_best_candidate
from src.workflow.executor import ToolExecutor
from src.workflow.runner import WorkflowRunner


@dataclass
class WorkflowResult:
	status: str
	plan: Plan
	answer: dict[str, Any]
	observation: Any | None = None
	reason: str | None = None


def run_goal(
	goal: str,
	*,
	planner: Any | None = None,
	executor: Any | None = None,
	runner: WorkflowRunner | None = None,
) -> WorkflowResult:
	if not goal or not goal.strip():
		raise ValueError("goal cannot be blank")

	planner = planner or DeterministicPlanner()
	plan = planner.plan(goal)
	if executor is None:
		executor = ToolExecutor(ProductTools())
	if runner is None:
		replanner = planner if callable(getattr(planner, "replan", None)) else None
		runner = WorkflowRunner(executor, replanner=replanner)

	final_plan = runner.run(plan)
	observation = final_plan.last_observation
	if final_plan.status is PlanStatus.COMPLETED:
		observation = next(
			(step.result for step in reversed(final_plan.steps) if step.result is not None),
			None,
		)
	elif observation is None and final_plan.steps:
		observation = final_plan.steps[-1].result
	if final_plan.status is PlanStatus.NEEDS_REPLAN:
		return WorkflowResult(
			status="needs_replan",
			plan=final_plan,
			answer={"message": "The workflow needs replanning based on the latest observation."},
			observation=final_plan.last_observation,
			reason=final_plan.last_error,
		)
	if final_plan.status is PlanStatus.FAILED:
		return WorkflowResult(
			status="failed",
			plan=final_plan,
			answer={"message": final_plan.last_error or "The workflow failed."},
			observation=final_plan.last_observation,
			reason=final_plan.last_error,
		)

	candidate = find_best_candidate(final_plan)
	if candidate is None:
		return WorkflowResult(
			status="no_match",
			plan=final_plan,
			answer={"message": "No eligible product matches the request."},
			observation=observation,
			reason="no_match",
		)

	response = {
		"product_id": candidate["id"],
		"name": candidate["name"],
		"category": candidate["category"],
		"price_inr": candidate["price_inr"],
		"stock_quantity": candidate["stock_quantity"],
		"message": "Found an eligible product matching the request.",
	}
	return WorkflowResult(
		status="completed",
		plan=final_plan,
		answer=response,
		observation=observation,
		reason=None,
	)


def main() -> None:
	parser = argparse.ArgumentParser(description="Run a structured product-search workflow.")
	parser.add_argument("goal", nargs="?", default="Find an in-stock running shoe under ₹5,000")
	parser.add_argument(
		"--planner",
		choices=("deterministic", "ollama"),
		default=os.getenv("PLANNER_BACKEND", "deterministic"),
	)
	parser.add_argument("--model", default=None, help="Ollama model name (defaults to OLLAMA_MODEL or llama3.2:3b)")
	args = parser.parse_args()
	planner = (
		LLMPlanner(OllamaClient(model=args.model))
		if args.planner == "ollama"
		else DeterministicPlanner()
	)
	try:
		result = run_goal(args.goal, planner=planner)
	except (ValueError, RuntimeError) as error:
		parser.exit(2, f"Error: {error}\n")
	print(json.dumps(result.answer, ensure_ascii=False))
	return None


if __name__ == "__main__":
	main()
