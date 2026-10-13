from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TypeAlias, TypeVar


JSONValue: TypeAlias = (
	None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)


class PlanStatus(str, Enum):
	PENDING = "pending"
	RUNNING = "running"
	COMPLETED = "completed"
	FAILED = "failed"
	NEEDS_REPLAN = "needs_replan"


class StepStatus(str, Enum):
	PENDING = "pending"
	RUNNING = "running"
	COMPLETED = "completed"
	FAILED = "failed"


PLAN_TRANSITIONS: dict[PlanStatus, set[PlanStatus]] = {
	PlanStatus.PENDING: {PlanStatus.RUNNING, PlanStatus.FAILED},
	PlanStatus.RUNNING: {
		PlanStatus.COMPLETED,
		PlanStatus.FAILED,
		PlanStatus.NEEDS_REPLAN,
	},
	PlanStatus.NEEDS_REPLAN: {PlanStatus.RUNNING, PlanStatus.FAILED},
	PlanStatus.COMPLETED: set(),
	PlanStatus.FAILED: set(),
}

STEP_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
	StepStatus.PENDING: {StepStatus.RUNNING, StepStatus.FAILED},
	StepStatus.RUNNING: {StepStatus.COMPLETED, StepStatus.FAILED},
	StepStatus.COMPLETED: set(),
	StepStatus.FAILED: set(),
}


_StatusT = TypeVar("_StatusT", PlanStatus, StepStatus)


def _validate_transition(
	current: _StatusT,
	target: _StatusT,
	transitions: dict[_StatusT, set[_StatusT]],
	entity_name: str,
) -> None:
	if type(current) is not type(target):
		raise TypeError(f"{entity_name} transition must use the matching status type")
	if target not in transitions[current]:
		raise ValueError(
			f"Invalid {entity_name} transition: {current.value} -> {target.value}"
		)


@dataclass
class PlanStep:
	step_id: str
	objective: str
	tool_name: str
	tool_input: dict[str, JSONValue] = field(default_factory=dict)
	status: StepStatus = StepStatus.PENDING
	result: JSONValue | None = None
	error: str | None = None

	def transition_to(self, status: StepStatus) -> None:
		"""Move the step to a permitted next status."""
		_validate_transition(self.status, status, STEP_TRANSITIONS, "step")
		self.status = status

	def to_dict(self) -> dict[str, JSONValue]:
		"""Return a JSON-compatible representation of the step."""
		return asdict(self)


@dataclass
class Plan:
	goal: str
	steps: list[PlanStep]
	status: PlanStatus = PlanStatus.PENDING
	replan_count: int = 0
	current_step_id: str | None = None
	last_observation: JSONValue | None = None
	last_error: str | None = None

	def __post_init__(self) -> None:
		if self.replan_count < 0:
			raise ValueError("replan_count cannot be negative")
		if self.current_step_id is not None and not self.current_step_id.strip():
			raise ValueError("current_step_id cannot be blank")

	def transition_to(self, status: PlanStatus) -> None:
		"""Move the plan to a permitted next status."""
		_validate_transition(self.status, status, PLAN_TRANSITIONS, "plan")
		self.status = status

	def to_dict(self) -> dict[str, JSONValue]:
		"""Return a JSON-compatible representation of the plan."""
		return asdict(self)
