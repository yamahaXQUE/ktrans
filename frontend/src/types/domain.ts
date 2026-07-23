// Frontend domain model for the call -> task flow.
//
// It mirrors the Python backend without leaking transport details:
//   - backend/task_create.py  -> TaskCandidate, ConfirmedTask, RejectedTaskCandidate
//   - bitrix/mirror.py         -> BitrixUser, BitrixDepartment, BitrixCall
//
// Sensitive values (raw phone numbers, recording URLs, SIP credentials) never
// reach this layer: the backend masks or omits them before serializing DTOs.

export type UserRole = "operator" | "supervisor";

/**
 * The signed-in Bitrix24 user, resolved once per session.
 * `role` decides which experience renders; supervisors and above see everyone.
 */
export type SessionUser = {
  id: string;
  displayName: string;
  workPosition: string;
  initials: string;
  avatarUrl: string;
  role: UserRole;
  departmentIds: number[];
  source: "bitrix" | "local";
};

/** 1 = low ... 5 = urgent, matching ConfirmedTask.priority (1..5). */
export type Priority = 1 | 2 | 3 | 4 | 5;

/**
 * Lifecycle of a prediction the operator controls.
 *   pending   - freshly extracted, waiting for the operator to review
 *   confirmed - operator approved it; a task was created in Bitrix
 *   rejected  - operator explicitly declined (RejectedTaskCandidate)
 *   failed    - a confirm attempt reached Bitrix but the create failed
 *               ("упавшая задача"); the operator fixes it and retries
 */
export type CandidateStatus = "pending" | "confirmed" | "rejected" | "failed";

export type CallDirection = "inbound" | "outbound";
export type AnalysisStatus = "pending" | "processing" | "completed" | "failed";
export type ComplaintBasis =
  | "legacy"
  | "explicit_complaint"
  | "explicit_negative_feedback"
  | "none";

export type TaskType =
  | "legacy"
  | "service_fm"
  | "bar_food"
  | "product_quality_food_safety"
  | "semi_finished_products"
  | "ice_cream"
  | "camera_recording"
  | "receipt_search"
  | "mobile_app_error"
  | "mobile_app_wrong_information"
  | "payment_check"
  | "operator_quality_violation"
  | "none";

/**
 * A telephony record from Bitrix (voximplant.statistic.get), already masked.
 * `transcript` is the Whisper transcription used to extract the candidate.
 */
export type SourceCall = {
  id: string;
  statisticId: number;
  operatorId: string;
  operatorName: string;
  direction: CallDirection;
  durationSeconds: number;
  startedAt: string;
  /** Masked, e.g. "+996 XXX XX 45 09" — raw numbers stay server-side. */
  phoneMasked: string;
  failedCode: string | null;
  transcript: string;
  conversationTitle: string;
  analysisStatus: AnalysisStatus;
  analysisRequested: boolean;
  analysisError: string | null;
};

/**
 * A model prediction extracted from one call. Never a Bitrix task by itself:
 * the operator turns it into a ConfirmedTask (with edits) or rejects it.
 */
export type TaskCandidate = {
  id: string;
  callId: string;
  call: SourceCall;
  operatorId: string;
  operatorName: string;
  conversationTitle: string;
  shouldCreate: boolean;
  taskName: string;
  taskDescription: string;
  department: string | null;
  priority: Priority;
  taskType: TaskType;
  qualityCriterion: number | null;
  complaintBasis: ComplaintBasis;
  complaintEvidence: string;
  status: CandidateStatus;
  /** Set once confirmed and created in Bitrix. */
  bitrixTaskId: string | null;
  /** Set when status === "failed". */
  failureReason: string | null;
  /** Set when status === "rejected". */
  rejectionReason: string | null;
  createdAt: string;
  updatedAt: string;
};

export type Department = {
  id: number;
  name: string;
};

/**
 * One row of the supervisor dashboard, aggregated per operator.
 */
export type OperatorSummary = {
  id: string;
  displayName: string;
  workPosition: string;
  initials: string;
  callCount: number;
  pendingCount: number;
  confirmedCount: number;
  failedCount: number;
  rejectedCount: number;
  lastCallAt: string | null;
};

export type ComplaintDepartmentStat = {
  department: string;
  count: number;
  sharePercent: number;
};

export type ComplaintAnalytics = {
  totalComplaints: number;
  generatedAt: string;
  departments: ComplaintDepartmentStat[];
};

export type Dictionaries = {
  departments: Department[];
};

/** Payload the operator submits when confirming/fixing a candidate. */
export type ConfirmCandidatePayload = {
  taskName: string;
  taskDescription: string;
  department: string | null;
  priority: Priority;
};
