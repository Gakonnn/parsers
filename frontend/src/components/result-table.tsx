import { formatDate, truncateMiddle } from "@/lib/format";
import type { ParserResult } from "@/lib/types";
import { EmptyState } from "./empty-state";

function value(payload: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const item = payload[key];
    if (item !== undefined && item !== null && String(item).trim()) return String(item);
  }
  return "-";
}

export function ResultTable({ rows }: { rows: ParserResult[] }) {
  if (!rows.length) {
    return <EmptyState title="Данных пока нет" text="Когда парсер сохранит записи в PostgreSQL, они появятся в этой таблице." />;
  }

  return (
    <div className="table-card">
      <div className="data-table results-table">
        <div className="table-row table-head">
          <span>Источник</span>
          <span>Название</span>
          <span>Телефон</span>
          <span>Локация</span>
          <span>Дата</span>
        </div>
        {rows.map((row) => (
          <div className="table-row" key={`${row.run_id}-${row.id}`}>
            <span className="source-cell">{row.source}</span>
            <span>{value(row.payload, ["title", "name", "description"])}</span>
            <span className="mono">{value(row.payload, ["seller_phone", "phones", "phone_1", "phone"] )}</span>
            <span>{value(row.payload, ["location", "city", "address", "region"])}</span>
            <span>{formatDate(row.created_at)}</span>
          </div>
        ))}
      </div>
      <div className="table-footnote">Показаны последние записи. ID запуска: {truncateMiddle(rows[0]?.run_id || "")}</div>
    </div>
  );
}
