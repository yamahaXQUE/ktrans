// Typed client for the call -> task backend.
//
// Every call targets the documented /api/* contract (see frontend/README.md).
// When the backend is unreachable (standalone dev) the client transparently
// falls back to the in-memory mock dataset, so the UI is fully interactive on
// its own. `getApiMode()` tells the shell which mode won, so it can show the
// dev-only role switch when running on mock data.

import type {
  ComplaintAnalytics,
  ConfirmCandidatePayload,
  Dictionaries,
  OperatorSummary,
  SessionUser,
  SourceCall,
  TaskCandidate,
} from "../types/domain";
import {
  mockCalls,
  mockCandidates,
  mockDepartments,
  mockOperators,
  mockOperatorUser,
} from "./mockData";
import { initBitrixSession } from "./bitrixApi";

export type ApiMode = "live" | "mock";

let apiMode: ApiMode | null = null;
let mockCandidateState: TaskCandidate[] | null = null;
let mockTaskSeq = 90000;

export function getApiMode(): ApiMode | null {
  return apiMode;
}

function mockState(): TaskCandidate[] {
  if (!mockCandidateState) {
    mockCandidateState = mockCandidates.map((candidate) => ({ ...candidate }));
  }
  return mockCandidateState;
}

function nowIso(): string {
  return new Date().toISOString();
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);

  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.error || error?.detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

/**
 * Resolve the session and lock in live/mock mode:
 *   1. Bitrix iframe handshake (BX24) -> live
 *   2. backend dev session (GET /api/session) -> live
 *   3. neither -> mock, returns null and the shell uses a local user
 */
export async function resolveSession(): Promise<SessionUser | null> {
  const bitrixUser = await initBitrixSession();
  if (bitrixUser) {
    apiMode = "live";
    return bitrixUser;
  }

  try {
    const response = await fetch("/api/session", { headers: { Accept: "application/json" } });
    if (response.ok) {
      const data = (await response.json()) as { user: SessionUser };
      if (data?.user) {
        apiMode = "live";
        return data.user;
      }
    }
  } catch {
    // backend not reachable — fall through to mock
  }

  apiMode = "mock";
  return null;
}

/** The local user used when the app runs on mock data. */
export function mockSessionUser(): SessionUser {
  return { ...mockOperatorUser };
}

export async function getEmulationUsers(): Promise<SessionUser[]> {
  if (apiMode !== "live") {
    return [];
  }

  const response = await fetch("/api/emulation/users", {
    headers: { Accept: "application/json" },
  });
  if (response.status === 404) {
    return [];
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.error || error?.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<SessionUser[]>;
}

export function switchEmulationUser(operatorId: string): Promise<{ user: SessionUser }> {
  return request<{ user: SessionUser }>("/api/emulation/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operatorId }),
  });
}

export function getDictionaries(): Promise<Dictionaries> {
  if (apiMode === "mock") {
    return Promise.resolve({ departments: mockDepartments });
  }
  return request<Dictionaries>("/api/dictionaries");
}

/**
 * Candidates the caller may see. Operators pass their own id (the backend also
 * enforces it); supervisors omit it for everyone, or pass one to drill in.
 */
export function getCandidates(operatorId?: string): Promise<TaskCandidate[]> {
  if (apiMode === "mock") {
    const rows = mockState()
      .filter((candidate) => (operatorId ? candidate.operatorId === operatorId : true))
      .sort((left, right) => (left.createdAt < right.createdAt ? 1 : -1));
    return Promise.resolve(rows.map((candidate) => ({ ...candidate })));
  }

  const query = operatorId ? `?operatorId=${encodeURIComponent(operatorId)}` : "";
  return request<TaskCandidate[]>(`/api/candidates${query}`);
}

export function confirmCandidate(
  id: string,
  payload: ConfirmCandidatePayload,
): Promise<TaskCandidate> {
  if (apiMode === "mock") {
    return Promise.resolve(
      mutateMock(id, (candidate) => ({
        ...candidate,
        ...payload,
        status: "confirmed",
        bitrixTaskId: `T-${(mockTaskSeq += 7)}`,
        failureReason: null,
        rejectionReason: null,
        updatedAt: nowIso(),
      })),
    );
  }

  return request<TaskCandidate>(`/api/candidates/${id}/confirm`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** Re-attempt Bitrix creation for a failed candidate, applying operator edits. */
export function retryCandidate(
  id: string,
  payload: ConfirmCandidatePayload,
): Promise<TaskCandidate> {
  if (apiMode === "mock") {
    return Promise.resolve(
      mutateMock(id, (candidate) => ({
        ...candidate,
        ...payload,
        status: "confirmed",
        bitrixTaskId: `T-${(mockTaskSeq += 7)}`,
        failureReason: null,
        updatedAt: nowIso(),
      })),
    );
  }

  return request<TaskCandidate>(`/api/candidates/${id}/retry`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function rejectCandidate(id: string, reason: string): Promise<TaskCandidate> {
  if (apiMode === "mock") {
    return Promise.resolve(
      mutateMock(id, (candidate) => ({
        ...candidate,
        status: "rejected",
        rejectionReason: reason.trim() || null,
        updatedAt: nowIso(),
      })),
    );
  }

  return request<TaskCandidate>(`/api/candidates/${id}/reject`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
}

export function getOperators(): Promise<OperatorSummary[]> {
  if (apiMode === "mock") {
    return Promise.resolve(buildMockOperatorSummaries());
  }
  return request<OperatorSummary[]>("/api/operators");
}

export function getComplaintAnalytics(): Promise<ComplaintAnalytics> {
  if (apiMode === "mock") {
    const counts = new Map<string, number>();
    for (const candidate of mockState()) {
      if (
        candidate.status !== "confirmed" ||
        !["explicit_complaint", "explicit_negative_feedback"].includes(
          candidate.complaintBasis,
        )
      ) {
        continue;
      }
      const department = candidate.department?.trim() || "Без отдела";
      counts.set(department, (counts.get(department) ?? 0) + 1);
    }
    const totalComplaints = Array.from(counts.values()).reduce(
      (total, count) => total + count,
      0,
    );
    const departments = Array.from(counts.entries())
      .map(([department, count]) => ({
        department,
        count,
        sharePercent: totalComplaints
          ? Math.round((count * 1000) / totalComplaints) / 10
          : 0,
      }))
      .sort(
        (left, right) =>
          right.count - left.count ||
          left.department.localeCompare(right.department, "ru"),
      );
    return Promise.resolve({
      totalComplaints,
      generatedAt: nowIso(),
      departments,
    });
  }
  return request<ComplaintAnalytics>("/api/analytics/complaints");
}

export async function downloadComplaintsExcel(): Promise<string> {
  if (apiMode === "mock") {
    const rows = mockState().filter(
      (candidate) =>
        candidate.status === "confirmed" &&
        ["explicit_complaint", "explicit_negative_feedback"].includes(
          candidate.complaintBasis,
        ),
    );
    const csvRows = [
      [
        "Дата",
        "Оператор",
        "Отдел",
        "Задача",
        "Описание",
        "ID Bitrix",
      ],
      ...rows.map((candidate) => [
        candidate.updatedAt,
        candidate.operatorName,
        candidate.department ?? "Без отдела",
        candidate.taskName,
        candidate.taskDescription,
        candidate.bitrixTaskId ?? "",
      ]),
    ];
    const csv = csvRows
      .map((row) =>
        row
          .map((value) => `"${String(value).split('"').join('""')}"`)
          .join(";"),
      )
      .join("\r\n");
    const filename = "complaints-demo.csv";
    saveDownload(
      new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }),
      filename,
    );
    return filename;
  }

  const response = await fetch("/api/analytics/complaints.xlsx", {
    headers: {
      Accept:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.error || error?.detail || `HTTP ${response.status}`);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename =
    disposition.match(/filename="([^"]+)"/i)?.[1] ?? "complaints.xlsx";
  saveDownload(await response.blob(), filename);
  return filename;
}

function saveDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function getOperatorCalls(operatorId: string): Promise<SourceCall[]> {
  if (apiMode === "mock") {
    const rows = mockCalls
      .filter((call) => call.operatorId === operatorId)
      .sort((left, right) => (left.startedAt < right.startedAt ? 1 : -1));
    return Promise.resolve(rows.map((call) => ({ ...call })));
  }
  return request<SourceCall[]>(`/api/operators/${operatorId}/calls`);
}

export function getCall(id: string): Promise<SourceCall> {
  if (apiMode === "mock") {
    const call = mockCalls.find((item) => item.id === id);
    if (!call) {
      return Promise.reject(new Error("Звонок не найден"));
    }
    return Promise.resolve({ ...call });
  }
  return request<SourceCall>(`/api/calls/${encodeURIComponent(id)}`);
}

export function requestCallAnalysis(id: string): Promise<SourceCall> {
  if (apiMode === "mock") {
    const call = mockCalls.find((item) => item.id === id);
    if (!call) {
      return Promise.reject(new Error("Звонок не найден"));
    }
    return Promise.resolve({
      ...call,
      analysisStatus: "pending",
      analysisRequested: true,
    });
  }
  return request<SourceCall>(`/api/calls/${encodeURIComponent(id)}/analysis`, {
    method: "POST",
  });
}

export function deleteCall(id: string): Promise<void> {
  if (apiMode === "mock") {
    const callIndex = mockCalls.findIndex((item) => item.id === id);
    if (callIndex !== -1) {
      mockCalls.splice(callIndex, 1);
    }
    const candidateIndex = mockState().findIndex(
      (candidate) => candidate.callId === id,
    );
    if (candidateIndex !== -1) {
      mockState().splice(candidateIndex, 1);
    }
    return Promise.resolve();
  }
  return request<void>(`/api/calls/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

function mutateMock(
  id: string,
  update: (candidate: TaskCandidate) => TaskCandidate,
): TaskCandidate {
  const rows = mockState();
  const index = rows.findIndex((candidate) => candidate.id === id);
  if (index === -1) {
    throw new Error("Кандидат не найден");
  }
  const next = update(rows[index]);
  rows[index] = next;
  return { ...next };
}

function buildMockOperatorSummaries(): OperatorSummary[] {
  const rows = mockState();

  return mockOperators
    .map((operator) => {
      const candidates = rows.filter((candidate) => candidate.operatorId === operator.id);
      const calls = mockCalls.filter((call) => call.operatorId === operator.id);
      const lastCallAt = calls.reduce<string | null>((latest, call) => {
        if (!latest || call.startedAt > latest) {
          return call.startedAt;
        }
        return latest;
      }, null);

      return {
        id: operator.id,
        displayName: operator.displayName,
        workPosition: operator.workPosition,
        initials: initials(operator.displayName),
        callCount: calls.length,
        pendingCount: candidates.filter((candidate) => candidate.status === "pending").length,
        confirmedCount: candidates.filter((candidate) => candidate.status === "confirmed").length,
        failedCount: candidates.filter((candidate) => candidate.status === "failed").length,
        rejectedCount: candidates.filter((candidate) => candidate.status === "rejected").length,
        lastCallAt: lastCallAt ? new Date(lastCallAt).toISOString() : null,
      };
    })
    .sort((left, right) => left.displayName.localeCompare(right.displayName, "ru"));
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase("ru-RU") ?? "")
    .join("");
}
