import type {
  CandidateStatus,
  ComplaintBasis,
  Priority,
  TaskType,
} from "../types/domain";

export const TASK_NAME_MAX_LENGTH = 160;
export const TASK_DESCRIPTION_MAX_LENGTH = 2000;
export const REJECTION_REASON_MAX_LENGTH = 400;

export const PRIORITIES: Priority[] = [1, 2, 3, 4, 5];

export const PRIORITY_LABEL: Record<Priority, string> = {
  1: "Низкий",
  2: "Ниже средн.",
  3: "Средний",
  4: "Высокий",
  5: "Срочный",
};

/** Maps a priority to a status-pill modifier (see styles.css). */
export const PRIORITY_TONE: Record<Priority, "low" | "mid" | "high" | "urgent"> = {
  1: "low",
  2: "low",
  3: "mid",
  4: "high",
  5: "urgent",
};

export const STATUS_LABEL: Record<CandidateStatus, string> = {
  pending: "Ждёт решения",
  confirmed: "Задача создана",
  rejected: "Отклонена",
  failed: "Упала",
};

/** CSS modifier appended to `.status` for each candidate status. */
export const STATUS_TONE: Record<CandidateStatus, string> = {
  pending: "soon",
  confirmed: "active",
  rejected: "archive",
  failed: "trash",
};

export const TASK_TYPE_LABEL: Record<TaskType, string> = {
  legacy: "Ранее созданная",
  service_fm: "Сервис ФМ/ФМК",
  bar_food: "Бар/еда",
  product_quality_food_safety: "Качество/пищевая безопасность",
  semi_finished_products: "Полуфабрикаты",
  ice_cream: "Мороженое",
  camera_recording: "Записи с камер",
  receipt_search: "Поиск чека",
  mobile_app_error: "Ошибка МП",
  mobile_app_wrong_information: "Неверная информация в МП",
  payment_check: "Проверка платежа",
  operator_quality_violation: "Качество оператора",
  none: "Задача не требуется",
};

export const COMPLAINT_BASIS_LABEL: Record<ComplaintBasis, string> = {
  legacy: "Старое правило",
  explicit_complaint: "Явная жалоба клиента",
  explicit_negative_feedback: "Негативная обратная связь",
  none: "Жалобы нет",
};
