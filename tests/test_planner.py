import pytest
from jsonschema import Draft202012Validator

from src.llm.client import OLLAMA_PLAN_SCHEMA, OllamaClient
from src.planner.contracts import Plan, PlanStatus
from src.planner.planner import LLMPlanner, PlanningError


class FakeLLMClient:
	def __init__(self, payload: str | dict | None) -> None:
		self.payload = payload

	def complete(self, prompt: str) -> str | dict:
		return self.payload if self.payload is not None else ""


def test_llm_planner_builds_valid_plan_from_structured_response():
	client = FakeLLMClient(
		{
			"goal": "Find an in-stock running shoe under ₹5,000",
			"steps": [
				{
					"step_id": "step-1",
					"objective": "Search for running shoes within budget",
					"tool_name": "search_products",
					"tool_input": {
						"category": "running_shoes",
						"max_price_inr": 5000,
						"in_stock_only": True,
					},
				}
			],
		}
	)
	planner = LLMPlanner(client)

	plan = planner.plan("Find an in-stock running shoe under ₹5,000")

	assert isinstance(plan, Plan)
	assert plan.goal == "Find an in-stock running shoe under ₹5,000"
	assert plan.status is PlanStatus.PENDING
	assert len(plan.steps) == 1
	assert plan.steps[0].tool_name == "search_products"


def test_llm_planner_keeps_application_goal_authoritative():
	planner = LLMPlanner(FakeLLMClient({
		"goal": "a different goal",
		"replan_count": 99,
		"steps": [{
			"step_id": "step-1",
			"objective": "Search shoes",
			"tool_name": "search_products",
			"tool_input": {"category": "running_shoes"},
		}],
	}))

	plan = planner.plan("Find a running shoe")

	assert plan.goal == "Find a running shoe"
	assert plan.replan_count == 0


def test_ollama_client_posts_non_streaming_json_request(monkeypatch):
	import io
	import json
	import urllib.request

	captured: dict[str, object] = {}

	class Response:
		def __enter__(self):
			return self

		def __exit__(self, *args):
			return None

		def read(self) -> bytes:
			return b'{"response":"{\\"steps\\": []}"}'

	def fake_urlopen(request, timeout):
		captured["url"] = request.full_url
		captured["body"] = json.loads(request.data.decode("utf-8"))
		captured["timeout"] = timeout
		return Response()

	monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
	client = OllamaClient(model="llama3.2:3b", base_url="http://localhost:11434/")

	response = client.complete("make a plan")

	assert response == '{"steps": []}'
	assert captured["url"] == "http://localhost:11434/api/generate"
	assert captured["body"] == {
		"model": "llama3.2:3b",
		"prompt": "make a plan",
		"stream": False,
		"format": OLLAMA_PLAN_SCHEMA,
		"options": {"temperature": 0},
	}


def test_ollama_schema_accepts_valid_plan_and_rejects_invalid_tool_input():
	Draft202012Validator.check_schema(OLLAMA_PLAN_SCHEMA)
	validator = Draft202012Validator(OLLAMA_PLAN_SCHEMA)
	valid_payload = {
		"steps": [{
			"step_id": "step-1",
			"objective": "Find in-stock running shoes under budget",
			"tool_name": "search_products",
			"tool_input": {
				"category": "running_shoes",
				"max_price_inr": 5000,
				"in_stock_only": True,
			},
		}],
	}
	invalid_payload = {
		"steps": [{
			"step_id": "step-1",
			"objective": "Search running shoes",
			"tool_name": "search_products",
			"tool_input": {"category": "running shoes", "in_stock_only": True},
		}],
	}

	assert validator.is_valid(valid_payload)
	assert not validator.is_valid(invalid_payload)


def test_llm_planner_can_generate_a_valid_replacement_plan():
	from src.planner.contracts import PlanStep

	client = FakeLLMClient({
		"steps": [{
			"step_id": "replacement-search",
			"objective": "Search for another in-stock shoe",
			"tool_name": "search_products",
			"tool_input": {"category": "running_shoes", "in_stock_only": True},
		}],
	})
	planner = LLMPlanner(client)
	previous = Plan(
		goal="Find a running shoe",
		steps=[PlanStep("check", "Check stock", "check_inventory", {"product_id": "P1002"})],
	)

	replacement = planner.replan(
		goal=previous.goal,
		previous_plan=previous,
		completed_steps=[],
		observation={"product_id": "P1002", "in_stock": False},
		reason="out_of_stock",
	)

	assert replacement.goal == previous.goal
	assert replacement.replan_count == 0
	assert replacement.steps[0].step_id == "replacement-search"


@pytest.mark.parametrize(
	"payload",
	[
		"not json",
		"{invalid json",
		{"goal": "Find a shoe"},
		{"steps": [{"step_id": "step-1", "objective": "x", "tool_name": "bad_tool"}]},
	],
)
def test_llm_planner_rejects_malformed_or_invalid_model_output(payload):
	planner = LLMPlanner(FakeLLMClient(payload))

	with pytest.raises((PlanningError, ValueError)):
		planner.plan("Find a shoe")


def test_llm_planner_surfaces_provider_errors():
	class FailingLLMClient:
		def complete(self, prompt: str) -> str:
			raise RuntimeError("provider error")

	planner = LLMPlanner(FailingLLMClient())

	with pytest.raises(PlanningError, match="provider error"):
		planner.plan("Find a shoe")


def test_llm_planner_rejects_fabricated_product_ids():
	planner = LLMPlanner(FakeLLMClient({
		"steps": [{
			"step_id": "step-1",
			"objective": "Look up a product",
			"tool_name": "get_product",
			"tool_input": {"product_id": "P9999"},
		}],
	}))

	with pytest.raises(PlanningError, match="not provided by the goal or prior observations"):
		planner.plan("Find a running shoe")


def test_llm_planner_allows_product_ids_explicitly_given_in_goal():
	planner = LLMPlanner(FakeLLMClient({
		"steps": [{
			"step_id": "step-1",
			"objective": "Look up the requested product",
			"tool_name": "get_product",
			"tool_input": {"product_id": "P1001"},
		}],
	}))

	plan = planner.plan("Tell me about product P1001")

	assert plan.steps[0].tool_input["product_id"] == "P1001"
