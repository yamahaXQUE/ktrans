import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  LayoutDashboard,
  LayoutList,
  PanelLeftClose,
  PanelLeftOpen,
  PhoneCall,
  Search,
} from "lucide-react";
import {
  confirmCandidate,
  deleteCall,
  downloadComplaintsExcel,
  getApiMode,
  getCandidates,
  getComplaintAnalytics,
  getDictionaries,
  getEmulationUsers,
  getOperatorCalls,
  getOperators,
  mockSessionUser,
  rejectCandidate,
  requestCallAnalysis,
  resolveSession,
  retryCandidate,
  switchEmulationUser,
} from "./api/tasksApi";
import { mockOperatorUser, mockSupervisorUser } from "./api/mockData";
import type {
  CandidateStatus,
  ComplaintAnalytics,
  ConfirmCandidatePayload,
  Dictionaries,
  OperatorSummary,
  SessionUser,
  SourceCall,
  TaskCandidate,
  UserRole,
} from "./types/domain";
import { normalizeText } from "./utils/format";
import { EmptyState } from "./components/common/EmptyState";
import { LoadingState } from "./components/common/LoadingState";
import { CandidateCard } from "./components/operator/CandidateCard";
import { CandidateFilters, type StatusFilter } from "./components/operator/CandidateFilters";
import { TaskReviewModal } from "./components/operator/TaskReviewModal";
import { OwnCallsPanel } from "./components/operator/OwnCallsPanel";
import { OperatorList } from "./components/supervisor/OperatorList";
import { OperatorCallsPanel } from "./components/supervisor/OperatorCallsPanel";
import { CallTranscriptModal } from "./components/supervisor/CallTranscriptModal";
import { AnalyticsDashboard } from "./components/supervisor/AnalyticsDashboard";

const STATUS_ORDER: Record<CandidateStatus, number> = {
  failed: 0,
  pending: 1,
  confirmed: 2,
  rejected: 3,
};

type SupervisorView = "operators" | "analytics";
type OperatorView = "calls" | "tasks";

export default function App() {
  const [session, setSession] = useState<SessionUser | null>(null);
  const [resolving, setResolving] = useState(true);
  const [mockMode, setMockMode] = useState(false);
  const [roleOverride, setRoleOverride] = useState<UserRole | null>(null);
  const [dictionaries, setDictionaries] = useState<Dictionaries | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [emulationUsers, setEmulationUsers] = useState<SessionUser[]>([]);
  const [switchingUser, setSwitchingUser] = useState(false);

  // Operator state
  const [candidates, setCandidates] = useState<TaskCandidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [departmentFilter, setDepartmentFilter] = useState<string | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [filtersHidden, setFiltersHidden] = useState(false);
  const [reviewCandidate, setReviewCandidate] = useState<TaskCandidate | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [operatorView, setOperatorView] = useState<OperatorView>("calls");
  const [ownCalls, setOwnCalls] = useState<SourceCall[]>([]);
  const [loadingOwnCalls, setLoadingOwnCalls] = useState(false);

  // Supervisor state
  const [operators, setOperators] = useState<OperatorSummary[]>([]);
  const [loadingOperators, setLoadingOperators] = useState(false);
  const [operatorQuery, setOperatorQuery] = useState("");
  const [selectedOperator, setSelectedOperator] = useState<OperatorSummary | null>(null);
  const [operatorCalls, setOperatorCalls] = useState<SourceCall[]>([]);
  const [operatorCandidates, setOperatorCandidates] = useState<TaskCandidate[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [transcriptCall, setTranscriptCall] = useState<SourceCall | null>(null);
  const [requestingCallId, setRequestingCallId] = useState<string | null>(null);
  const [supervisorView, setSupervisorView] =
    useState<SupervisorView>("operators");
  const [complaintAnalytics, setComplaintAnalytics] =
    useState<ComplaintAnalytics | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [exportingAnalytics, setExportingAnalytics] = useState(false);

  const effectiveUser: SessionUser | null = useMemo(() => {
    if (mockMode && roleOverride) {
      return roleOverride === "supervisor" ? mockSupervisorUser : mockOperatorUser;
    }
    return session;
  }, [mockMode, roleOverride, session]);

  const role: UserRole = effectiveUser?.role ?? "operator";

  // Session bootstrap: empty until we know who the user is (fetch to DB).
  useEffect(() => {
    let active = true;
    resolveSession()
      .then((user) => {
        if (!active) {
          return;
        }
        setMockMode(getApiMode() === "mock");
        setSession(user ?? mockSessionUser());
      })
      .catch((err: Error) => {
        if (active) {
          setSession(null);
          setMockMode(false);
          setError(err.message);
        }
      })
      .finally(() => {
        if (active) {
          setResolving(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!session) {
      return;
    }
    getDictionaries()
      .then(setDictionaries)
      .catch((err: Error) => setError(err.message));
  }, [session]);

  useEffect(() => {
    if (!session || mockMode) {
      setEmulationUsers([]);
      return;
    }
    let active = true;
    getEmulationUsers()
      .then((users) => {
        if (active) {
          setEmulationUsers(users);
        }
      })
      .catch((err: Error) => {
        if (active) {
          setError(err.message);
        }
      });
    return () => {
      active = false;
    };
  }, [mockMode, session]);

  useEffect(() => {
    if (!notice) {
      return;
    }
    const timeout = window.setTimeout(() => setNotice(null), 3200);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  // Reset per-role scaffolding when the effective role changes.
  useEffect(() => {
    setReviewCandidate(null);
    setSelectedOperator(null);
    setTranscriptCall(null);
    setSupervisorView("operators");
    setOperatorView("calls");
    setError(null);
  }, [role]);

  // Load the operator's complete call history and analyzed candidates.
  useEffect(() => {
    if (!effectiveUser || role !== "operator") {
      return;
    }
    let active = true;
    setLoadingCandidates(true);
    setLoadingOwnCalls(true);
    setError(null);
    Promise.all([
      getCandidates(effectiveUser.id),
      getOperatorCalls(effectiveUser.id),
    ])
      .then(([rows, calls]) => {
        if (active) {
          setCandidates(rows);
          setOwnCalls(calls);
        }
      })
      .catch((err: Error) => {
        if (active) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingCandidates(false);
          setLoadingOwnCalls(false);
        }
      });
    return () => {
      active = false;
    };
  }, [effectiveUser, role]);

  // Refresh queued work so "В очереди" cannot remain stale in the UI.
  useEffect(() => {
    if (
      !effectiveUser ||
      role !== "operator" ||
      !ownCalls.some(
        (call) =>
          call.analysisStatus === "processing" ||
          (call.analysisStatus === "pending" && call.analysisRequested),
      )
    ) {
      return;
    }
    let active = true;
    const interval = window.setInterval(() => {
      Promise.all([
        getOperatorCalls(effectiveUser.id),
        getCandidates(effectiveUser.id),
      ])
        .then(([calls, rows]) => {
          if (active) {
            setOwnCalls(calls);
            setCandidates(rows);
          }
        })
        .catch((err: Error) => {
          if (active) {
            setError(err.message);
          }
        });
    }, 4000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [effectiveUser, ownCalls, role]);

  // Load the supervisor dashboard.
  useEffect(() => {
    if (role !== "supervisor") {
      return;
    }
    let active = true;
    setLoadingOperators(true);
    setError(null);
    getOperators()
      .then((rows) => {
        if (active) {
          setOperators(rows);
        }
      })
      .catch((err: Error) => {
        if (active) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingOperators(false);
        }
      });
    return () => {
      active = false;
    };
  }, [role]);

  useEffect(() => {
    if (role !== "supervisor" || supervisorView !== "analytics") {
      return;
    }
    let active = true;
    setLoadingAnalytics(true);
    setError(null);
    getComplaintAnalytics()
      .then((analytics) => {
        if (active) {
          setComplaintAnalytics(analytics);
        }
      })
      .catch((err: Error) => {
        if (active) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingAnalytics(false);
        }
      });
    return () => {
      active = false;
    };
  }, [role, supervisorView]);

  // Load a selected operator's calls + candidates for the drilldown.
  useEffect(() => {
    if (role !== "supervisor" || !selectedOperator) {
      return;
    }
    let active = true;
    setLoadingDetail(true);
    Promise.all([
      getOperatorCalls(selectedOperator.id),
      getCandidates(selectedOperator.id),
    ])
      .then(([calls, rows]) => {
        if (active) {
          setOperatorCalls(calls);
          setOperatorCandidates(rows);
        }
      })
      .catch((err: Error) => {
        if (active) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingDetail(false);
        }
      });
    return () => {
      active = false;
    };
  }, [role, selectedOperator]);

  useEffect(() => {
    if (
      role !== "supervisor" ||
      !selectedOperator ||
      !operatorCalls.some(
        (call) =>
          call.analysisStatus === "processing" ||
          (call.analysisStatus === "pending" && call.analysisRequested),
      )
    ) {
      return;
    }
    let active = true;
    const interval = window.setInterval(() => {
      Promise.all([
        getOperatorCalls(selectedOperator.id),
        getCandidates(selectedOperator.id),
      ]).then(([calls, rows]) => {
        if (active) {
          setOperatorCalls(calls);
          setOperatorCandidates(rows);
        }
      });
    }, 4000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [operatorCalls, role, selectedOperator]);

  const visibleCandidates = useMemo(() => {
    const query = normalizeText(searchQuery);
    return candidates
      .filter((candidate) => statusFilter === "all" || candidate.status === statusFilter)
      .filter(
        (candidate) => departmentFilter === "all" || candidate.department === departmentFilter,
      )
      .filter((candidate) => {
        if (!query) {
          return true;
        }
        const haystack = normalizeText(
          [
            candidate.conversationTitle,
            candidate.taskName,
            candidate.taskDescription,
            candidate.department ?? "",
            candidate.callId,
            candidate.call.transcript,
          ].join(" "),
        );
        return haystack.includes(query);
      })
      .sort(
        (left, right) =>
          STATUS_ORDER[left.status] - STATUS_ORDER[right.status] ||
          (left.createdAt < right.createdAt ? 1 : -1),
      );
  }, [candidates, departmentFilter, searchQuery, statusFilter]);

  const visibleOperators = useMemo(() => {
    const query = normalizeText(operatorQuery);
    if (!query) {
      return operators;
    }
    return operators.filter((operator) =>
      normalizeText(`${operator.displayName} ${operator.workPosition}`).includes(query),
    );
  }, [operatorQuery, operators]);

  const candidateByCallId = useMemo(() => {
    const map = new Map<string, TaskCandidate>();
    for (const candidate of operatorCandidates) {
      map.set(candidate.callId, candidate);
    }
    return map;
  }, [operatorCandidates]);

  const ownCandidateByCallId = useMemo(() => {
    const map = new Map<string, TaskCandidate>();
    for (const candidate of candidates) {
      map.set(candidate.callId, candidate);
    }
    return map;
  }, [candidates]);

  const pendingCount = useMemo(
    () => candidates.filter((candidate) => candidate.status === "pending").length,
    [candidates],
  );
  const failedCount = useMemo(
    () => candidates.filter((candidate) => candidate.status === "failed").length,
    [candidates],
  );

  function applyCandidate(updated: TaskCandidate) {
    setCandidates((current) =>
      current.map((candidate) => (candidate.id === updated.id ? updated : candidate)),
    );
  }

  async function handleConfirm(payload: ConfirmCandidatePayload) {
    if (!reviewCandidate) {
      return;
    }
    setReviewBusy(true);
    setError(null);
    try {
      const updated = await confirmCandidate(reviewCandidate.id, payload);
      applyCandidate(updated);
      setReviewCandidate(null);
      setNotice(`Задача создана · ${updated.bitrixTaskId ?? "Bitrix"}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать задачу");
    } finally {
      setReviewBusy(false);
    }
  }

  async function handleRetry(payload: ConfirmCandidatePayload) {
    if (!reviewCandidate) {
      return;
    }
    setReviewBusy(true);
    setError(null);
    try {
      const updated = await retryCandidate(reviewCandidate.id, payload);
      applyCandidate(updated);
      setReviewCandidate(null);
      setNotice(
        updated.status === "confirmed"
          ? `Задача создана · ${updated.bitrixTaskId ?? "Bitrix"}`
          : "Повтор отправлен",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось повторить создание");
    } finally {
      setReviewBusy(false);
    }
  }

  async function handleReject(reason: string) {
    if (!reviewCandidate) {
      return;
    }
    setReviewBusy(true);
    setError(null);
    try {
      const updated = await rejectCandidate(reviewCandidate.id, reason);
      applyCandidate(updated);
      setReviewCandidate(null);
      setNotice("Кандидат отклонён");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отклонить кандидата");
    } finally {
      setReviewBusy(false);
    }
  }

  async function handleEmulationUserChange(operatorId: string) {
    if (!operatorId || operatorId === effectiveUser?.id) {
      return;
    }
    setSwitchingUser(true);
    setError(null);
    try {
      await switchEmulationUser(operatorId);
      window.location.reload();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Не удалось переключить пользователя",
      );
      setSwitchingUser(false);
    }
  }

  async function handleRequestCallAnalysis(call: SourceCall) {
    setRequestingCallId(call.id);
    setError(null);
    try {
      const updated = await requestCallAnalysis(call.id);
      setOperatorCalls((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setOwnCalls((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setTranscriptCall((current) =>
        current?.id === updated.id ? updated : current,
      );
      setNotice("Звонок поставлен в очередь на расшифровку и проверку");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Не удалось запустить анализ звонка",
      );
    } finally {
      setRequestingCallId(null);
    }
  }

  async function handleDeleteCall(call: SourceCall) {
    const title =
      ownCandidateByCallId.get(call.id)?.conversationTitle ||
      call.conversationTitle ||
      `звонок ${call.statisticId}`;
    const confirmed = window.confirm(
      `Удалить «${title}» полностью из приложения?\n\n` +
        "Расшифровка, кандидат, решение и локальная история задачи будут удалены. " +
        "Уже созданная задача в Bitrix останется в Bitrix.",
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      await deleteCall(call.id);
      setOwnCalls((current) => current.filter((item) => item.id !== call.id));
      setOperatorCalls((current) =>
        current.filter((item) => item.id !== call.id),
      );
      setCandidates((current) =>
        current.filter((candidate) => candidate.callId !== call.id),
      );
      setOperatorCandidates((current) =>
        current.filter((candidate) => candidate.callId !== call.id),
      );
      setReviewCandidate((current) =>
        current?.callId === call.id ? null : current,
      );
      setTranscriptCall((current) => (current?.id === call.id ? null : current));
      setNotice("Запись удалена из приложения");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить запись");
    }
  }

  function handleDeleteCandidate(candidate: TaskCandidate) {
    void handleDeleteCall(candidate.call);
  }

  async function handleAnalyticsExport() {
    setExportingAnalytics(true);
    setError(null);
    try {
      const filename = await downloadComplaintsExcel();
      setNotice(`Файл выгружен · ${filename}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Не удалось выгрузить аналитику",
      );
    } finally {
      setExportingAnalytics(false);
    }
  }

  if (resolving) {
    return <main className="boot">Определяю пользователя…</main>;
  }

  if (!effectiveUser) {
    return (
      <main className="boot">
        {error ?? "Не удалось авторизоваться через Bitrix24"}
      </main>
    );
  }

  const hasLocalFilters =
    statusFilter !== "all" || departmentFilter !== "all" || normalizeText(searchQuery) !== "";
  const operatorEmptyMessage = hasLocalFilters
    ? "по выбранным фильтрам ничего нет"
    : "по вашим звонкам пока нет кандидатов";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <img src="/logo-main-D-coE2rl.webp" alt="KULIKOV" />
        </div>
        <div className="topbar-right">
          {emulationUsers.length > 0 && (
            <label className="user-emulation-select">
              <span>Смотреть от лица</span>
              <select
                value={effectiveUser.id}
                disabled={switchingUser}
                aria-label="Эмуляция пользователя Bitrix"
                onChange={(event) => handleEmulationUserChange(event.target.value)}
              >
                {emulationUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.displayName} · {user.role === "supervisor" ? "руководитель" : "оператор"}
                  </option>
                ))}
              </select>
            </label>
          )}
          {mockMode && (
            <div className="role-switch" role="group" aria-label="Демо-режим: роль">
              <button
                className={role === "operator" ? "is-active" : ""}
                type="button"
                onClick={() => setRoleOverride("operator")}
              >
                Оператор
              </button>
              <button
                className={role === "supervisor" ? "is-active" : ""}
                type="button"
                onClick={() => setRoleOverride("supervisor")}
              >
                Супервайзер
              </button>
            </div>
          )}
          <div className="user-badge" aria-label="Пользователь Bitrix24">
            <div className="user-avatar">
              {effectiveUser.avatarUrl ? (
                <img src={effectiveUser.avatarUrl} alt="" />
              ) : (
                effectiveUser.initials
              )}
            </div>
            <div>
              <strong>{effectiveUser.displayName}</strong>
              <span>
                {role === "supervisor" ? "Супервайзер" : "Оператор"}
                {effectiveUser.workPosition ? ` · ${effectiveUser.workPosition}` : ""}
              </span>
            </div>
          </div>
        </div>
      </header>

      <div className={sidebarCollapsed ? "layout is-sidebar-collapsed" : "layout"}>
        <nav className={sidebarCollapsed ? "sidebar is-collapsed" : "sidebar"} aria-label="Разделы">
          <button
            className="sidebar-toggle"
            type="button"
            title={sidebarCollapsed ? "Развернуть меню" : "Свернуть меню"}
            aria-label={sidebarCollapsed ? "Развернуть меню" : "Свернуть меню"}
            onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>

          {role === "operator" ? (
            <>
              <button
                className={
                  operatorView === "calls"
                    ? "nav-button is-active"
                    : "nav-button"
                }
                type="button"
                title="Мои звонки"
                onClick={() => setOperatorView("calls")}
              >
                <PhoneCall size={17} />
                <span className="nav-label">Мои звонки</span>
              </button>
              <button
                className={
                  operatorView === "tasks"
                    ? "nav-button is-active"
                    : "nav-button"
                }
                type="button"
                title="Решения по задачам"
                onClick={() => setOperatorView("tasks")}
              >
                <LayoutList size={17} />
                <span className="nav-label">Задачи</span>
              </button>
            </>
          ) : (
            <>
              <button
                className={
                  supervisorView === "operators"
                    ? "nav-button is-active"
                    : "nav-button"
                }
                type="button"
                title="Операторы"
                onClick={() => {
                  setSupervisorView("operators");
                  setSelectedOperator(null);
                }}
              >
                <LayoutDashboard size={17} />
                <span className="nav-label">Операторы</span>
              </button>
              <button
                className={
                  supervisorView === "analytics"
                    ? "nav-button is-active"
                    : "nav-button"
                }
                type="button"
                title="Аналитика"
                onClick={() => {
                  setSupervisorView("analytics");
                  setSelectedOperator(null);
                }}
              >
                <BarChart3 size={17} />
                <span className="nav-label">Аналитика</span>
              </button>
            </>
          )}
        </nav>

        <section className="content">
          {error && <div className="error-box">{error}</div>}
          {notice && <div className="toast-message">{notice}</div>}

          {role === "operator" ? operatorView === "calls" ? (
            <OwnCallsPanel
              calls={ownCalls}
              candidateByCallId={ownCandidateByCallId}
              loading={loadingOwnCalls}
              requestingCallId={requestingCallId}
              onOpenCall={setTranscriptCall}
              onOpenCandidate={setReviewCandidate}
              onRequestAnalysis={handleRequestCallAnalysis}
              onDelete={handleDeleteCall}
            />
          ) : (
            <>
              <section className="control-panel" aria-label="Управление кандидатами">
                <div className="toolbar">
                  <div>
                    <h2>Мои задачи из звонков</h2>
                    <p>
                      {loadingCandidates
                        ? "Загружаю из API…"
                        : `Найдено: ${visibleCandidates.length} · ждут: ${pendingCount} · упало: ${failedCount}`}
                    </p>
                  </div>
                  <div className="search-box">
                    <Search className="search-box-icon" size={18} aria-hidden="true" />
                    <input
                      type="search"
                      value={searchQuery}
                      placeholder="Задача, отдел, номер звонка, текст расшифровки"
                      aria-label="Поиск по кандидатам"
                      onChange={(event) => setSearchQuery(event.target.value)}
                    />
                  </div>
                </div>

                {filtersHidden ? (
                  <div className="filter-restore">
                    <button className="secondary" type="button" onClick={() => setFiltersHidden(false)}>
                      Показать фильтры
                    </button>
                  </div>
                ) : (
                  <CandidateFilters
                    departments={dictionaries?.departments ?? []}
                    status={statusFilter}
                    department={departmentFilter}
                    onStatusChange={setStatusFilter}
                    onDepartmentChange={setDepartmentFilter}
                    onHide={() => setFiltersHidden(true)}
                  />
                )}
              </section>

              <section className="promo-grid">
                {loadingCandidates ? (
                  <LoadingState />
                ) : visibleCandidates.length === 0 ? (
                  <EmptyState message={operatorEmptyMessage} />
                ) : (
                  visibleCandidates.map((candidate) => (
                    <CandidateCard
                      key={candidate.id}
                      candidate={candidate}
                      onOpen={setReviewCandidate}
                      onDelete={handleDeleteCandidate}
                    />
                  ))
                )}
              </section>
            </>
          ) : supervisorView === "analytics" ? (
            <AnalyticsDashboard
              analytics={complaintAnalytics}
              loading={loadingAnalytics}
              exporting={exportingAnalytics}
              onExport={handleAnalyticsExport}
            />
          ) : selectedOperator ? (
            <OperatorCallsPanel
              operator={selectedOperator}
              calls={operatorCalls}
              candidateByCallId={candidateByCallId}
              loading={loadingDetail}
              requestingCallId={requestingCallId}
              onBack={() => setSelectedOperator(null)}
              onOpenCall={setTranscriptCall}
              onRequestAnalysis={handleRequestCallAnalysis}
            />
          ) : (
            <>
              <section className="control-panel" aria-label="Панель операторов">
                <div className="toolbar">
                  <div>
                    <h2>Операторы</h2>
                    <p>
                      {loadingOperators
                        ? "Загружаю из API…"
                        : `Операторов: ${visibleOperators.length}`}
                    </p>
                  </div>
                  <div className="search-box">
                    <Search className="search-box-icon" size={18} aria-hidden="true" />
                    <input
                      type="search"
                      value={operatorQuery}
                      placeholder="Имя оператора или должность"
                      aria-label="Поиск по операторам"
                      onChange={(event) => setOperatorQuery(event.target.value)}
                    />
                  </div>
                </div>
              </section>

              {loadingOperators ? (
                <LoadingState />
              ) : visibleOperators.length === 0 ? (
                <EmptyState message="операторы не найдены" />
              ) : (
                <OperatorList operators={visibleOperators} onSelect={setSelectedOperator} />
              )}
            </>
          )}
        </section>
      </div>

      {reviewCandidate && role === "operator" && (
        <TaskReviewModal
          key={reviewCandidate.id}
          candidate={reviewCandidate}
          departments={dictionaries?.departments ?? []}
          busy={reviewBusy}
          onClose={() => setReviewCandidate(null)}
          onConfirm={handleConfirm}
          onRetry={handleRetry}
          onReject={handleReject}
          onDelete={() => handleDeleteCandidate(reviewCandidate)}
        />
      )}

      {transcriptCall && (
        <CallTranscriptModal
          call={transcriptCall}
          candidate={
            (role === "operator"
              ? ownCandidateByCallId.get(transcriptCall.id)
              : candidateByCallId.get(transcriptCall.id)) ?? null
          }
          onClose={() => setTranscriptCall(null)}
        />
      )}
    </main>
  );
}
