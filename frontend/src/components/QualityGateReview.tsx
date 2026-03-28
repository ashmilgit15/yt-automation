'use client';

import type { ChangeEvent } from 'react';
import { useEffect, useMemo, useRef, useState, useTransition } from 'react';
import Image from 'next/image';
import { LoaderCircle, ShieldCheck, ShieldX, X } from 'lucide-react';

import { reviewJob } from '@/lib/api';
import type { VideoJobDetail } from '@/types/jobs';

interface QualityGateReviewProps {
  job: VideoJobDetail | null;
  isLoading?: boolean;
  onClose: () => void;
  onResolved: () => void;
}

export function QualityGateReview({ job, isLoading = false, onClose, onResolved }: QualityGateReviewProps) {
  const [notes, setNotes] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  const concerns = useMemo(() => {
    const raw = job?.critique_json?.concerns;
    return Array.isArray(raw) ? raw.map((item) => String(item)) : [];
  }, [job]);

  useEffect(() => {
    if (!job && !isLoading) {
      return;
    }

    previousActiveElementRef.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const timer = window.setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 40);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousActiveElementRef.current?.focus();
    };
  }, [isLoading, job, onClose]);

  if (!job && !isLoading) {
    return null;
  }

  const decide = (approved: boolean) => {
    if (!job) {
      return;
    }

    setFeedback(null);
    startTransition(async () => {
      try {
        await reviewJob(job.id, approved, notes);
        setFeedback(approved ? 'Upload override submitted.' : 'Job terminated.');
        onResolved();
        onClose();
      } catch (error) {
        const fallback = error instanceof Error ? error.message : 'Unable to submit review decision.';
        setFeedback(fallback);
      }
    });
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink/80 px-4 py-8 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="quality-gate-title"
        aria-describedby="quality-gate-description"
        className="mx-auto grid max-w-6xl gap-6 overflow-hidden rounded-[36px] border border-white/10 bg-[#08121d] shadow-panel lg:grid-cols-[1.2fr_0.8fr]"
      >
        <section className="space-y-6 p-6 lg:p-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-rose">Quality Gate Review</p>
              <h3 id="quality-gate-title" className="balanced-heading mt-3 text-2xl font-semibold text-white">
                {isLoading ? 'Loading Review…' : job?.title ?? job?.topic}
              </h3>
              <p id="quality-gate-description" className="mt-2 text-sm text-mist">
                The Gemini policy auditor flagged this upload. Review the draft before allowing the publish worker to resume.
              </p>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              aria-label="Close quality gate review"
              onClick={onClose}
              className="rounded-2xl border border-white/10 bg-white/5 p-2 text-white/70 transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
            >
              <X aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>

          {isLoading ? (
            <div className="rounded-[28px] border border-white/10 bg-white/5 p-6 text-sm text-mist">Loading the blocked job details…</div>
          ) : (
            <>
              <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
                <p className="text-xs uppercase tracking-[0.22em] text-mist/80">AI Critique</p>
                <p className="mt-3 text-sm leading-7 text-white/90">{job?.critique_text ?? 'No critique text was stored for this job.'}</p>
                {concerns.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {concerns.map((concern) => (
                      <span key={concern} className="rounded-full border border-rose/20 bg-rose/10 px-3 py-1 text-xs text-rose-100">
                        {concern}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
                <p className="text-xs uppercase tracking-[0.22em] text-mist/80">Script Draft</p>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-white/90">{job?.script_text ?? 'Script unavailable.'}</p>
              </div>

              <div className="rounded-[28px] border border-white/10 bg-white/5 p-5">
                <p className="text-xs uppercase tracking-[0.22em] text-mist/80">Operator Notes</p>
                <textarea
                  name="qualityGateNotes"
                  autoComplete="off"
                  placeholder="Add context before forcing the upload or terminating the run…"
                  className="mt-3 min-h-28 w-full rounded-3xl border border-white/10 bg-slate/70 px-4 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
                  value={notes}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setNotes(event.target.value)}
                />
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => decide(true)}
                  disabled={isPending}
                  className="inline-flex items-center gap-2 rounded-3xl bg-gradient-to-r from-lime/80 to-aqua px-4 py-3 text-sm font-semibold text-slate transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30 disabled:opacity-60"
                >
                  {isPending ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <ShieldCheck aria-hidden="true" className="h-4 w-4" />}
                  Approve & Resume Upload
                </button>
                <button
                  type="button"
                  onClick={() => decide(false)}
                  disabled={isPending}
                  className="inline-flex items-center gap-2 rounded-3xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm font-semibold text-rose-100 transition hover:bg-rose/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose/30 disabled:opacity-60"
                >
                  <ShieldX aria-hidden="true" className="h-4 w-4" />
                  Terminate Job
                </button>
              </div>
            </>
          )}

          <p aria-live="polite" className="text-sm text-mist">
            {feedback}
          </p>
        </section>

        <aside className="overscroll-contain border-t border-white/10 bg-white/[0.03] p-6 lg:border-l lg:border-t-0 lg:max-h-[82vh] lg:overflow-y-auto lg:p-8">
          <p className="text-xs uppercase tracking-[0.22em] text-mist/80">Selected visual assets</p>
          <div className="mt-5 space-y-4">
            {isLoading ? (
              <div className="rounded-[28px] border border-white/10 bg-white/5 p-5 text-sm text-mist">Loading scene matches…</div>
            ) : job?.visual_asset_manifest?.length ? (
              job.visual_asset_manifest.map((asset) => (
                <div key={`${asset.pexels_video_id}-${asset.scene_index}`} className="overflow-hidden rounded-[28px] border border-white/10 bg-white/5">
                  {asset.thumbnail_url ? (
                    <div className="relative h-44 w-full overflow-hidden">
                      <Image src={asset.thumbnail_url} alt={asset.visual_keyword} fill className="object-cover" sizes="(max-width: 1024px) 100vw, 35vw" />
                    </div>
                  ) : null}
                  <div className="space-y-2 p-4">
                    <p className="text-xs uppercase tracking-[0.22em] text-aqua">Scene {asset.scene_index}</p>
                    <p className="text-sm font-semibold text-white">{asset.visual_keyword}</p>
                    <p className="text-sm leading-6 text-mist">{asset.sentence}</p>
                    <p className="text-xs text-white/70">Relevance score: {asset.score}/10</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[28px] border border-white/10 bg-white/5 p-5 text-sm text-mist">No visual assets were attached to this blocked job.</div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
