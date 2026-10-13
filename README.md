# Phase 06 — Planning and Structured Workflows

## Purpose

Build a small planning-and-workflow system from first principles, without LangGraph or another orchestration framework. The project should make the boundary clear:

- **Planner:** proposes what work should happen and in what order.
- **Validator:** checks that the proposed plan is safe and executable.
- **Workflow runner:** controls when each step runs and how results or failures affect execution.
- **Executor/tools:** perform the actual application operations and return observations.

The learning example is a product-search task such as: “Find the best running shoe under ₹5,000 that is in stock.” Begin with deterministic plans; introduce the LLM only after the deterministic workflow is tested.

## Current repository state

Phase 0 uses Python 3.13.1 and `pytest`. Phases A–E are implemented: plan/step contracts, deterministic tools, validation, allowlisted execution, structured LLM planning, bounded replanning, and end-to-end workflow outcomes. Phase E is a focused, application-controlled recovery/replanning workflow—not a generic branch or graph engine. The default mode is deterministic and needs no credentials or network access. An optional local Ollama client supports both initial planning and replanning; model-generated plans are validated before execution. No orchestration framework is used.

## Setup and baseline checks

Create and activate a local virtual environment, then install the project dependencies:

- macOS/Linux: `python3 -m venv .venv`, then `source .venv/bin/activate`
- Windows: `py -m venv .venv`, then `.venv\\Scripts\\activate`
- Install dependencies: `python -m pip install -r requirements.txt`
- Run baseline tests from the repository root: `python -m pytest`

The project fixture intentionally covers an in-stock running shoe under ₹5,000, an out-of-stock running shoe, and a running shoe over budget.

## Optional local Ollama planner

The default planner is deterministic. To use a local model, install and start [Ollama](https://ollama.com/), then download a model, for example:

```text
ollama pull llama3.2:latest
```

Run a goal with the Ollama-backed planner:

```text
python main.py --planner ollama "Find an in-stock running shoe under ₹5,000"
```

Configuration:

- `OLLAMA_BASE_URL`: Ollama server URL; defaults to `http://localhost:11434`.
- `OLLAMA_MODEL`: model name; defaults to `llama3.2:latest`.
- `PLANNER_BACKEND`: default planner mode, `deterministic` or `ollama`; the CLI `--planner` option overrides it.
- `--model`: override the model for one run.

The client uses Ollama's local `/api/generate` endpoint with a tool-aware JSON Schema and deterministic temperature through Python's standard library. Lookup IDs from a model plan must be grounded in the user request or prior tool observations. The test suite stubs HTTP responses and does not contact Ollama. Ollama must be running with the selected model pulled before using the `ollama` mode.

## Scope and non-goals

### In scope

1. Typed plan and step contracts.
2. Deterministic plan validation.
3. Product tools backed by a local JSON fixture.
4. Sequential workflow execution with observable state and results.
5. Structured LLM planning, validated before execution.
6. Bounded replanning when observations make the remaining plan unusable.
7. Explicit failure handling and deterministic tests.

### Out of scope

LangGraph, MCP, multi-agent systems, vector databases, complex memory, autonomous sub-agents, production orchestration, and human approval gates. Do not add these until this project’s primitives are understood and working.

## Target execution flow

```text
User goal
	↓
Planner (first deterministic, later LLM)
	↓
Plan validator ── invalid → reject with a useful error
	↓ valid
Workflow runner
	↓
Executor → allowlisted product tool → observation
	↓
Update run state and mark step complete
	↓
Next step / complete / recover / replan
	↓
Final result
```

The model must never execute tools directly. It returns a plan proposal; application code validates the proposal and owns execution, policy, state transitions, and recovery.

## Contract design

Define these contracts in `src/planner/contracts.py` before writing the runner:

- `PlanStatus`: `pending`, `running`, `completed`, `failed`, or `needs_replan`.
- `StepStatus`: `pending`, `running`, `completed`, or `failed`.
- `PlanStep`: stable step ID, human-readable objective, allowlisted tool name, JSON-compatible tool arguments, status, and optional result/error.
- `Plan`: original goal, ordered steps, status, and replan count (plus any run metadata needed by tests).
- `WorkflowResult` or equivalent: terminal status, final answer/result, and the plan/run state for inspection.

Keep contracts serializable and easy to test. Use standard-library dataclasses and enums unless the project has a concrete reason to introduce another schema package. Define state transitions centrally rather than accepting arbitrary status strings.

For executable steps, represent the action explicitly (for example, `tool_name="search_products"` and structured `tool_input`) rather than asking the runner to interpret free-form prose. Keep the natural-language objective for explanation and logs, not dispatch.

## File responsibilities

| File | Responsibility |
|---|---|
| `src/planner/contracts.py` | Plan, step, status, and run-result types. |
| `src/planner/planner.py` | Planner interface and later LLM-backed plan generation; no tool execution. |
| `src/planner/prompts.py` | LLM planning instructions and structured-output expectations. |
| `src/validation/plan_validator.py` | Validate plan structure, allowed tools, argument shapes, IDs, and limits. |
| `src/tools/product_tools.py` | Deterministic product lookup/search/price/inventory operations over fixture data. |
| `src/workflow/executor.py` | Dispatch one validated step to an allowlisted tool and normalize its observation. |
| `src/workflow/runner.py` | Sequential execution, state transitions, stopping, recovery, and replanning coordination. |
| `src/llm/client.py` | Thin model client with a small interface; isolate provider details and configuration. |
| `data/products.json` | Small, deterministic product catalog covering matches, price boundaries, and stock cases. |
| `main.py` | Wire dependencies, accept/run a goal, and display the final result. |
| `tests/` | Contract, validation, planner, workflow, replanning, and failure-recovery tests. |

If validation grows beyond one focused module, split schema/semantic validation then; avoid premature layering.

## Step-by-step implementation phases

### Phase 0 — Establish the baseline

1. Confirm the repository is the dedicated Phase 06 project; keep prior learning repositories frozen.
2. Choose and document the supported Python version and test command. Keep dependencies minimal; add `pytest` and an LLM SDK only when their respective phases need them.
3. Add package markers where needed so imports work consistently from both `main.py` and tests.
4. Add a minimal catalog fixture with product ID, name, category, price in INR, and stock quantity/status. Include at least one in-stock match, one out-of-stock match, and one over-budget item.
5. Add a smoke test proving fixture loading and the test command work.

**Done when:** the project runs tests from its root, and the fixture is deterministic and documented.

### Phase A — Planning contracts (no LLM, no execution)

1. Implement the enums and dataclasses in `src/planner/contracts.py`.
2. Specify required fields, defaults, serialization behavior, and allowed state transitions.
3. Add contract tests for construction, defaults, serialization round-trip if supported, and invalid transitions.
4. Create a hand-authored sample plan in a test; do not add model calls or runner behavior yet.

**Done when:** tests can construct a valid plan and make its state explicit without relying on LLM output.

### Phase B — Deterministic tools, validation, and execution

1. Implement pure/local product operations in `src/tools/product_tools.py`; load the fixture once or inject its data for tests.
2. Give each tool a clear input/output contract (e.g. search by category, retrieve price, check inventory). Avoid hidden model calls in tools.
3. Implement plan validation: non-empty goal/steps, unique step IDs, supported tools only, valid arguments, bounded step count, and any required ordering/dependency checks.
4. Implement `src/workflow/executor.py` as an allowlist dispatcher. Unknown tools and malformed inputs must fail closed.
5. Implement the first `src/workflow/runner.py` as a simple sequential loop over a manually authored plan. Record each observation and step status; stop on a terminal failure rather than silently continuing.
6. Add tests for happy-path execution, tool dispatch, observed results, invalid plans, unknown tools, and failure stopping.

**Done when:** a fixed plan can answer a product query end-to-end with no LLM and repeatable test results.

### Phase C — LLM planner, behind the same contract

1. Define a planner interface whose output is a `Plan`; make the deterministic test planner conform to it.
2. Implement `src/llm/client.py` as a thin, injectable provider boundary. Read credentials from environment/configuration, never commit secrets, and keep network calls out of unit tests.
3. Write `src/planner/prompts.py` to request only structured plan data, with tool names and argument shapes drawn from the supported catalog.
4. Implement LLM output parsing in `src/planner/planner.py`. Treat malformed JSON, missing fields, and provider errors as explicit planning failures.
5. Pass every generated plan through the exact same validator from Phase B before the runner can execute it.
6. Test parsing and validation with mocked model responses: valid plan, malformed response, unsupported tool, invalid arguments, and provider error. Keep any live-model smoke test opt-in.

**Done when:** a model can propose a plan, but invalid output cannot reach execution and tests remain offline/deterministic.

### Phase D — Replanning after observations

1. Define which observations invalidate the remaining plan (for example, a candidate is out of stock) separately from tool/runtime failures.
2. Extend run state with completed steps/results, current step, replan count, and the observation/reason that triggered replanning.
3. Add a replanner entry point that receives the original goal, prior plan, completed results, and new observation. It should propose only the remaining work, or explicitly identify preserved completed work.
4. Validate every replacement plan with the Phase B validator. Preserve completed results and do not repeat successful side-effect-free work without reason.
5. Bound replanning (e.g. a small configurable maximum) and detect repeated plans/no-progress to prevent loops.
6. Add deterministic tests for out-of-stock recovery, preservation of completed work, invalid replacement plans, and replan-limit exhaustion.

**Done when:** a changed observation leads to a bounded, validated revised plan and the run terminates predictably.

### Phase E — Structured recovery and end-to-end outcomes

This phase uses explicit application-controlled decisions for this product-search workflow. It does not implement a reusable branching DSL, graph engine, or generic decision-node abstraction.

1. Add explicit workflow decisions for outcomes such as `in_stock` versus `out_of_stock`; do not encode branch logic as free-form LLM prose.
2. Keep branching policy in application code. The planner can propose work, but the runner decides which branch is eligible from validated observations.
3. Define completion criteria for the user goal (a valid candidate satisfies category, budget, and stock constraints; otherwise report no match).
4. Wire the planner, validator, executor, runner, and tools in `main.py`; make the selected planner configurable so deterministic mode works without credentials.
5. Add end-to-end tests for a successful candidate, first candidate unavailable then a valid alternative, no qualifying products, and exhausted recovery.
6. Update the README with setup, configuration, run/test instructions, architecture boundaries, and known limitations.

**Done when:** recovery decisions and final outcomes are deterministic given the same tool observations, while planning remains replaceable. This milestone does not require a generalized branching engine.

## Validation and test strategy

- Use unit tests for contracts, validator rules, product tools, parser behavior, and runner transitions.
- Use injected tools and mocked planner/model responses; tests must not need network access or credentials.
- Assert both outcomes and state: plan/step statuses, observations, tool-call sequence, replan count, and termination reason.
- Include negative cases: empty/oversized plans, duplicate IDs, unsupported tools, invalid arguments, malformed model output, tool exception, repeated replan, and no eligible product.
- Keep a separately marked, opt-in live LLM smoke test if desired; never make it part of the default test suite.

## Implementation guardrails

1. Complete each phase’s tests and acceptance criteria before beginning the next phase.
2. Do not call tools from the planner. Only the executor may dispatch validated tool actions.
3. Treat LLM output as untrusted input, not as executable instructions.
4. Keep retries for transient tool errors distinct from replanning due to changed task facts; do not retry or replan indefinitely.
5. Make state and observations inspectable so tests and learners can explain why the workflow took each path.
6. Avoid introducing frameworks until the manual implementation is complete and its abstractions are understood.

## Suggested implementation order

`Phase 0 → Phase A → Phase B → Phase C → Phase D → Phase E`

The staged order above records the learning progression. All listed phases are now implemented; the next learning repository should begin only after the acceptance suite is green and the local Ollama path has been exercised when Ollama is available.
