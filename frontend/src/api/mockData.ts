// In-memory dataset for standalone development (no backend running).
// The typed API client (tasksApi.ts) falls back to this so the UI is fully
// interactive on its own — the same idea as the reference app's fallbackUser.
//
// Timestamps are anchored near 2026-07-23 to look realistic in demos.

import type {
  Department,
  SessionUser,
  SourceCall,
  TaskCandidate,
} from "../types/domain";
import { initialsFromName } from "../utils/format";

export const mockDepartments: Department[] = [
  { id: 10, name: "Продажи" },
  { id: 11, name: "Поддержка" },
  { id: 12, name: "Логистика" },
  { id: 13, name: "Бухгалтерия" },
];

type MockOperator = {
  id: string;
  displayName: string;
  workPosition: string;
  departmentIds: number[];
};

export const mockOperators: MockOperator[] = [
  { id: "7", displayName: "Иван Петров", workPosition: "Менеджер по продажам", departmentIds: [10] },
  { id: "12", displayName: "Айгуль Осмонова", workPosition: "Специалист поддержки", departmentIds: [11] },
  { id: "15", displayName: "Данияр Ким", workPosition: "Менеджер по продажам", departmentIds: [10] },
  { id: "19", displayName: "Мээрим Асанова", workPosition: "Оператор логистики", departmentIds: [12] },
];

/** The signed-in user when running standalone. Swap role from the header. */
export const mockOperatorUser: SessionUser = {
  id: "7",
  displayName: "Иван Петров",
  workPosition: "Менеджер по продажам",
  initials: "ИП",
  avatarUrl: "",
  role: "operator",
  departmentIds: [10],
  source: "local",
};

export const mockSupervisorUser: SessionUser = {
  id: "3",
  displayName: "Ирина Смирнова",
  workPosition: "Руководитель поддержки",
  initials: "ИС",
  avatarUrl: "",
  role: "supervisor",
  departmentIds: [11],
  source: "local",
};

function call(
  partial: Omit<
    SourceCall,
    | "operatorName"
    | "conversationTitle"
    | "analysisStatus"
    | "analysisRequested"
    | "analysisError"
  >,
): SourceCall {
  const operator = mockOperators.find((item) => item.id === partial.operatorId);
  return {
    ...partial,
    operatorName: operator?.displayName ?? "Оператор",
    conversationTitle: "",
    analysisStatus: partial.transcript ? "completed" : "pending",
    analysisRequested: false,
    analysisError: null,
  };
}

const calls: SourceCall[] = [
  call({
    id: "call.5001",
    statisticId: 5001,
    operatorId: "7",
    direction: "inbound",
    durationSeconds: 245,
    startedAt: "2026-07-23T09:12:00+06:00",
    phoneMasked: "+996 XXX XX 45 09",
    failedCode: null,
    transcript:
      "Оператор: Здравствуйте, компания KULIKOV, меня зовут Иван. Клиент: Добрый день. Я на прошлой неделе оставлял заявку на кухонный гарнитур, хотел уточнить сроки. Оператор: Секунду, посмотрю по вашему заказу. Клиент: И ещё — пришлите, пожалуйста, актуальный счёт на почту, у меня старый с прошлой ценой. Оператор: Хорошо, подготовлю новый счёт и отправлю сегодня до конца дня. Клиент: Отлично, жду. Спасибо.",
  }),
  call({
    id: "call.5002",
    statisticId: 5002,
    operatorId: "7",
    direction: "outbound",
    durationSeconds: 128,
    startedAt: "2026-07-23T10:40:00+06:00",
    phoneMasked: "+996 XXX XX 88 21",
    failedCode: null,
    transcript:
      "Оператор: Добрый день, это Иван из KULIKOV, вам удобно говорить? Клиент: Да, конечно. Оператор: Звоню подтвердить доставку на четверг. Клиент: Да, всё в силе, но перенесите, пожалуйста, на первую половину дня. Оператор: Принято, поставлю доставку на утро четверга и предупрежу логистов.",
  }),
  call({
    id: "call.5003",
    statisticId: 5003,
    operatorId: "7",
    direction: "inbound",
    durationSeconds: 52,
    startedAt: "2026-07-22T16:05:00+06:00",
    phoneMasked: "+996 XXX XX 10 77",
    failedCode: null,
    transcript:
      "Оператор: KULIKOV, здравствуйте. Клиент: Здравствуйте, а вы работаете в выходные? Оператор: Да, в субботу с 10 до 16. Клиент: Понял, спасибо, тогда заеду в субботу. Оператор: Будем ждать, хорошего дня.",
  }),
  call({
    id: "call.5010",
    statisticId: 5010,
    operatorId: "12",
    direction: "inbound",
    durationSeconds: 312,
    startedAt: "2026-07-23T08:55:00+06:00",
    phoneMasked: "+996 XXX XX 34 12",
    failedCode: null,
    transcript:
      "Клиент: Здравствуйте, у меня перестал работать доводчик на дверце шкафа, гарантия ещё действует. Оператор: Добрый день, оформлю заявку в сервис. Подскажите номер заказа и адрес. Клиент: Заказ 44120, адрес — Бишкек, Чуй 155. Оператор: Записала. Мастер приедет в течение двух рабочих дней, я поставлю задачу на сервисный отдел.",
  }),
  call({
    id: "call.5011",
    statisticId: 5011,
    operatorId: "12",
    direction: "outbound",
    durationSeconds: 96,
    startedAt: "2026-07-22T14:20:00+06:00",
    phoneMasked: "+996 XXX XX 60 03",
    failedCode: null,
    transcript:
      "Оператор: Добрый день, это Айгуль из сервиса KULIKOV. Ваш мастер выехал, будет через 40 минут. Клиент: Спасибо, что предупредили. Оператор: Хорошего дня.",
  }),
  call({
    id: "call.5020",
    statisticId: 5020,
    operatorId: "15",
    direction: "inbound",
    durationSeconds: 201,
    startedAt: "2026-07-23T11:15:00+06:00",
    phoneMasked: "+996 XXX XX 77 45",
    failedCode: null,
    transcript:
      "Клиент: Здравствуйте, хочу оформить рассрочку на диван, который смотрел в шоуруме. Оператор: Добрый день, подберём рассрочку. Нужно подготовить договор и согласовать первый взнос. Клиент: Давайте на 6 месяцев. Оператор: Хорошо, подготовлю договор рассрочки на 6 месяцев и перезвоню завтра.",
  }),
  call({
    id: "call.5021",
    statisticId: 5021,
    operatorId: "15",
    direction: "inbound",
    durationSeconds: 40,
    startedAt: "2026-07-21T13:00:00+06:00",
    phoneMasked: "+996 XXX XX 09 88",
    failedCode: "603",
    transcript:
      "Короткий звонок, клиент ошибся номером. Задача не требуется.",
  }),
  call({
    id: "call.5030",
    statisticId: 5030,
    operatorId: "19",
    direction: "outbound",
    durationSeconds: 150,
    startedAt: "2026-07-23T12:05:00+06:00",
    phoneMasked: "+996 XXX XX 51 30",
    failedCode: null,
    transcript:
      "Оператор: Добрый день, это логистика KULIKOV. Уточняю адрес доставки на завтра. Клиент: Да, адрес прежний, но добавьте, пожалуйста, подъём на 4 этаж без лифта. Оператор: Отмечу подъём на 4 этаж и пересчитаю стоимость доставки.",
  }),
];

function iso(input: string): string {
  return new Date(input).toISOString();
}

/**
 * Candidates across every status so both experiences render fully:
 *   - Иван (op 7): a pending, a failed ("упавшая"), a confirmed, a should_create=false
 *   - Айгуль (op 12): a pending, a confirmed
 *   - Данияр (op 15): a failed, plus a rejected short call
 *   - Мээрим (op 19): a pending
 */
const mockCandidateSeeds: Array<
  Omit<
    TaskCandidate,
    | "conversationTitle"
    | "taskType"
    | "qualityCriterion"
    | "complaintBasis"
    | "complaintEvidence"
    | "isConcreteComplaint"
    | "complaintSubject"
    | "complaintIssue"
  >
> = [
  {
    id: "cand-5001",
    callId: "call.5001",
    call: calls[0],
    operatorId: "7",
    operatorName: "Иван Петров",
    shouldCreate: true,
    taskName: "Выставить новый счёт по заказу на кухонный гарнитур",
    taskDescription:
      "Клиент просит актуальный счёт взамен старого (изменилась цена). Подготовить и отправить на почту сегодня до конца дня.",
    department: "Продажи",
    priority: 4,
    status: "pending",
    bitrixTaskId: null,
    failureReason: null,
    rejectionReason: null,
    createdAt: iso("2026-07-23T09:16:00+06:00"),
    updatedAt: iso("2026-07-23T09:16:00+06:00"),
  },
  {
    id: "cand-5002",
    callId: "call.5002",
    call: calls[1],
    operatorId: "7",
    operatorName: "Иван Петров",
    shouldCreate: true,
    taskName: "Перенести доставку на утро четверга",
    taskDescription:
      "Клиент подтвердил доставку в четверг, но просит первую половину дня. Согласовать с логистикой утренний слот.",
    department: "Логистика",
    priority: 3,
    status: "failed",
    bitrixTaskId: null,
    failureReason: "Bitrix API error ERROR_CORE: поле assignedById не найдено на портале",
    rejectionReason: null,
    createdAt: iso("2026-07-23T10:43:00+06:00"),
    updatedAt: iso("2026-07-23T10:45:00+06:00"),
  },
  {
    id: "cand-5003",
    callId: "call.5003",
    call: calls[2],
    operatorId: "7",
    operatorName: "Иван Петров",
    shouldCreate: false,
    taskName: "",
    taskDescription: "",
    department: null,
    priority: 1,
    status: "pending",
    bitrixTaskId: null,
    failureReason: null,
    rejectionReason: null,
    createdAt: iso("2026-07-22T16:06:00+06:00"),
    updatedAt: iso("2026-07-22T16:06:00+06:00"),
  },
  {
    id: "cand-5010",
    callId: "call.5010",
    call: calls[3],
    operatorId: "12",
    operatorName: "Айгуль Осмонова",
    shouldCreate: true,
    taskName: "Оформить сервисную заявку на ремонт доводчика",
    taskDescription:
      "Гарантийный случай по заказу 44120 (Бишкек, Чуй 155). Назначить мастера в течение двух рабочих дней.",
    department: "Поддержка",
    priority: 4,
    status: "pending",
    bitrixTaskId: null,
    failureReason: null,
    rejectionReason: null,
    createdAt: iso("2026-07-23T09:01:00+06:00"),
    updatedAt: iso("2026-07-23T09:01:00+06:00"),
  },
  {
    id: "cand-5011",
    callId: "call.5011",
    call: calls[4],
    operatorId: "12",
    operatorName: "Айгуль Осмонова",
    shouldCreate: true,
    taskName: "Подтвердить выезд мастера клиенту",
    taskDescription: "Проинформировать клиента о выезде мастера. Выполнено в звонке, задача для истории.",
    department: "Поддержка",
    priority: 2,
    status: "confirmed",
    bitrixTaskId: "T-88190",
    failureReason: null,
    rejectionReason: null,
    createdAt: iso("2026-07-22T14:22:00+06:00"),
    updatedAt: iso("2026-07-22T14:25:00+06:00"),
  },
  {
    id: "cand-5020",
    callId: "call.5020",
    call: calls[5],
    operatorId: "15",
    operatorName: "Данияр Ким",
    shouldCreate: true,
    taskName: "Подготовить договор рассрочки на 6 месяцев",
    taskDescription:
      "Клиент оформляет рассрочку на диван из шоурума на 6 месяцев. Подготовить договор, согласовать первый взнос, перезвонить завтра.",
    department: "Продажи",
    priority: 5,
    status: "failed",
    bitrixTaskId: null,
    failureReason: "Таймаут запроса к Bitrix при создании задачи",
    rejectionReason: null,
    createdAt: iso("2026-07-23T11:19:00+06:00"),
    updatedAt: iso("2026-07-23T11:20:00+06:00"),
  },
  {
    id: "cand-5021",
    callId: "call.5021",
    call: calls[6],
    operatorId: "15",
    operatorName: "Данияр Ким",
    shouldCreate: false,
    taskName: "",
    taskDescription: "",
    department: null,
    priority: 1,
    status: "rejected",
    bitrixTaskId: null,
    failureReason: null,
    rejectionReason: "Ошиблись номером, задача не нужна",
    createdAt: iso("2026-07-21T13:01:00+06:00"),
    updatedAt: iso("2026-07-21T13:02:00+06:00"),
  },
  {
    id: "cand-5030",
    callId: "call.5030",
    call: calls[7],
    operatorId: "19",
    operatorName: "Мээрим Асанова",
    shouldCreate: true,
    taskName: "Добавить подъём на 4 этаж и пересчитать доставку",
    taskDescription:
      "Клиент просит учесть подъём на 4 этаж без лифта. Обновить параметры доставки на завтра и пересчитать стоимость.",
    department: "Логистика",
    priority: 3,
    status: "pending",
    bitrixTaskId: null,
    failureReason: null,
    rejectionReason: null,
    createdAt: iso("2026-07-23T12:08:00+06:00"),
    updatedAt: iso("2026-07-23T12:08:00+06:00"),
  },
];

export const mockCandidates: TaskCandidate[] = mockCandidateSeeds.map(
  (candidate) => ({
    ...candidate,
    conversationTitle:
      candidate.taskName || "Информационный разговор с клиентом",
    taskType: candidate.shouldCreate ? "legacy" : "none",
    qualityCriterion: null,
    complaintBasis: candidate.shouldCreate ? "explicit_complaint" : "none",
    complaintEvidence: candidate.shouldCreate
      ? "Клиент явно сообщил о жалобе."
      : "",
    isConcreteComplaint: candidate.shouldCreate,
    complaintSubject: candidate.shouldCreate ? candidate.taskName : "",
    complaintIssue: candidate.shouldCreate ? candidate.taskDescription : "",
  }),
);

export const mockCalls = calls;

export function mockInitials(name: string): string {
  return initialsFromName(name);
}
