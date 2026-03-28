'use client';

import clsx from 'clsx';

import type { JobStatus } from '@/types/jobs';

const stages = ['PENDING', 'RESEARCHING', 'AUDIO', 'VISUALS', 'COMPOSING', 'UPLOADING', 'COMPLETED'] as const;

const labels: Record<(typeof stages)[number], string> = {
  PENDING: 'Queued',
  RESEARCHING: 'Research',
  AUDIO: 'Narrate',
  VISUALS: 'Curate',
  COMPOSING: 'Assemble',
  UPLOADING: 'Publish',
  COMPLETED: 'Live'
};

const statusIndex: Record<JobStatus, number> = {
  PENDING: 0,
  RESEARCHING: 1,
  AUDIO: 2,
  VISUALS: 3,
  COMPOSING: 4,
  READY_TO_PUBLISH: 5,
  UPLOADING: 5,
  COMPLETED: 6,
  BLOCKED_BY_QUALITY_GATE: 5,
  FAILED: 4,
  CANCELLED: 0
};

export function PipelineVisualizer({ status }: { status: JobStatus }) {
  const activeIndex = statusIndex[status];
  const failureLike = status === 'FAILED' || status === 'CANCELLED';
  const blocked = status === 'BLOCKED_BY_QUALITY_GATE';

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-7 gap-2">
        {stages.map((stage, index) => {
          const complete = index < activeIndex;
          const current = index === activeIndex;
          return (
            <div key={stage} className="flex flex-col items-center gap-2 text-center">
              <div
                className={clsx(
                  'h-2.5 w-full rounded-full border transition-colors',
                  complete && 'border-aqua/40 bg-aqua',
                  current && !failureLike && !blocked && 'border-ember/50 bg-ember',
                  current && blocked && 'border-fuchsia-300/50 bg-fuchsia-300',
                  current && failureLike && 'border-rose/50 bg-rose',
                  !complete && !current && 'border-white/10 bg-white/5'
                )}
              />
              <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-mist/80">
                {labels[stage]}
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-mist/80">
        {blocked
          ? 'Quality gate blocked the upload and is waiting for human review.'
          : failureLike
            ? 'The pipeline halted before completion. Inspect the error trace for details.'
            : 'The pipeline advances automatically as each service finishes.'}
      </p>
    </div>
  );
}
