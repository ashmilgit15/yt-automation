'use client';

import type { ChangeEvent, KeyboardEvent } from 'react';
import { useMemo, useState, useTransition } from 'react';
import { LoaderCircle, Sparkles } from 'lucide-react';

import { createJob } from '@/lib/api';
import type { Orientation, PublishPrivacy, VideoJobSummary } from '@/types/jobs';

interface JobSubmissionFormProps {
  onCreated: (job: VideoJobSummary) => void;
}

const sampleTopics = [
  'This week in AI product launches for founders',
  '3 automation workflows every solo creator should copy',
  'Why open-source AI tools are replacing paid stacks'
];

export function JobSubmissionForm({ onCreated }: JobSubmissionFormProps) {
  const [topic, setTopic] = useState('Trending AI startup moves this week');
  const [targetAudience, setTargetAudience] = useState('Busy founders and creators');
  const [durationSeconds, setDurationSeconds] = useState(60);
  const [orientation, setOrientation] = useState<Orientation>('portrait');
  const [publishPrivacy, setPublishPrivacy] = useState<PublishPrivacy>('public');
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const canSubmit = useMemo(() => topic.trim().length >= 3 && !isPending, [isPending, topic]);

  const effectiveDuration = orientation === 'portrait' ? Math.min(durationSeconds, 59) : durationSeconds;

  const submit = () => {
    if (!canSubmit) {
      return;
    }

    setMessage(null);
    startTransition(async () => {
      try {
        const response = await createJob({
          topic,
          target_audience: targetAudience,
          duration_seconds: effectiveDuration,
          orientation,
          publish_privacy: publishPrivacy
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
          distribution_label: orientation === 'portrait' ? 'YouTube Shorts' : 'Standard Video',
          batch_label: null,
          batch_index: null,
          youtube_url: null,
          title: null,
          critique_text: null,
          manual_override: false,
          created_at: now,
          updated_at: now,
          scene_count: 0,
          visual_asset_count: 0,
          error_summary: null
        });

        setMessage('Pipeline accepted. The worker picked up your job.');
      } catch (error) {
        const fallback = error instanceof Error ? error.message : 'Unable to create the job.';
        setMessage(fallback);
      }
    });
  };

  const handleTopicHotkey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur xl:p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-aqua">Orchestration Panel</p>
          <h2 className="balanced-heading mt-3 text-2xl font-semibold text-white">Launch a new autonomous video run</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-mist">
            Feed the pipeline a sharp topic, audience, and output format. FastAPI enqueues the job instantly and the worker carries it through research, narration, clip scoring, composition, and upload.
          </p>
        </div>
        <div className="hidden rounded-2xl border border-white/10 bg-white/5 p-3 text-aqua lg:block">
          <Sparkles aria-hidden="true" className="h-5 w-5" />
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {sampleTopics.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => setTopic(suggestion)}
            className="rounded-full border border-white/10 bg-slate/70 px-3 py-2 text-xs text-mist transition hover:border-aqua/30 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
          >
            {suggestion}
          </button>
        ))}
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <label className="space-y-2">
          <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Topic Brief</span>
          <textarea
            id="job-topic-input"
            name="topic"
            autoComplete="off"
            placeholder="Describe the video angle, hook, or trend you want to cover…"
            className="min-h-36 w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
            value={topic}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setTopic(event.target.value)}
            onKeyDown={handleTopicHotkey}
          />
          <p className="text-xs text-mist/70">Tip: press Ctrl/Cmd + Enter to queue the job.</p>
        </label>

        <div className="grid gap-4">
          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Target Audience</span>
            <input
              name="targetAudience"
              autoComplete="off"
              spellCheck={false}
              placeholder="Example: Busy founders & creators…"
              className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
              value={targetAudience}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setTargetAudience(event.target.value)}
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-3">
            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Duration</span>
              <input
                name="durationSeconds"
                type="number"
                min={15}
                max={600}
                inputMode="numeric"
                autoComplete="off"
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
                value={durationSeconds}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setDurationSeconds(Number(event.target.value))}
              />
              {orientation === 'portrait' ? <p className="text-xs text-mist/70">Shorts are capped at 59 seconds so YouTube treats them as Shorts.</p> : null}
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Format</span>
              <select
                name="orientation"
                autoComplete="off"
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
                value={orientation}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => setOrientation(event.target.value as Orientation)}
              >
                <option value="portrait">Portrait / Shorts</option>
                <option value="landscape">Landscape / Long-form</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Visibility</span>
              <select
                name="publishPrivacy"
                autoComplete="off"
                className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
                value={publishPrivacy}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => setPublishPrivacy(event.target.value as PublishPrivacy)}
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
            className="inline-flex items-center justify-center gap-2 rounded-3xl bg-gradient-to-r from-aqua to-emerald-300 px-5 py-4 text-sm font-semibold text-slate transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isPending ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden="true" className="h-4 w-4" />}
            {isPending ? 'Queueing Job…' : 'Queue Video Job'}
          </button>
        </div>
      </div>

      <p aria-live="polite" className="mt-4 text-sm text-mist">
        {message}
      </p>
    </div>
  );
}
