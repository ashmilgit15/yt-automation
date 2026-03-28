'use client';

import type { ChangeEvent } from 'react';
import { useMemo, useState, useTransition } from 'react';
import { LoaderCircle, ScissorsLineDashed, WandSparkles } from 'lucide-react';

import { createSourceRemixJob } from '@/lib/api';
import type { Orientation, PublishPrivacy, VideoJobSummary } from '@/types/jobs';

interface SourceRemixLauncherProps {
  onCreated: (job: VideoJobSummary) => void;
}

export function SourceRemixLauncher({ onCreated }: SourceRemixLauncherProps) {
  const [topic, setTopic] = useState('AI startup founders podcast');
  const [targetAudience, setTargetAudience] = useState('Founders and creators');
  const [durationSeconds, setDurationSeconds] = useState(59);
  const [orientation, setOrientation] = useState<Orientation>('portrait');
  const [publishPrivacy, setPublishPrivacy] = useState<PublishPrivacy>('public');
  const [shotsCount, setShotsCount] = useState(5);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const canSubmit = useMemo(() => topic.trim().length >= 3 && !isPending, [isPending, topic]);

  const submit = () => {
    if (!canSubmit) {
      return;
    }

    const effectiveDuration = orientation === 'portrait' ? Math.min(durationSeconds, 59) : durationSeconds;
    setMessage(null);
    startTransition(async () => {
      try {
        const response = await createSourceRemixJob({
          topic,
          target_audience: targetAudience,
          duration_seconds: effectiveDuration,
          orientation,
          publish_privacy: publishPrivacy,
          shots_count: shotsCount
        });
        const now = new Date().toISOString();
        onCreated({
          id: response.job_id,
          topic,
          target_audience: targetAudience || null,
          duration_seconds: effectiveDuration,
          orientation,
          status: 'PENDING',
          quality_score: null,
          publish_privacy: publishPrivacy,
          distribution_label: orientation === 'portrait' ? 'YouTube Shorts Remix' : 'Long-form Remix',
          batch_label: null,
          batch_index: null,
          youtube_url: null,
          title: null,
          critique_text: null,
          manual_override: false,
          created_at: now,
          updated_at: now,
          scene_count: shotsCount,
          visual_asset_count: 0,
          error_summary: null
        });
        setMessage('Source remix job queued. The system will find a long-form YouTube source, download it, cut highlights, and prepare an upload.');
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Unable to queue the source remix job.');
      }
    });
  };

  return (
    <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur xl:p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-lime">Source Video Remix</p>
          <h2 className="balanced-heading mt-3 text-2xl font-semibold text-white">Find a long-form YouTube video and auto-cut viral highlights</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-mist">
            Enter a topic. The backend uses FireCrawl and YouTube discovery to find a long-form source video or podcast, downloads it with `yt-dlp`, extracts the best highlight shots, adds captions and effects, and uploads the remix.
          </p>
        </div>
        <div className="hidden rounded-2xl border border-white/10 bg-white/5 p-3 text-lime lg:block">
          <ScissorsLineDashed aria-hidden="true" className="h-5 w-5" />
        </div>
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
        <label className="space-y-2">
          <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Source Topic</span>
          <textarea
            value={topic}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setTopic(event.target.value)}
            placeholder="Example: AI founder interviews, startup podcast clips, productivity podcast, finance podcast..."
            className="min-h-32 w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-lime/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30"
          />
        </label>

        <div className="grid gap-4">
          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Target Audience</span>
            <input
              value={targetAudience}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setTargetAudience(event.target.value)}
              placeholder="Who should this remixed video target?"
              className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-lime/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-4">
            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Final Length</span>
              <input
                type="number"
                min={15}
                max={180}
                value={durationSeconds}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setDurationSeconds(Number(event.target.value))}
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-lime/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">No. of Shots</span>
              <input
                type="number"
                min={3}
                max={10}
                value={shotsCount}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setShotsCount(Math.max(3, Math.min(10, Number(event.target.value) || 3)))}
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-lime/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30"
              />
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Format</span>
              <select
                value={orientation}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => setOrientation(event.target.value as Orientation)}
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-lime/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30"
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
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-lime/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30"
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
            className="inline-flex items-center justify-center gap-2 rounded-3xl bg-gradient-to-r from-lime to-aqua px-5 py-4 text-sm font-semibold text-slate transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/40 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isPending ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <WandSparkles aria-hidden="true" className="h-4 w-4" />}
            {isPending ? 'Building Remix…' : 'Generate Source Remix'}
          </button>
        </div>
      </div>

      <p aria-live="polite" className="mt-4 text-sm text-mist">
        {message}
      </p>
    </section>
  );
}
