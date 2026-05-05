import type { CSSProperties } from "react";

export function ProgressRing({ value, label }: { value: number; label?: string }) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <div className="progress-ring" style={{ "--progress": `${safe * 3.6}deg` } as CSSProperties}>
      <div>
        <strong>{safe}%</strong>
        <span>{label || "progress"}</span>
      </div>
    </div>
  );
}
