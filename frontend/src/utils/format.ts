import type { CallDirection } from "../types/domain";

/** "4:05", "0:45", "1:02:30" */
export function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;

  const mm = hours > 0 ? String(minutes).padStart(2, "0") : String(minutes);
  const ss = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${ss}` : `${mm}:${ss}`;
}

export function directionLabel(direction: CallDirection): string {
  return direction === "inbound" ? "Входящий" : "Исходящий";
}

/** First letters of the first two name parts, e.g. "Иван Петров" -> "ИП". */
export function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "?";
  }
  const letters = parts.slice(0, 2).map((part) => part[0]?.toLocaleUpperCase("ru-RU") ?? "");
  return letters.join("") || "?";
}

/** Case/ё-insensitive text for local search and sort. */
export function normalizeText(value: string): string {
  return value
    .toLocaleLowerCase("ru-RU")
    .replace(/ё/g, "е")
    .replace(/\s+/g, " ")
    .trim();
}

export function pluralizeRu(count: number, forms: [string, string, string]): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return forms[0];
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) {
    return forms[1];
  }
  return forms[2];
}
