import json
import os
from typing import Protocol
from urllib.error import URLError
from urllib.request import Request
import urllib.request


OLLAMA_PLAN_SCHEMA: dict[str, object] = {
	"type": "object",
	"additionalProperties": False,
	"required": ["steps"],
	"properties": {
		"steps": {
			"type": "array",
			"minItems": 1,
			"maxItems": 10,
			"items": {
				"anyOf": [
					{
						"$ref": "#/$defs/search_products_step",
					},
					{
						"$ref": "#/$defs/product_lookup_step",
					},
				],
			},
		},
	},
	"$defs": {
		"step_base": {
			"type": "object",
			"required": ["step_id", "objective", "tool_name", "tool_input"],
			"properties": {
				"step_id": {"type": "string", "minLength": 1},
				"objective": {"type": "string", "minLength": 1},
				"tool_name": {"type": "string"},
			},
		},
		"search_products_step": {
			"allOf": [
				{"$ref": "#/$defs/step_base"},
				{
					"type": "object",
					"properties": {
						"tool_name": {"const": "search_products"},
						"tool_input": {
							"type": "object",
							"required": ["category", "in_stock_only"],
							"additionalProperties": False,
							"properties": {
								"category": {"type": "string", "enum": ["running_shoes", "walking_shoes"]},
								"max_price_inr": {"type": "integer", "minimum": 0},
								"in_stock_only": {"type": "boolean"},
							},
						},
					},
				},
			],
			"unevaluatedProperties": False,
		},
		"product_lookup_step": {
			"allOf": [
				{"$ref": "#/$defs/step_base"},
				{
					"type": "object",
					"properties": {
						"tool_name": {
							"enum": ["get_product", "get_product_price", "check_inventory"]
						},
						"tool_input": {
							"type": "object",
							"required": ["product_id"],
							"additionalProperties": False,
							"properties": {"product_id": {"type": "string", "minLength": 1}},
						},
					},
				},
			],
			"unevaluatedProperties": False,
		},
	},
}


class LLMClient(Protocol):
	"""Minimal synchronous client interface used by planners."""

	def complete(self, prompt: str) -> str | dict:
		"""Return a model response for the given prompt."""
		...


class StaticLLMClient:
	"""Simple injected client that returns the same payload for every prompt."""

	def __init__(self, response: str | dict) -> None:
		self.response = response

	def complete(self, prompt: str) -> str | dict:
		return self.response


class OllamaClient:
	"""Call a local Ollama server's JSON-mode generate endpoint."""

	def __init__(
		self,
		*,
		model: str | None = None,
		base_url: str | None = None,
		timeout_seconds: float = 120.0,
	) -> None:
		self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:latest")
		self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
		self.timeout_seconds = timeout_seconds

	def complete(self, prompt: str) -> str:
		if not prompt.strip():
			raise ValueError("prompt cannot be blank")
		if not self.model.strip():
			raise ValueError("Ollama model cannot be blank")

		body = json.dumps(
			{
				"model": self.model,
				"prompt": prompt,
				"stream": False,
				"format": OLLAMA_PLAN_SCHEMA,
				"options": {"temperature": 0},
			}
		).encode("utf-8")
		request = Request(
			f"{self.base_url}/api/generate",
			data=body,
			headers={"Content-Type": "application/json"},
			method="POST",
		)
		try:
			with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
				payload = json.loads(response.read().decode("utf-8"))
		except URLError as exc:
			raise RuntimeError(
				f"Could not reach Ollama at {self.base_url}; ensure Ollama is running and the model is available"
			) from exc
		except (UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise RuntimeError("Ollama returned an invalid JSON response") from exc

		content = payload.get("response") if isinstance(payload, dict) else None
		if not isinstance(content, str) or not content.strip():
			raise RuntimeError("Ollama response did not contain generated text")
		return content
