import type { JobStatus } from "@/lib/types";

const labels: Record<string, string> = {
  pending: "В очереди",
  running: "В работе",
  completed: "Готово",
  failed: "Ошибка",
  cancelled: "Остановлено",
  active: "Активен",
  paid: "Оплачен",
  pending_invoice: "Ожидает",
  new: "Новое",
  in_progress: "В работе",
  closed: "Закрыто",
};

export function StatusPill({ status }: { status: JobStatus | string }) {
  const normalized = status || "pending";
  return <span className={`status-pill status-${normalized}`}>{labels[normalized] || normalized}</span>;
}
