export function inputDateFromDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function inputDateFromValue(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : inputDateFromDate(date);
}

export function todayInputValue(): string {
  return inputDateFromDate(new Date());
}

export function plusDaysInputValue(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return inputDateFromDate(date);
}

/** "23.07.2026" */
export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

/** "23 июля 2026, 10:00" */
export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
