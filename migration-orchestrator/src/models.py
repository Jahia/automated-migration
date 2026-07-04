from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────


class StepStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    running = "running"
    verifying = "verifying"
    done = "done"
    failed = "failed"
    blocked = "blocked"
    waiting_human = "waiting_human"
    halted = "halted"
    rejected = "rejected"
    # Decision point (ASSIST-PLAN §3): retries exhausted with strategies left, or a
    # review checkpoint reached. Decided ONLY via POST /runs/{id}/steps/{id}/decide.
    decision_pending = "decision_pending"


class StoryStatus(str, Enum):
    pending = "pending"
    running = "running"
    approved = "approved"
    failed = "failed"


class EpicStatus(str, Enum):
    pending = "pending"
    running = "running"
    reviewing = "reviewing"
    waiting_approval = "waiting_approval"
    approved = "approved"
    failed = "failed"


class RunStatus(str, Enum):
    created = "created"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"


# ── Strategies (pre-registered decision options, ASSIST-PLAN §3-4) ────


class StrategyPatch(BaseModel):
    """Full replacement of the provided fields on the target step."""
    step_id: str
    inputs: dict | None = None
    acceptance_criteria: list[str] | None = None


class Strategy(BaseModel):
    id: str
    title: str = ""
    when: str = "on_retries_exhausted"
    order: int = 0
    # arm_swap=True: whole generator-emitted arm swap — exempt from the
    # PROBE-preservation lint. halt=True: converts the decision into a halted
    # gate (gate_type "segmentation") instead of patch+rerun.
    arm_swap: bool = False
    halt: bool = False
    patches: list[StrategyPatch] = []
    skip: list[str] = []
    notes: str = ""


# ── Input (POST /runs) ────────────────────────────────


class StepInput(BaseModel):
    id: str
    title: str
    task_type: str = "general"
    agent: str | None = None
    depends_on: list[str] = []
    inputs: dict = {}
    expected_outputs: dict = {}
    acceptance_criteria: list[str] = []
    max_attempts: int = 3
    strategies: list[Strategy] = []
    # review=True: scheduled decision checkpoint — the engine NEVER sends it to
    # an agent; when selected it becomes decision_pending and the run pauses.
    review: bool = False


class StoryInput(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = []
    depends_on: list[str] = []
    github_issues: list[str] = []
    steps: list[StepInput] = []


class ReviewConfig(BaseModel):
    max_review_rounds: int = 3
    review_criteria: list[str] = []
    auto_approve_on_max_rounds: bool = True


class EpicInput(BaseModel):
    id: str
    title: str
    goal: str
    stories: list[StoryInput]
    review_config: ReviewConfig = Field(default_factory=ReviewConfig)
    github_issues: list[str] = []


class PlanInput(BaseModel):
    goal: str
    repo_dir: str
    model: str = "anthropic/claude-sonnet-4-5"
    epics: list[EpicInput]
    github_repo: str | None = None


# ── GitHub ─────────────────────────────────────────────


class GitHubComment(BaseModel):
    author: str
    body: str
    created_at: str


class GitHubIssue(BaseModel):
    ref: str
    number: int
    title: str
    body: str
    state: str
    labels: list[str] = []
    comments: list[GitHubComment] = []
    url: str


# ── State ─────────────────────────────────────────────


class HumanQuestion(BaseModel):
    question_id: str
    step_id: str
    question: str
    options: list[dict] = []
    default: str | None = None
    timestamp: float


class AgentResult(BaseModel):
    step_id: str
    agent: str
    status: str
    summary: str
    modified_files: list[str] = []
    commands_requested: list[str] = []
    risks: list[str] = []
    loop_to: str | None = None


class VerificationResult(BaseModel):
    passed: bool
    checks: list[str] = []
    errors: list[str] = []


class TraceEvent(BaseModel):
    seq: int
    timestamp: float
    type: str
    step_id: str | None = None
    story_id: str | None = None
    epic_id: str | None = None
    payload: dict = {}


class StepState(BaseModel):
    id: str
    story_id: str
    title: str = ""
    task_type: str = "general"
    agent: str = "code"
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict = Field(default_factory=dict)
    expected_outputs: dict = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.pending
    attempt: int = 0
    max_attempts: int = 3
    # Legacy field: kept for backward compat with persisted run blobs and the
    # frontend types (P5.5 dropped opencode; the engine no longer sets it).
    opencode_session_id: str | None = None
    agent_result: AgentResult | None = None
    verification: VerificationResult | None = None
    question: HumanQuestion | None = None
    human_answer: str | None = None
    streaming_text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cache: int = 0
    cost: float = 0.0
    trace: list[TraceEvent] = []
    started_at: float | None = None
    completed_at: float | None = None
    duration_ms: float | None = None
    prompt_text: str | None = None
    # Migration profile: when a step HALTs for human review, which domain panel
    # the frontend should render (scope|model|fidelity|content|golive). Null = generic.
    gate_type: str | None = None
    # Decision protocol (ASSIST-PLAN §3): pre-registered strategies, review flag,
    # and the ids of strategies already consumed (each strategy is single-shot).
    strategies: list[Strategy] = Field(default_factory=list)
    review: bool = False
    strategies_applied: list[str] = Field(default_factory=list)


class StoryState(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = []
    depends_on: list[str] = []
    github_issues: list[str] = []
    github_issues_content: list[GitHubIssue] = []
    status: StoryStatus = StoryStatus.pending
    steps: list[StepState] = Field(default_factory=list)
    current_step_index: int = 0


# ── Review results ────────────────────────────────────


class NewStepProposal(BaseModel):
    id: str
    title: str
    task_type: str = "general"
    agent: str | None = None
    depends_on: list[str] = []
    inputs: dict = {}
    expected_outputs: dict = {}
    acceptance_criteria: list[str] = []
    reason: str


class NewStoryProposal(BaseModel):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str] = []
    depends_on: list[str] = []
    github_issues: list[str] = []
    steps: list[NewStepProposal] = []
    reason: str


class EpicReviewApproved(BaseModel):
    action: Literal["approved"] = "approved"
    summary: str
    confidence: float = 1.0
    remaining_concerns: list[str] = []


class EpicReviewRectify(BaseModel):
    action: Literal["rectify"] = "rectify"
    diagnosis: str
    new_stories: list[NewStoryProposal]
    target_after_story_id: str | None = None


EpicReviewResult = EpicReviewApproved | EpicReviewRectify


class RectificationProposal(BaseModel):
    proposal_id: str
    epic_id: str
    round: int
    result: EpicReviewRectify
    status: Literal["pending_approval", "approved", "rejected"] = "pending_approval"
    timestamp: float


# ── Epic state ────────────────────────────────────────


class EpicState(BaseModel):
    id: str
    title: str
    goal: str
    github_issues: list[str] = []
    github_issues_content: list[GitHubIssue] = []
    status: EpicStatus = EpicStatus.pending
    stories: list[StoryState] = Field(default_factory=list)
    review_config: ReviewConfig = Field(default_factory=ReviewConfig)
    review_round: int = 0
    review_history: list[dict] = []
    pending_proposal: RectificationProposal | None = None
    opencode_session_id: str | None = None


# ── Run state ─────────────────────────────────────────


class RunState(BaseModel):
    run_id: str
    goal: str
    repo_dir: str
    github_repo: str | None = None
    model: str
    status: RunStatus = RunStatus.running
    epics: list[EpicState] = Field(default_factory=list)
    current_epic_id: str | None = None
    current_story_id: str | None = None
    current_step_id: str | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    created_at: float
    updated_at: float
    forced_next_step: str | None = None
    # Migration profile: how an LLM/agent drives this run's quality gates.
    # manual = human approves every gate; assisted = agent auto-approves green gates
    # and escalates amber/red; autonomous = agent decides all, human on failure only.
    autonomy: str = "assisted"


# ── Agent discovery ───────────────────────────────────


class AgentInfo(BaseModel):
    name: str
    description: str
    model: str | None = None


class AgentsInfo(BaseModel):
    available: list[AgentInfo] = Field(default_factory=list)
    routing: dict[str, str] = Field(default_factory=dict)


# ── SSE ───────────────────────────────────────────────


class SSEEvent(BaseModel):
    type: str
    run_id: str
    epic_id: str | None = None
    story_id: str | None = None
    step_id: str | None = None
    data: dict = {}


# ── Step transition (for loop logic) ──────────────────


class StepTransition(BaseModel):
    from_step_id: str
    to_step_id: str
    condition: str = "failed"
