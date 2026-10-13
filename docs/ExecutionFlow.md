
# Execution Flow — Planning and Structured Workflows

## 1. Purpose

This document explains the complete execution flow of the `06-planning-and-workflows-from-scratch` project.

The project demonstrates how a user goal moves through:

```text
User Goal
   ↓
Planner
   ↓
Plan
   ↓
Plan Validation
   ↓
Workflow Runner
   ↓
Tool Executor
   ↓
Product Tools
   ↓
Observation
   ↓
Workflow Decision
   ↓
Next Step / Replanning
   ↓
Completion
   ↓
Final Outcome
```

The implementation deliberately keeps the responsibilities separated:

- **Planner** decides what work should be performed.
- **Plan Validator** determines whether the proposed plan is structurally safe.
- **Workflow Runner** controls execution.
- **Tool Executor** dispatches approved steps to actual tools.
- **Product Tools** perform the actual business operation.
- **Replanner** proposes replacement work when an observation invalidates the current plan.
- **Completion logic** determines the final eligible product.
- **`main.py`** wires everything together.

A major design principle is:

> **The planner proposes. The application validates and executes.**

The LLM never directly executes a tool.

---

# 2. High-Level Architecture

The current implementation looks like this:

```text
                         USER
                          │
                          │ goal
                          ▼
                    ┌─────────────┐
                    │  main.py    │
                    │ Application │
                    │   Entry     │
                    └──────┬──────┘
                           │
                           │ goal
                           ▼
                    ┌─────────────┐
                    │   Planner   │
                    │             │
                    │ Deterministic│
                    │      OR     │
                    │ LLM + Ollama│
                    └──────┬──────┘
                           │
                           │ Plan
                           ▼
                  ┌──────────────────┐
                  │ Plan Validator   │
                  └────────┬─────────┘
                           │
                    validated Plan
                           │
                           ▼
                  ┌──────────────────┐
                  │ WorkflowRunner   │
                  │                  │
                  │ execution control│
                  └────────┬─────────┘
                           │
                      PlanStep
                           │
                           ▼
                  ┌──────────────────┐
                  │  ToolExecutor    │
                  │                  │
                  │ allowlisted tools│
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  ProductTools    │
                  │                  │
                  │ products.json    │
                  └────────┬─────────┘
                           │
                           │ Observation
                           ▼
                  ┌──────────────────┐
                  │ WorkflowRunner   │
                  └───────┬──────────┘
                          │
             ┌────────────┴────────────┐
             │                         │
          Normal                    Invalidating
          result                    observation
             │                         │
             ▼                         ▼
        Next Step                  Replanner
             │                         │
             │                         ▼
             │                  Replacement Plan
             │                         │
             │                    Validation
             │                         │
             └─────────────┬───────────┘
                           │
                           ▼
                      Final Plan
                           │
                           ▼
                  find_best_candidate()
                           │
                           ▼
                     Final Response
```

---

# 3. Where Does Execution Start?

The execution starts in:

```text
main.py
```

The important entry point is:

```python
if __name__ == "__main__":
    main()
```

The `main()` function:

1. Reads the command-line goal.
2. Determines which planner to use.
3. Creates the planner.
4. Calls `run_goal()`.
5. Prints the final response.

For example:

```bash
python main.py "Find an in-stock running shoe under ₹5,000"
```

The default planner is deterministic unless this is overridden:

```bash
python main.py "Find an in-stock running shoe under ₹5,000" \
    --planner ollama
```

So there are currently two planning paths:

```text
                 main.py
                    │
           ┌────────┴────────┐
           │                 │
   deterministic          Ollama
           │                 │
DeterministicPlanner   LLMPlanner
```

Everything **after planning** follows essentially the same workflow architecture.

---

# 4. `main.py` — Application Entry Point

File:

```text
main.py
```

This is the composition root of the application.

It does not contain the actual workflow implementation.

Instead, it wires the components together.

The important function is:

```python
run_goal(
    goal,
    planner=None,
    executor=None,
    runner=None
)
```

The flow is:

```text
goal
 ↓
planner.plan(goal)
 ↓
Plan
 ↓
ToolExecutor(ProductTools())
 ↓
WorkflowRunner(...)
 ↓
runner.run(plan)
 ↓
final Plan
 ↓
find_best_candidate(final_plan)
 ↓
WorkflowResult
```

The code essentially does:

```python
planner = planner or DeterministicPlanner()

plan = planner.plan(goal)

executor = ToolExecutor(ProductTools())

runner = WorkflowRunner(
    executor,
    replanner=planner.replan if available
)

final_plan = runner.run(plan)
```

This is an important architectural decision.

`main.py` knows **which components need to be connected**, but it does not know how the workflow executes internally.

---

# 5. Step 1 — User Provides a Goal

Suppose the user asks:

```text
Find an in-stock running shoe under ₹5,000
```

At this point the system has only:

```text
Goal
-----
"Find an in-stock running shoe under ₹5,000"
```

The application passes this goal to the planner.

---

# 6. Step 2 — Planner Creates a Plan

The planner is implemented in:

```text
src/planner/planner.py
```

There are two implementations.

## 6.1 DeterministicPlanner

```python
class DeterministicPlanner:
```

This planner does not use an LLM.

It examines the goal and extracts:

- category
- budget
- stock requirement

For:

```text
Find an in-stock running shoe under ₹5,000
```

it creates approximately:

```python
Plan(
    goal="Find an in-stock running shoe under ₹5,000",
    steps=[
        PlanStep(
            step_id="step-1",
            objective="Search for products that match the goal constraints",
            tool_name="search_products",
            tool_input={
                "category": "running_shoes",
                "max_price_inr": 5000,
                "in_stock_only": True
            }
        )
    ]
)
```

So the planner transforms:

```text
Natural language goal
        ↓
Structured execution plan
```

---

# 7. What Is a Plan?

The plan contracts are defined in:

```text
src/planner/contracts.py
```

The two most important objects are:

```text
Plan
PlanStep
```

A `Plan` contains:

```text
goal
steps
status
replan_count
current_step_id
last_observation
last_error
```

A `PlanStep` contains:

```text
step_id
objective
tool_name
tool_input
status
result
error
```

For example:

```text
PLAN
─────────────────────────────────────────
Goal:
Find an in-stock running shoe under ₹5,000

Step:
  ID: step-1
  Objective:
    Search for products matching constraints

  Tool:
    search_products

  Input:
    category = running_shoes
    max_price_inr = 5000
    in_stock_only = true

  Status:
    pending
```

This is the central execution object passed through the workflow.

---

# 8. Plan Status and Step Status

The project explicitly models state transitions.

Plan statuses:

```text
PENDING
   ↓
RUNNING
   ↓
COMPLETED

or

RUNNING
   ↓
NEEDS_REPLAN
   ↓
RUNNING

or

RUNNING
   ↓
FAILED
```

Step statuses:

```text
PENDING
   ↓
RUNNING
   ↓
COMPLETED
```

or:

```text
RUNNING
   ↓
FAILED
```

The transition rules are implemented in:

```text
src/planner/contracts.py
```

This prevents arbitrary state changes.

For example, a completed step cannot suddenly become pending.

---

# 9. Step 3 — Plan Validation

Before execution, the plan goes through:

```text
src/validation/plan_validator.py
```

This is an important security/control boundary.

The system does **not** blindly execute whatever the planner produces.

The validator checks things such as:

### Goal

The goal cannot be blank.

### Number of steps

Maximum:

```text
10 steps
```

### Step IDs

Every step must have:

- a non-empty ID
- a unique ID

### Objective

Every step needs an objective.

### Tool

Only supported tools are allowed:

```text
search_products
get_product
get_product_price
check_inventory
```

### Tool input

Each tool has defined required and optional parameters.

For example:

```text
search_products

required:
    category

optional:
    max_price_inr
    in_stock_only
```

Whereas:

```text
check_inventory

required:
    product_id
```

This is the first major execution boundary:

```text
Planner output
     ↓
VALIDATOR
     ↓
safe structured Plan
```

The planner cannot simply say:

```json
{
  "tool_name": "delete_customer_database"
}
```

because that tool does not exist in the allowlist.

---

# 10. LLM Planner Path

When using:

```bash
--planner ollama
```

the flow becomes:

```text
Goal
 ↓
LLMPlanner
 ↓
build_plan_prompt()
 ↓
OllamaClient
 ↓
Ollama
 ↓
JSON response
 ↓
LLMPlanner parses response
 ↓
Plan object
 ↓
validate_plan()
 ↓
WorkflowRunner
```

The planner implementation is still:

```text
src/planner/planner.py
```

while the prompt is defined in:

```text
src/planner/prompts.py
```

---

# 11. `prompts.py` — Planning Instructions

File:

```text
src/planner/prompts.py
```

This file contains the instructions given to the LLM.

For example, the model is told:

```text
Use only these tools:

search_products
get_product
get_product_price
check_inventory
```

It is also instructed:

```text
Never invent product IDs.
```

and:

```text
For product discovery, make exactly one search_products step
unless the user explicitly includes a product ID.
```

The prompt therefore establishes the **planning contract**.

But the prompt is not considered sufficient protection.

The application still validates the returned plan.

This is an important principle:

> **Prompt rules guide the model. Application validation enforces the contract.**

---

# 12. `LLMPlanner` — Converting Model Output Into a Plan

`LLMPlanner` receives the model response.

Suppose Ollama returns:

```json
{
  "steps": [
    {
      "step_id": "step-1",
      "objective": "Search for in-stock running shoes under ₹5000",
      "tool_name": "search_products",
      "tool_input": {
        "category": "running_shoes",
        "max_price_inr": 5000,
        "in_stock_only": true
      }
    }
  ]
}
```

`LLMPlanner` converts this into:

```python
Plan(
    goal=goal,
    steps=[
        PlanStep(...)
    ]
)
```

Then:

```python
validate_plan(plan)
```

is called.

So the model never produces the final executable object directly.

There is an application conversion layer:

```text
LLM JSON
   ↓
LLMPlanner
   ↓
Plan object
   ↓
Plan Validator
```

---

# 13. Product ID Grounding

One particularly important protection exists in `LLMPlanner`.

For lookup tools:

```text
get_product
get_product_price
check_inventory
```

the planner verifies that the referenced `product_id` came from:

- the user's goal, or
- previous observations.

For example, if the model suddenly generates:

```json
{
  "tool_name": "check_inventory",
  "tool_input": {
    "product_id": "P9999"
  }
}
```

without `P9999` having been established by the goal or previous tool results, the planner rejects it.

This prevents the model from inventing product identifiers.

That is a very good example of:

> **LLM output treated as untrusted input.**

---

# 14. Step 4 — WorkflowRunner Takes Control

After validation:

```text
Plan
 ↓
WorkflowRunner.run(plan)
```

The implementation is:

```text
src/workflow/runner.py
```

This is arguably the most important file in Phase 06.

Why?

Because the **WorkflowRunner owns execution control**.

The planner does not.

The LLM does not.

The tool does not.

The runner controls:

- step ordering
- state transitions
- execution
- observations
- failure handling
- replanning
- preservation of completed work
- replan limits
- repeated-plan detection
- final workflow completion

---

# 15. Initial Workflow Execution

Suppose our plan is:

```text
Plan
 └── step-1
       search_products
```

The runner begins with:

```text
PlanStatus = PENDING
StepStatus = PENDING
```

The runner changes the plan to:

```text
RUNNING
```

Then the step:

```text
PENDING
```

becomes:

```text
RUNNING
```

So:

```text
Plan
  PENDING
     ↓
  RUNNING

Step
  PENDING
     ↓
  RUNNING
```

---

# 16. Step 5 — ToolExecutor

The runner does not directly call `ProductTools`.

Instead:

```text
WorkflowRunner
      ↓
ToolExecutor
      ↓
ProductTools
```

The file is:

```text
src/workflow/executor.py
```

`ToolExecutor` contains an explicit allowlist:

```python
{
    "search_products": tools.search_products,
    "get_product": tools.get_product,
    "get_product_price": tools.get_product_price,
    "check_inventory": tools.check_inventory,
}
```

This means the workflow step says:

```text
tool_name = "search_products"
```

and the executor resolves that name to the actual Python function.

Conceptually:

```python
handler = self._handlers.get(step.tool_name)

result = handler(**step.tool_input)
```

So:

```text
PlanStep
   │
   │ tool_name
   │ tool_input
   ▼
ToolExecutor
   │
   │ lookup
   ▼
Python function
```

---

# 17. Step 6 — ProductTools

The actual business operation lives in:

```text
src/tools/product_tools.py
```

The tool reads:

```text
data/products.json
```

Current catalog:

```text
P1001
PaceRun Flex
running_shoes
₹4,299
stock = 12

P1002
RoadRunner Lite
running_shoes
₹4,799
stock = 0

P1003
TrailSprint Pro
running_shoes
₹6,499
stock = 5

P1004
Everyday Walker
walking_shoes
₹2,999
stock = 8
```

For example:

```python
search_products(
    category="running_shoes",
    max_price_inr=5000,
    in_stock_only=True
)
```

returns:

```json
[
  {
    "id": "P1001",
    "name": "PaceRun Flex",
    "category": "running_shoes",
    "price_inr": 4299,
    "stock_quantity": 12
  }
]
```

---

# 18. Tool Result Becomes an Observation

This is a critical concept.

The tool result is not simply discarded.

It becomes the observation/result associated with the step.

Conceptually:

```text
Action:

search_products(
    category="running_shoes",
    max_price_inr=5000,
    in_stock_only=True
)

             ↓

Tool execution

             ↓

Observation:

[
    {
        "id": "P1001",
        "name": "PaceRun Flex",
        "price_inr": 4299,
        "stock_quantity": 12
    }
]
```

The `PlanStep` now contains:

```text
status = COMPLETED

result =
[
  {
    id: P1001,
    name: PaceRun Flex,
    ...
  }
]
```

So the flow is:

```text
Tool
 ↓
Result
 ↓
PlanStep.result
```

---

# 19. What Happens After a Successful Step?

The runner checks whether the observation should trigger replanning.

This happens through:

```python
_should_replan(observation)
```

The current implementation recognizes observations such as:

```text
in_stock == False
out_of_stock == True
status == "out_of_stock"
status == "failed"
status == "needs_replan"
eligible == False
```

If none of these conditions occur:

```text
Step completed
     ↓
No replan required
     ↓
Continue to next step
```

---

# 20. Important Distinction — Normal Completion vs Replanning

There are two fundamentally different types of failure/change.

### Tool execution failure

Example:

```text
ProductTools throws ProductNotFoundError
```

This is an execution failure.

The workflow marks the step:

```text
FAILED
```

and the plan:

```text
FAILED
```

### Valid tool result that changes the plan

Example:

```json
{
  "product_id": "P1002",
  "in_stock": false
}
```

The tool itself worked correctly.

There was no technical failure.

But the **business fact has changed the validity of the remaining plan**.

That triggers:

```text
NEEDS_REPLAN
```

This distinction is extremely important.

```text
Tool failure
     ↓
FAILED

Valid observation invalidates plan
     ↓
NEEDS_REPLAN
```

---

# 21. Replanning Flow

Suppose the workflow discovers:

```text
P1002
RoadRunner Lite
₹4,799
OUT OF STOCK
```

The runner determines:

```text
This observation invalidates the remaining plan.
```

It then:

```text
RUNNING
   ↓
NEEDS_REPLAN
```

The runner collects completed steps.

Then it calls:

```python
replanner.replan(...)
```

with:

```text
goal
previous_plan
completed_steps
observation
reason
```

So the replanner receives:

```text
Original Goal
      +
Previous Plan
      +
Completed Work
      +
New Observation
      +
Reason
```

---

# 22. Why Completed Work Is Passed to the Replanner

This is one of the most important improvements in the current implementation.

Imagine:

```text
Step 1 ✓
Step 2 ✓
Step 3 ✗
```

Replanning should not produce:

```text
Step 1
Step 2
Step 3
Step 4
```

because Step 1 and Step 2 have already been executed.

Instead:

```text
Step 1 ✓ preserved
Step 2 ✓ preserved
Step 3' → replacement work
```

The current implementation explicitly collects:

```python
completed_steps = [
    step
    for step in plan.steps
    if step.status is StepStatus.COMPLETED
]
```

and passes them to the replanner.

---

# 23. Default Replanner

The default replanner is:

```text
DefaultReplanner
```

in:

```text
src/workflow/runner.py
```

It is deliberately deterministic.

If an observation indicates that something is out of stock, it creates a replacement search with:

```text
in_stock_only = True
```

For example:

```text
Original:

search running shoes
under ₹5000
```

After:

```text
candidate is out of stock
```

the replanner creates:

```text
Search running shoes
under ₹5000
in stock only
```

The replacement gets a new ID:

```text
replan-1
```

---

# 24. LLM Replanning

When using `LLMPlanner`, the replanning process can instead use Ollama.

The flow becomes:

```text
WorkflowRunner
      │
      │ replan(...)
      ▼
LLMPlanner
      │
      ▼
build_replan_prompt()
      │
      ▼
OllamaClient
      │
      ▼
Ollama
      │
      ▼
replacement JSON
      │
      ▼
LLMPlanner
      │
      ▼
Plan
      │
      ▼
validate_plan()
```

The LLM is told:

```text
Return only remaining work.

Do not repeat completed work.
```

Again, the LLM proposes.

The runner controls.

---

# 25. Replacement Plan Validation

The replacement plan is **not trusted**.

The runner checks:

### Is it a Plan?

```text
replacement must be Plan
```

### Same goal?

```text
replacement.goal == previous.goal
```

The replanner cannot silently change:

```text
Find running shoe under ₹5000
```

into:

```text
Find laptop under ₹50000
```

### Pending status?

The replacement plan must be:

```text
PENDING
```

### Valid structure?

It goes through:

```python
validate_plan(replacement)
```

again.

So every plan entering execution is validated.

---

# 26. Preservation of Completed Work

The current runner merges:

```text
completed steps
+
new pending steps
```

For example:

```text
Previous plan:

step-1 ✓
step-2 ✓
step-3 → invalidated
```

Replacement:

```text
replan-1
```

becomes:

```text
step-1 ✓
step-2 ✓
replan-1 → PENDING
```

The previous results remain attached to their steps.

This is exactly what the latest regression test verifies.

---

# 27. Preventing Infinite Replanning

The workflow has two protections.

## Maximum number of replans

Current default:

```text
max_replans = 3
```

So:

```text
Replan 1
Replan 2
Replan 3
STOP
```

The workflow cannot replan forever.

---

# 28. Repeated Pending Action Detection

The runner also creates a signature from pending actions:

```text
tool_name
+
tool_input
```

For example:

```json
[
  {
    "tool_name": "search_products",
    "tool_input": {
      "category": "running_shoes",
      "max_price_inr": 5000,
      "in_stock_only": true
    }
  }
]
```

If a replacement produces exactly the same pending work again, the runner detects:

```text
No progress
```

and stops.

This protects against:

```text
Plan A
 ↓
Replan
 ↓
Plan A again
 ↓
Replan
 ↓
Plan A again
 ↓
...
```

---

# 29. Replan Execution

This is an important point because it was one of the previous gaps that was fixed.

The replacement plan is **actually executed**.

The flow is:

```text
Original Plan
     ↓
Execute
     ↓
Observation invalidates plan
     ↓
Create Replacement Plan
     ↓
Validate Replacement
     ↓
current_plan = replacement
     ↓
Execute Replacement
     ↓
Observation
     ↓
Continue
```

The system does not merely generate a replacement plan and stop.

---

# 30. Complete Example

Let's walk through an end-to-end conceptual example.

Goal:

```text
Find the best running shoe under ₹5,000 that is in stock.
```

### Initial plan

```text
step-1
search_products
{
    category: running_shoes,
    max_price_inr: 5000,
    in_stock_only: false
}
```

Suppose search returns:

```text
P1001 → ₹4299 → stock 12
P1002 → ₹4799 → stock 0
```

The workflow may then perform:

```text
check_inventory(P1002)
```

and receive:

```json
{
  "product_id": "P1002",
  "in_stock": false
}
```

The runner sees:

```text
in_stock == false
```

and says:

```text
Current plan is invalidated.
```

Then:

```text
Plan
 ↓
NEEDS_REPLAN
```

The replanner receives:

```text
Goal:
Find best running shoe under ₹5000

Completed:
search_products(...)

Observation:
P1002 is out of stock

Reason:
out_of_stock
```

It produces:

```text
replan-1

search_products(
    category="running_shoes",
    max_price_inr=5000,
    in_stock_only=True
)
```

The runner validates it.

Then executes it.

Result:

```text
P1001
PaceRun Flex
₹4299
stock 12
```

The replacement succeeds.

Final state:

```text
PlanStatus = COMPLETED
```

Then:

```text
find_best_candidate(final_plan)
```

selects:

```text
P1001
PaceRun Flex
₹4299
stock 12
```

---

# 31. `completion.py`

File:

```text
src/workflow/completion.py
```

This is intentionally separate from the workflow runner.

The function:

```python
find_best_candidate(plan)
```

examines executed search results.

It:

1. Finds search results.
2. Removes products known to be unavailable.
3. Applies category constraint.
4. Applies budget constraint.
5. Applies stock constraint.
6. Selects the lowest-priced eligible candidate.

Conceptually:

```text
Executed Plan
     ↓
Search Results
     ↓
Filter
 ├── category
 ├── budget
 ├── stock
 └── known unavailable IDs
     ↓
Eligible products
     ↓
minimum price
     ↓
Best candidate
```

For our catalog:

```text
P1001 → ₹4299 → stock 12
P1002 → ₹4799 → stock 0
P1003 → ₹6499 → stock 5
```

Goal:

```text
running shoe
under ₹5000
in stock
```

The final candidate is:

```text
P1001
PaceRun Flex
₹4299
stock 12
```

---

# 32. Final Response Construction

`main.py` converts the selected candidate into:

```python
{
    "product_id": candidate["id"],
    "name": candidate["name"],
    "category": candidate["category"],
    "price_inr": candidate["price_inr"],
    "stock_quantity": candidate["stock_quantity"],
    "message": "Found an eligible product matching the request."
}
```

Then:

```python
print(json.dumps(result.answer, ensure_ascii=False))
```

So the final output is produced by the application.

---

# 33. Complete File-by-File Responsibility

## `main.py`

**Responsibility: Application entry and dependency wiring**

Does:

```text
CLI
 ↓
planner
 ↓
executor
 ↓
runner
 ↓
completion
 ↓
response
```

Does **not** implement the workflow algorithm.

---

## `src/planner/contracts.py`

**Responsibility: Data contracts and state transitions**

Contains:

```text
PlanStatus
StepStatus
PlanStep
Plan
```

Defines legal state transitions.

---

## `src/planner/planner.py`

**Responsibility: Plan creation**

Contains:

```text
Planner protocol
LLMPlanner
DeterministicPlanner
PlanningError
```

Converts:

```text
Goal → Plan
```

and, for LLM mode:

```text
LLM response → Plan
```

It also performs product-ID grounding.

---

## `src/planner/prompts.py`

**Responsibility: LLM planning instructions**

Contains:

```text
PLAN_PROMPT_TEMPLATE
REPLAN_PROMPT_TEMPLATE
```

Defines how the model should structure plans.

---

## `src/llm/client.py`

**Responsibility: LLM communication**

Contains:

```text
LLMClient protocol
StaticLLMClient
OllamaClient
OLLAMA_PLAN_SCHEMA
```

`OllamaClient` communicates with:

```text
http://localhost:11434/api/generate
```

and requests structured JSON using the defined schema.

---

## `src/validation/plan_validator.py`

**Responsibility: Application-side plan validation**

Checks:

```text
goal
step count
step IDs
objectives
tools
tool inputs
types
categories
budget
```

This is an execution safety boundary.

---

## `src/workflow/executor.py`

**Responsibility: Tool dispatch**

Maps:

```text
tool name
   ↓
actual Python function
```

Only explicitly registered tools can execute.

---

## `src/workflow/runner.py`

**Responsibility: Workflow orchestration**

This is the core execution engine.

It manages:

```text
plan state
step state
execution order
tool execution
observations
failures
replanning
completed-work preservation
replan limits
no-progress detection
```

This is the most important file to understand for Phase 06.

---

## `src/workflow/completion.py`

**Responsibility: Final outcome evaluation**

Finds the best eligible product from executed results.

It is deliberately separate from workflow orchestration.

---

## `src/tools/product_tools.py`

**Responsibility: Actual product operations**

Implements:

```text
search_products
get_product
get_product_price
check_inventory
```

Uses:

```text
data/products.json
```

---

## `data/products.json`

**Responsibility: Deterministic test data**

Contains the e-commerce product catalog.

---

# 34. Complete Data Flow

The entire application can therefore be understood as:

```text
                    USER
                     │
                     │
                     │ "Find running shoe under ₹5000"
                     ▼
                  main.py
                     │
                     ▼
                  Planner
                     │
          ┌──────────┴──────────┐
          │                     │
 DeterministicPlanner       LLMPlanner
          │                     │
          │                  Prompt
          │                     │
          │                  Ollama
          │                     │
          │                 JSON response
          │                     │
          └──────────┬──────────┘
                     │
                     ▼
                   Plan
                     │
                     ▼
              Plan Validator
                     │
              Valid Plan
                     │
                     ▼
              WorkflowRunner
                     │
                     ▼
                 PlanStep
                     │
                     ▼
               ToolExecutor
                     │
                     ▼
              ProductTools
                     │
                     ▼
             products.json
                     │
                     ▼
                 Result
                     │
                     ▼
               Observation
                     │
             ┌───────┴────────┐
             │                │
         Continue          Replan?
             │                │
             │                ▼
             │           Replanner
             │                │
             │         Replacement Plan
             │                │
             │           Validation
             │                │
             └────────┬───────┘
                      │
                      ▼
                Final Plan
                      │
                      ▼
             find_best_candidate()
                      │
                      ▼
                Final Result
```

---

# 35. The Most Important Architectural Boundary

There are three different responsibilities that should **never be confused**.

### Planner

Answers:

> **What should we do?**

```text
Goal
 ↓
Plan
```

### Runner

Answers:

> **How should execution proceed?**

```text
Plan
 ↓
Execute
 ↓
Observe
 ↓
Continue / Replan
```

### Executor

Answers:

> **How do I actually perform this particular operation?**

```text
Tool name
 ↓
Python function
 ↓
Result
```

This gives:

```text
Planner
"What should happen?"

Runner
"How should the workflow proceed?"

Executor
"How do I perform this action?"
```

That separation is one of the most important lessons from this repository.

---

# 36. Where Does the LLM Actually Participate?

This is also important for interviews.

In deterministic mode:

```text
LLM participation = NONE
```

The planner is:

```text
DeterministicPlanner
```

In Ollama mode:

```text
Goal
 ↓
LLMPlanner
 ↓
Prompt
 ↓
Ollama
 ↓
Structured JSON
 ↓
LLMPlanner
 ↓
Plan
```

The LLM participates in **planning**, and potentially **replanning**.

It does **not**:

```text
❌ execute Python tools
❌ change workflow state directly
❌ decide whether a plan is structurally valid
❌ bypass the executor
❌ directly access products.json
```

The application remains in control.

---

# 37. The Core Principle of This Repository

The entire Phase 06 implementation can be summarized as:

> **The LLM/planner proposes a structured plan. The application validates the plan, executes it through an allowlisted executor, observes the results, and can create a bounded replacement plan when new observations invalidate the original plan.**

Or even shorter:

```text
PLAN
 ↓
VALIDATE
 ↓
EXECUTE
 ↓
OBSERVE
 ↓
CONTINUE
      or
REPLAN
 ↓
EXECUTE
 ↓
COMPLETE
```

---

# 38. What This Repository Is NOT

This is important because it defines the boundary before we move to MCP.

This repository is **not**:

```text
❌ LangGraph
❌ Generic workflow graph engine
❌ General branching framework
❌ Multi-agent system
❌ MCP system
❌ Distributed orchestration system
❌ Production workflow platform
❌ Event-driven workflow engine
```

Phase E is intentionally a **focused, application-controlled structured recovery/replanning workflow**.

That is the correct scope.

---

# 39. The Mental Model to Freeze

Before moving to MCP, I would memorize this:

```text
                     GOAL
                       │
                       ▼
                    PLANNER
                       │
                       │ proposes
                       ▼
                     PLAN
                       │
                       ▼
                PLAN VALIDATOR
                       │
                       │ approved
                       ▼
                WORKFLOW RUNNER
                       │
                       │ PlanStep
                       ▼
                 TOOL EXECUTOR
                       │
                       │ dispatch
                       ▼
                 BUSINESS TOOL
                       │
                       ▼
                  OBSERVATION
                       │
              ┌────────┴────────┐
              │                 │
          Plan still        Plan invalid
            valid               │
              │                 ▼
              │             REPLANNER
              │                 │
              │                 ▼
              │          REPLACEMENT PLAN
              │                 │
              │            VALIDATION
              │                 │
              └────────┬────────┘
                       │
                       ▼
                   COMPLETION
                       │
                       ▼
                 FINAL ANSWER
```

And the five words:

> **Plan → Validate → Execute → Observe → Replan**

That is the essence of Phase 06.

---

## Recommended document name

I would use:

```text
docs/ExecutionFlow.md
```

rather than `ExecutionWorkflow.md`.

And I would keep `docs/ProjctPlan.md` as the **implementation roadmap**, while `docs/ExecutionFlow.md` becomes the **"how the code actually runs"** document.

So your documentation structure becomes:

```text
docs/
├── ProjctPlan.md
└── ExecutionFlow.md
```

`ProjctPlan.md` answers:

> **Why was this project built and how was it implemented phase by phase?**

`ExecutionFlow.md` answers:

> **When I run this application, exactly what happens from `main.py` to the final response?**
