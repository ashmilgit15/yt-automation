'use client';

import Link from 'next/link';
import { CopyPlus, ExternalLink, Globe2, PencilLine, RotateCcw, ShieldAlert, Trash2, TriangleAlert, WandSparkles, UploadCloud } from 'lucide-react';

import { PipelineVisualizer } from '@/components/PipelineVisualizer';
import { StatusBadge } from '@/components/StatusBadge';
import type { VideoJobSummary } from '@/types/jobs';

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  }).format(new Date(value));
}

interface JobGridProps {
  jobs: VideoJobSummary[];
  detailed?: boolean;
  onReview: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onDuplicate: (jobId: string) => void;
  onMakePublic: (jobId: string) => void;
  onResumeFromStage: (jobId: string) => void;
  onRegenerateMetadata: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onPublish: (jobId: string) => void;
  selectedJobIds?: Set<string>;
  onSelectJob?: (jobId: string, selected: boolean) => void;
  busyActionKey?: string | null;
}

export function JobGrid({ jobs, detailed = false, onReview, onRetry, onDuplicate, onMakePublic, onResumeFromStage, onRegenerateMetadata, onDelete, onPublish, selectedJobIds, onSelectJob, busyActionKey }: JobGridProps) {
  return (
    <div className={detailed ? 'space-y-4' : 'grid gap-4 xl:grid-cols-2'}>
      {jobs.map((job) => (
        <article
          key={job.id}
          id={job.id}
          className={`content-visibility-auto scroll-mt-28 overflow-hidden rounded-[30px] border ${selectedJobIds?.has(job.id) ? 'border-aqua shadow-[0_0_15px_rgba(74,215,209,0.3)]' : 'border-white/10'} bg-white/5 p-5 shadow-panel backdrop-blur transition hover:border-aqua/20`}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-4">
              {onSelectJob && job.status === 'READY_TO_PUBLISH' && (
                <input 
                  type="checkbox" 
                  checked={selectedJobIds?.has(job.id) || false}
                  onChange={(e) => onSelectJob(job.id, e.target.checked)}
                  className="mt-1.5 w-5 h-5 rounded border-white/20 bg-white/5 text-aqua focus:ring-aqua focus:ring-offset-slate cursor-pointer"
                />
              )}
              <div className="min-w-0 space-y-2">
                <p className="text-xs uppercase tracking-[0.22em] text-mist/70">{formatDate(job.created_at)}</p>
                <h3 className="balanced-heading max-w-2xl text-xl font-semibold text-white">{job.title ?? job.topic}</h3>
                <p className="text-sm text-mist">
                  {job.target_audience ? `${job.target_audience} · ` : ''}
                  {job.duration_seconds}s · {job.distribution_label} · {job.publish_privacy}
                </p>
                {job.batch_label ? (
                  <p className="text-xs uppercase tracking-[0.18em] text-amber-100/80">
                    Batch: {job.batch_label}{job.batch_index ? ` · #${job.batch_index}` : ''}
                  </p>
                ) : null}
              </div>
            </div>
            <StatusBadge status={job.status} />
          </div>

          <div className="mt-6">
            <PipelineVisualizer status={job.status} />
          </div>

          <div className="mt-6 grid gap-3 text-sm text-mist md:grid-cols-3">
            <div className="rounded-[24px] border border-white/10 bg-slate/60 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-mist/70">Pipeline</p>
              <p className="mt-2 text-white">{job.scene_count} scenes planned</p>
              <p className="mt-1 text-xs text-mist/80">{job.visual_asset_count} curated clips attached so far</p>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-slate/60 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-mist/70">Quality Gate</p>
              <p className="mt-2 text-white">Score: {job.quality_score ?? 'pending'}</p>
              <p className="mt-1 line-clamp-4 text-xs text-mist/80">{job.critique_text ?? 'The policy auditor has not reported back yet.'}</p>
            </div>
            <div className="rounded-[24px] border border-white/10 bg-slate/60 p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-mist/70">Reliability</p>
              <p className="mt-2 text-white">{job.status === 'FAILED' ? 'Needs attention' : 'Stable'}</p>
              <p className="mt-1 line-clamp-4 text-xs text-mist/80">{job.error_summary ?? 'No operator-facing issue summary has been recorded.'}</p>
            </div>
          </div>

          {job.status === 'BLOCKED_BY_QUALITY_GATE' ? (
            <button
              type="button"
              onClick={() => onReview(job.id)}
              className="mt-5 inline-flex items-center gap-2 rounded-3xl border border-fuchsia-300/30 bg-fuchsia-300/10 px-4 py-3 text-sm font-semibold text-fuchsia-100 transition hover:bg-fuchsia-300/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-300/50"
            >
              <ShieldAlert aria-hidden="true" className="h-4 w-4" />
              Review & Override
            </button>
          ) : null}

          {job.status === 'FAILED' && job.error_summary ? (
            <div className="mt-5 rounded-[24px] border border-rose/20 bg-rose/10 p-4 text-sm text-rose-100">
              <div className="flex items-center gap-2 font-semibold">
                <TriangleAlert aria-hidden="true" className="h-4 w-4" />
                Failure summary
              </div>
              <p className="mt-2 text-xs leading-6 text-rose-50/90">{job.error_summary}</p>
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap items-center gap-3 text-sm">
            {job.status === 'READY_TO_PUBLISH' ? (
              <button
                type="button"
                onClick={() => onPublish(job.id)}
                disabled={busyActionKey === `publish:${job.id}`}
                className="inline-flex items-center gap-2 rounded-full border border-aqua/30 bg-aqua/10 px-4 py-2 text-white font-bold transition hover:bg-aqua/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40 disabled:opacity-60"
              >
                <UploadCloud aria-hidden="true" className="h-4 w-4" />
                {busyActionKey === `publish:${job.id}` ? 'Publishing…' : 'Publish to YouTube'}
              </button>
            ) : null}
            {(job.status === 'FAILED' || job.status === 'CANCELLED') ? (
              <button
                type="button"
                onClick={() => onRetry(job.id)}
                disabled={busyActionKey === `retry:${job.id}`}
                className="inline-flex items-center gap-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-amber-50 transition hover:bg-amber-300/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/40 disabled:opacity-60"
              >
                <RotateCcw aria-hidden="true" className="h-4 w-4" />
                {busyActionKey === `retry:${job.id}` ? 'Retrying…' : 'Retry Job'}
              </button>
            ) : null}
            {job.status === 'FAILED' ? (
              <button
                type="button"
                onClick={() => onResumeFromStage(job.id)}
                disabled={busyActionKey === `resume:${job.id}`}
                className="inline-flex items-center gap-2 rounded-full border border-sky-300/25 bg-sky-300/10 px-3 py-2 text-sky-100 transition hover:bg-sky-300/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/40 disabled:opacity-60"
              >
                <WandSparkles aria-hidden="true" className="h-4 w-4" />
                {busyActionKey === `resume:${job.id}` ? 'Resuming…' : 'Resume Stage'}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => onDuplicate(job.id)}
              disabled={busyActionKey === `duplicate:${job.id}`}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-white transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40 disabled:opacity-60"
            >
              <CopyPlus aria-hidden="true" className="h-4 w-4" />
              {busyActionKey === `duplicate:${job.id}` ? 'Duplicating…' : 'Duplicate'}
            </button>
            {job.youtube_url && job.publish_privacy !== 'public' ? (
              <button
                type="button"
                onClick={() => onMakePublic(job.id)}
                disabled={busyActionKey === `public:${job.id}`}
                className="inline-flex items-center gap-2 rounded-full border border-lime/30 bg-lime/10 px-3 py-2 text-lime-100 transition hover:bg-lime/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30 disabled:opacity-60"
              >
                <Globe2 aria-hidden="true" className="h-4 w-4" />
                {busyActionKey === `public:${job.id}` ? 'Publishing…' : 'Make Public'}
              </button>
            ) : null}
            {job.scene_count > 0 ? (
              <button
                type="button"
                onClick={() => onRegenerateMetadata(job.id)}
                disabled={busyActionKey === `metadata:${job.id}`}
                className="inline-flex items-center gap-2 rounded-full border border-fuchsia-300/25 bg-fuchsia-300/10 px-3 py-2 text-fuchsia-100 transition hover:bg-fuchsia-300/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-300/40 disabled:opacity-60"
              >
                <PencilLine aria-hidden="true" className="h-4 w-4" />
                {busyActionKey === `metadata:${job.id}` ? 'Refreshing…' : 'Refresh Metadata'}
              </button>
            ) : null}
            {['COMPLETED', 'FAILED', 'CANCELLED', 'BLOCKED_BY_QUALITY_GATE'].includes(job.status) ? (
              <button
                type="button"
                onClick={() => onDelete(job.id)}
                disabled={busyActionKey === `delete:${job.id}`}
                className="inline-flex items-center gap-2 rounded-full border border-rose/25 bg-rose/10 px-3 py-2 text-rose-100 transition hover:bg-rose/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose/30 disabled:opacity-60"
              >
                <Trash2 aria-hidden="true" className="h-4 w-4" />
                {busyActionKey === `delete:${job.id}` ? 'Deleting…' : 'Delete'}
              </button>
            ) : null}
            <Link
              href={`/jobs#${job.id}`}
              className="rounded-full border border-white/10 px-3 py-2 text-mist transition hover:border-aqua/30 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
            >
              Inspect Job
            </Link>
            {job.youtube_url ? (
              <a
                href={job.youtube_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-full border border-lime/30 bg-lime/10 px-3 py-2 text-lime-100 transition hover:bg-lime/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30"
              >
                <ExternalLink aria-hidden="true" className="h-4 w-4" />
                View Upload
              </a>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
