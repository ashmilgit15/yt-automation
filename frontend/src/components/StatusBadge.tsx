'use client';

import clsx from 'clsx';

import type { JobStatus } from '@/types/jobs';

const toneMap: Record<JobStatus, string> = {
  PENDING: 'border-white/10 bg-white/5 text-slate-200',
  RESEARCHING: 'border-cyan-400/20 bg-cyan-400/10 text-cyan-100',
  AUDIO: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-100',
  VISUALS: 'border-sky-400/20 bg-sky-400/10 text-sky-100',
  COMPOSING: 'border-amber-400/20 bg-amber-400/10 text-amber-100',
  READY_TO_PUBLISH: 'border-indigo-400/20 bg-indigo-400/10 text-indigo-100',
  UPLOADING: 'border-orange-400/20 bg-orange-400/10 text-orange-100',
  COMPLETED: 'border-lime-300/20 bg-lime-300/10 text-lime-100',
  FAILED: 'border-red-400/20 bg-red-400/10 text-red-100',
  BLOCKED_BY_QUALITY_GATE: 'border-fuchsia-300/20 bg-fuchsia-300/10 text-fuchsia-100',
  CANCELLED: 'border-white/10 bg-white/5 text-slate-400'
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={clsx(
        'inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.22em]',
        toneMap[status]
      )}
    >
      {status.replace(/_/g, ' ')}
    </span>
  );
}
