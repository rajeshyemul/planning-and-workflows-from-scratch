## Implementation status

This document preserves the original learning/design plan. Phases 0 through E have since been implemented, including an optional Ollama-backed planner/replanner. Phase E provides focused application-controlled recovery and outcome evaluation; it is not a generic branching graph engine. See the root README for current setup and run instructions. Replanning validates and executes revised plans with bounded/no-progress protection.

---

Yes. At this point, I would **freeze the prior repository** and start the next concept in a completely new repo.

You have now completed the conceptual progression:

```text
01 LLM Foundations
        ↓
02 RAG
        ↓
03 Tool Calling
        ↓
04 Single Agent
        ↓
05 Agent State + Persistence + Memory
```



## Next Step: Planning + Structured Workflows

I recommend the next repository as:

```text
06-planning-and-workflows-from-scratch
```

The important thing is that we **do not jump to LangGraph yet**.

We should first build planning ourselves so you understand exactly what frameworks are later abstracting.

### What changes now?

Until now, our agent essentially does:

```text
Goal
 ↓
Decide ONE next action
 ↓
Execute
 ↓
Observe
 ↓
Decide ONE next action
 ↓
Execute
 ↓
Observe
 ↓
...
```

The next capability introduces:

```text
Goal
 ↓
PLAN
 ↓
Step 1
 ↓
Step 2
 ↓
Step 3
 ↓
Step 4
 ↓
Evaluate
 ↓
Complete
```

And eventually:

```text
Goal
 ↓
Create Plan
 ↓
Execute Step 1
 ↓
Observation
 ↓
Execute Step 2
 ↓
Observation
 ↓
Something unexpected happens
 ↓
REPLAN
 ↓
Execute revised plan
 ↓
...
 ↓
Complete
```

That is a **major conceptual jump**, so we should isolate it in its own repository.

---

# What I want you to learn in the next repo

We will answer these questions by actually implementing them:

### 1. What is Planning?

What does it mean when an agent says:

> "Before I start executing, let me break the goal into steps."

For example:

```text
Goal:

Find the best running shoe under ₹5,000 that is currently in stock.
```

The planner might produce:

```text
Plan

Step 1 → Identify running-shoe products
Step 2 → Check prices
Step 3 → Remove products above ₹5,000
Step 4 → Check inventory
Step 5 → Select the best valid product
Step 6 → Produce final answer
```

---

### 2. What is the difference between Planning and Acting?

This is extremely important.

```text
PLANNER

Goal
 ↓
"What should I do?"
 ↓
Plan
```

versus:

```text
AGENT/RUNNER

Plan
 ↓
"What should I execute now?"
 ↓
Action
 ↓
Tool
 ↓
Observation
```

So we start separating:

```text
Reason about the work
        ↓
Create a plan
        ↓
Execute the plan
```

---

# 3. Planning vs Workflow

We will also introduce an important distinction.

### Planning

The LLM may propose:

```text
Step 1 → Find products
Step 2 → Check price
Step 3 → Check stock
Step 4 → Select product
```

The model is reasoning about **what needs to happen**.

### Workflow

The application controls:

```text
Step 1
  ↓
Step 2
  ↓
Step 3
  ↓
Step 4
```

The application decides **how execution is controlled**.

This distinction becomes extremely important later when you work with:

- LangGraph
- agent SDKs
- enterprise orchestration
- multi-agent systems
- approval gates
- recovery
- deterministic workflows

---

# 4. We will introduce Replanning

This is where the project starts becoming genuinely interesting.

Suppose the plan is:

```text
1. Find running shoes
2. Check price
3. Check inventory
4. Select product
```

But execution discovers:

```text
P1001
Price = ₹4,999
Stock = 0
```

The original plan is no longer sufficient.

The agent may need to change its approach:

```text
Original Plan
     ↓
Execute
     ↓
Observation
     ↓
P1001 unavailable
     ↓
REPLAN
     ↓
Check another candidate
     ↓
Continue
```

This introduces the concept:

> **A plan is not necessarily immutable. Observations can invalidate a plan.**

That will prepare you for much more advanced agent architectures.

---

# Proposed repository

```text
06-planning-and-workflows-from-scratch/

├── data/
│   └── products.json
│
├── src/
│   ├── planner/
│   │   ├── contracts.py
│   │   ├── planner.py
│   │   └── prompts.py
│   │
│   ├── workflow/
│   │   ├── runner.py
│   │   └── executor.py
│   │
│   ├── agent/
│   │   └── ...
│   │
│   ├── tools/
│   │   └── product_tools.py
│   │
│   ├── llm/
│   │   └── client.py
│   │
│   └── validation/
│       └── ...
│
├── tests/
│   ├── test_planner.py
│   ├── test_plan_validation.py
│   ├── test_workflow.py
│   ├── test_replanning.py
│   └── test_failure_recovery.py
│
├── main.py
├── README.md
└── requirements.txt
```

We can adjust this after we define the exact scope.

---

# Most important architectural evolution

Your architecture will evolve from:

```text
                 ┌─────────────┐
                 │    Goal     │
                 └──────┬──────┘
                        ↓
                       LLM
                        ↓
                      Action
                        ↓
                       Tool
                        ↓
                   Observation
                        ↓
                     State
                        ↓
                       LLM
```

to:

```text
                 ┌─────────────┐
                 │    Goal     │
                 └──────┬──────┘
                        ↓
                 ┌─────────────┐
                 │   Planner   │
                 └──────┬──────┘
                        ↓
                       Plan
                        ↓
              ┌───────────────────┐
              │ Workflow / Runner │
              └─────────┬─────────┘
                        ↓
                    Plan Step
                        ↓
                      Action
                        ↓
                       Tool
                        ↓
                   Observation
                        ↓
                      State
                        ↓
               Step Complete?
                  /          \
                Yes           No
                 ↓             ↓
            Next Step       Recover/
                            Replan
```

This is the next major layer.

---

# The learning sequence I recommend

Don't implement everything at once.

### Phase A — Planning Contract

First understand:

```text
Plan
PlanStep
PlanStatus
```

For example:

```python
Plan(
    goal="Find a running shoe under ₹5000 in stock",
    steps=[
        PlanStep(...),
        PlanStep(...),
        PlanStep(...),
    ]
)
```

No LLM yet.

---

### Phase B — Deterministic Plan Execution

We manually create a plan:

```text
Step 1 → Find product
Step 2 → Get price
Step 3 → Check inventory
Step 4 → Finish
```

Then build the workflow runner.

This lets us understand:

```text
Plan
 ↓
Workflow
 ↓
Step
 ↓
Tool
 ↓
Observation
 ↓
Next Step
```

without introducing LLM uncertainty.

---

### Phase C — LLM Planner

Only after the deterministic version works:

```text
Goal
 ↓
LLM
 ↓
Structured Plan
 ↓
Validator
 ↓
Workflow Runner
```

The LLM proposes the plan.

The **application validates and executes it**.

This preserves the architectural boundary we've been building all along.

---

### Phase D — Replanning

Then deliberately introduce failure:

```text
Plan:

1. Find P1001
2. Check price
3. Check stock
```

Execution:

```text
P1001
₹4,999
OUT OF STOCK
```

Now:

```text
Plan invalidated
       ↓
Replanner
       ↓
New Plan
       ↓
P1002 / P1003
       ↓
Continue
```

---

### Phase E — Structured Recovery Workflows

The implemented scope uses explicit application-controlled recovery decisions for the product-search example. It does not provide general-purpose branch nodes or a reusable workflow graph.

Finally we'll explore controlled branching:

```text
             Check inventory
                    │
           ┌────────┴────────┐
           ↓                 ↓
        IN STOCK          OUT OF STOCK
           ↓                 ↓
       Continue            Replan
           ↓                 ↓
        Checkout          Candidate
```

This will teach you why **agentic systems don't necessarily mean "let the LLM control everything."**

In good enterprise architecture:

```text
LLM
 ↓
Reasoning / proposal

Application
 ↓
Validation
 ↓
Policy
 ↓
Workflow
 ↓
Execution
```

That principle will become extremely important for your Atlas work as well.

---

# What we will NOT introduce yet

For this repository, I would deliberately keep these out:

```text
❌ LangGraph
❌ MCP
❌ Multi-agent
❌ Vector database
❌ Complex memory
❌ Autonomous sub-agents
❌ Production orchestration
❌ Human approval gates
```

We first need to understand the primitive ourselves.

Then, when we eventually see something like:

```python
graph.add_node(...)
graph.add_edge(...)
```

you'll understand **why the framework exists**, rather than just learning framework syntax.

---

# Your complete learning progression

The overall journey now becomes:

```text
01 LLM
   │
   ├── Prompt
   ├── Context
   ├── Temperature
   └── Structured output
        ↓
02 RAG
   │
   ├── Chunking
   ├── Embeddings
   ├── Retrieval
   └── Grounding
        ↓
03 Tool Calling
   │
   ├── Tool contracts
   ├── Tool selection
   ├── Validation
   └── Execution
        ↓
04 Single Agent
   │
   └── Decide → Act → Observe → Decide
        ↓
05 State + Persistence + Memory
   │
   ├── Current execution state
   ├── Checkpointing
   └── Reusable memory
        ↓
06 Planning + Workflows        ← NEXT
   │
   ├── Plan
   ├── Plan execution
   ├── Workflow
   └── Replanning
        ↓
07 MCP
   │
   └── Connect agent to external systems
        ↓
08 Multi-Agent
   │
   ├── Specialist agents
   ├── Orchestration
   └── Agent communication
        ↓
09 Guardrails + Evaluation + Recovery
        ↓
10 Production E-commerce Agentic System
```



## So, yes — freeze the current repo.

Create:

```text
06-planning-and-workflows-from-scratch
```

The original recommendation below was written before implementation began. The complete learning/design document and staged implementation now exist in this repository.

The original next step was to create the `README.md`/explanation document and implement **Phase A one piece at a time**; that staged work has been completed.