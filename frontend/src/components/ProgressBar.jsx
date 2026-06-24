import React from 'react';

export default function ProgressBar({ progressPct = 0, stage = 'Processing…' }) {
  const pct = Math.min(Math.max(Math.round(progressPct), 0), 100);

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-4">
        <span className="text-[var(--text-2)] text-[13px] font-medium truncate min-w-0">
          {stage}
        </span>
        <span className="text-[var(--text-1)] text-[12px] font-mono font-semibold shrink-0 tabular-nums">
          {pct}%
        </span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={stage}
      >
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
