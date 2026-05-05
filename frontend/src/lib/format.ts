export function formatDate(value?: string | null): string {
  if (!value) return "-";
  try {
    return new Intl.DateTimeFormat("ru-KZ", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function formatMoney(value: number, currency = "KZT"): string {
  return new Intl.NumberFormat("ru-KZ", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value || 0);
}

export function percent(current: number, total: number): number {
  if (!total || total <= 0) return current > 0 ? 12 : 0;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

export function truncateMiddle(value: string, size = 8): string {
  if (!value || value.length <= size * 2 + 3) return value;
  return `${value.slice(0, size)}...${value.slice(-size)}`;
}
