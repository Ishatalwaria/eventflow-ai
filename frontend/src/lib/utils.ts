import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value: string | null | undefined, options: Intl.DateTimeFormatOptions = {}) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", ...options }).format(date);
}

export function compactId(value: string, size = 8) {
  return value.length > size ? `${value.slice(0, size)}…` : value;
}

export function formatDuration(value: number | null) {
  if (value === null || value === undefined) return "—";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s`;
}

export function formatMoney(minorUnits: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(minorUnits / 100);
}

export function sanitizeDiagnosticText(value: string) {
  return value
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, " ")
    .replace(/\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[:=]\s*[^\s,;]+/gi, "$1=[REDACTED]")
    .replace(/\bBearer\s+[A-Za-z0-9._~+/-]+=*/gi, "Bearer [REDACTED]")
    .replace(/(authorization\s*[:=]\s*)[^,;]+/gi, "$1[REDACTED]")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[REDACTED_EMAIL]")
    .replace(/(?<!\w)\+?\d[\d .()/-]{7,}\d(?!\w)/g, "[REDACTED_PHONE]")
    .replace(/\s+/g, " ")
    .slice(0, 300);
}
