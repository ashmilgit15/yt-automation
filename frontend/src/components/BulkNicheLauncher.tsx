'use client';

import type { ChangeEvent } from 'react';
import { useMemo, useState, useTransition } from 'react';
import { Layers3, LoaderCircle, WandSparkles } from 'lucide-react';

import { createBulkJobs } from '@/lib/api';
import type { Orientation, PublishPrivacy, VideoJobSummary } from '@/types/jobs';

interface BulkNicheLauncherProps {
  onCreated: (jobs: VideoJobSummary[]) => void;
}

export function BulkNicheLauncher({ onCreated }: BulkNicheLauncherProps) {
  const [niche, setNiche] = useState('AI startup shake-up');
  const [targetAudience, setTargetAudience] = useState('Busy founders and professionals');
  const [durationSeconds, setDurationSeconds] = useState(60);
  const [orientation, setOrientation] = useState<Orientation>('portrait');
  const [publishPrivacy, setPublishPrivacy] = useState<PublishPrivacy>('public');
  const [videosCount, setVideosCount] = useState(5);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const canSubmit = useMemo(() => niche.trim().length >= 3 && !isPending, [isPending, niche]);

  const submit = () => {
    if (!canSubmit) {
      return;
    }

    const effectiveDuration = orientation === 'portrait' ? Math.min(durationSeconds, 59) : durationSeconds;
    setMessage(null);
    startTransition(async () => {
      try {
        const response = await createBulkJobs({
          niche,
          target_audience: targetAudience,
          duration_seconds: effectiveDuration,
          orientation,
          publish_privacy: publishPrivacy,
          videos_count: videosCount
        });

        const now = new Date().toISOString();
        const queuedJobs: VideoJobSummary[] = response.jobs.map((job) => ({
          id: job.job_id,
          topic: job.topic,
          target_audience: job.target_audience,
          duration_seconds: effectiveDuration,
          orientation,
          status: job.status,
          quality_score: null,
          publish_privacy: publishPrivacy,
          distribution_label: orientation === 'portrait' ? 'YouTube Shorts' : 'Standard Video',
          batch_label: response.batch_label,
          batch_index: job.batch_index,
          youtube_url: null,
          title: null,
          critique_text: null,
          manual_override: false,
          created_at: now,
          updated_at: now,
          scene_count: 0,
          visual_asset_count: 0,
          error_summary: null
        }));

        onCreated(queuedJobs);
        setMessage(`Queued ${response.videos_count} sub-niche jobs from the niche "${response.batch_label}".`);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Unable to queue the bulk niche batch.');
      }
    });
  };

  return (
    <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur xl:p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-ember">Bulk Niche Launcher</p>
          <h2 className="balanced-heading mt-3 text-2xl font-semibold text-white">Turn one niche into multiple sub-niche video jobs</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-mist">
            Drop in one broad niche and the planner will create a batch of specific sub-topic videos and queue them all with one click.
          </p>
        </div>
        <div className="hidden rounded-2xl border border-white/10 bg-white/5 p-3 text-ember lg:block">
          <Layers3 aria-hidden="true" className="h-5 w-5" />
        </div>
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
        <label className="space-y-2">
          <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Main Niche</span>
          <textarea
            value={niche}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setNiche(event.target.value)}
            placeholder="Example: AI startup news, personal finance for freelancers, faceless health hacks..."
            className="min-h-32 w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-ember/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/30"
          />
        </label>

        <div className="grid gap-4">
          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Target Audience</span>
            <input
              value={targetAudience}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setTargetAudience(event.target.value)}
              placeholder={`Who should these ${videosCount} videos target?`}
              className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-ember/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/30"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-4">
            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Duration</span>
              <input
                type="number"
                min={15}
                max={600}
                value={durationSeconds}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setDurationSeconds(Number(event.target.value))}
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-ember/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/30"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">No. of Videos</span>
              <input
                type="number"
                min={2}
                max={10}
                value={videosCount}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setVideosCount(Math.max(2, Math.min(10, Number(event.target.value) || 2)))}
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-ember/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/30"
              />
              <p className="text-xs text-mist/70">Choose between 2 and 10 videos.</p>
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Format</span>
              <select
                value={orientation}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => setOrientation(event.target.value as Orientation)}
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-ember/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/30"
              >
                <option value="portrait">Portrait / Shorts</option>
                <option value="landscape">Landscape / Long-form</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Visibility</span>
              <select
                value={publishPrivacy}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => setPublishPrivacy(event.target.value as PublishPrivacy)}
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-ember/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/30"
              >
                <option value="public">Public</option>
                <option value="unlisted">Unlisted</option>
                <option value="private">Private</option>
              </select>
            </label>
          </div>

          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            className="inline-flex items-center justify-center gap-2 rounded-3xl bg-gradient-to-r from-ember to-aqua px-5 py-4 text-sm font-semibold text-slate transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/40 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isPending ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <WandSparkles aria-hidden="true" className="h-4 w-4" />}
            {isPending ? `Planning ${videosCount} Videos…` : `Generate ${videosCount} Sub-Niche Jobs`}
          </button>
        </div>
      </div>

      <p aria-live="polite" className="mt-4 text-sm text-mist">
        {message}
      </p>
    </section>
  );
}
