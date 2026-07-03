export type StepStatus = 'pending' | 'ready' | 'running' | 'verifying' | 'done' | 'failed' | 'blocked' | 'waiting_human' | 'halted' | 'rejected'

export type StoryStatus = 'pending' | 'running' | 'approved' | 'failed'

export type EpicStatus = 'pending' | 'running' | 'reviewing' | 'waiting_approval' | 'approved' | 'failed'

export type RunStatus = 'created' | 'running' | 'paused' | 'completed' | 'failed' | 'aborted'

export interface AgentResult {
  step_id: string
  agent: string
  status: string
  summary: string
  modified_files: string[]
  commands_requested: string[]
  risks: string[]
  loop_to?: string | null
}

export interface VerificationResult {
  passed: boolean
  checks: string[]
  errors: string[]
}

export interface HumanQuestion {
  question_id: string
  step_id: string
  question: string
  options: { label: string; value: string }[]
  default?: string | null
  timestamp: number
}

export interface StepState {
  id: string
  story_id: string
  title: string
  task_type: string
  agent: string
  depends_on: string[]
  inputs: Record<string, unknown>
  expected_outputs: Record<string, unknown>
  acceptance_criteria: string[]
  status: StepStatus
  attempt: number
  max_attempts: number
  opencode_session_id?: string | null
  agent_result?: AgentResult | null
  verification?: VerificationResult | null
  question?: HumanQuestion | null
  human_answer?: string | null
  streaming_text: string
  tokens_in: number
  tokens_out: number
  tokens_cache: number
  cost: number
  gate_type?: string | null
}

export interface GitHubIssue {
  ref: string
  number: number
  title: string
  body: string
  state: string
  labels: string[]
  comments: { author: string; body: string; created_at: string }[]
  url: string
}

export interface StoryState {
  id: string
  title: string
  description: string
  acceptance_criteria: string[]
  depends_on: string[]
  github_issues: string[]
  github_issues_content: GitHubIssue[]
  status: StoryStatus
  steps: StepState[]
  current_step_index: number
}

export interface NewStepProposal {
  id: string
  title: string
  task_type: string
  agent?: string | null
  depends_on: string[]
  inputs: Record<string, unknown>
  expected_outputs: Record<string, unknown>
  acceptance_criteria: string[]
  reason: string
}

export interface NewStoryProposal {
  id: string
  title: string
  description: string
  acceptance_criteria: string[]
  depends_on: string[]
  github_issues: string[]
  steps: NewStepProposal[]
  reason: string
}

export interface EpicReviewRectify {
  action: 'rectify'
  diagnosis: string
  new_stories: NewStoryProposal[]
  target_after_story_id?: string | null
}

export interface RectificationProposal {
  proposal_id: string
  epic_id: string
  round: number
  result: EpicReviewRectify
  status: 'pending_approval' | 'approved' | 'rejected'
  timestamp: number
}

export interface EpicState {
  id: string
  title: string
  goal: string
  github_issues: string[]
  github_issues_content: GitHubIssue[]
  status: EpicStatus
  stories: StoryState[]
  review_config: {
    max_review_rounds: number
    review_criteria: string[]
    auto_approve_on_max_rounds: boolean
  }
  review_round: number
  review_history: { round: number; result: Record<string, unknown>; timestamp: number }[]
  pending_proposal?: RectificationProposal | null
}

export interface RunState {
  run_id: string
  goal: string
  repo_dir: string
  github_repo?: string | null
  model: string
  status: RunStatus
  epics: EpicState[]
  current_epic_id?: string | null
  current_story_id?: string | null
  current_step_id?: string | null
  created_at: number
  updated_at: number
}

export interface SSEEvent {
  type: string
  run_id: string
  epic_id?: string | null
  story_id?: string | null
  step_id?: string | null
  data: Record<string, unknown>
}
