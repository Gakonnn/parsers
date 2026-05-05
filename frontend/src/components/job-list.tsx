import Link from "next/link";

import { formatDate, percent, truncateMiddle } from "@/lib/format";
import type { ParserJob } from "@/lib/types";
import { EmptyState } from "./empty-state";
import { StatusPill } from "./status-pill";

export function JobList({ jobs, compact = false }: { jobs: ParserJob[]; compact?: boolean }) {
  if (!jobs.length) {
    return <EmptyState title="Пока нет задач" text="Запустите первый парсер, и здесь появится история выполнения." />;
  }

  return (
    <div className="table-card">
      <div className="data-table jobs-table">
        <div className="table-row table-head">
          <span>Источник</span>
          <span>Статус</span>
          <span>Прогресс</span>
          <span>Запуск</span>
          {!compact ? <span>ID</span> : null}
        </div>
        {jobs.map((job) => {
          const value = percent(job.progress_current, job.progress_total);
          return (
            <Link className="table-row clickable-row" href={`/jobs/${job.id}`} key={job.id}>
              <span className="source-cell">{job.source}</span>
              <span><StatusPill status={job.status} /></span>
              <span>
                <div className="inline-progress">
                  <i style={{ width: `${value}%` }} />
                </div>
                <small>{job.progress_current}/{job.progress_total || "?"}</small>
              </span>
              <span>{formatDate(job.created_at)}</span>
              {!compact ? <span className="mono">{truncateMiddle(job.id)}</span> : null}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
