'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { ArrowRight, Bot, Film, HelpCircle, Radar } from 'lucide-react';

import { JobGrid } from '@/components/JobGrid';
import { BulkNicheLauncher } from '@/components/BulkNicheLauncher';
import { JobSubmissionForm } from '@/components/JobSubmissionForm';
import { KeyboardShortcutsPanel } from '@/components/KeyboardShortcutsPanel';
import { OperatorAccessPanel } from '@/components/OperatorAccessPanel';
import { QualityGateReview } from '@/components/QualityGateReview';
import { SourceRemixLauncher } from '@/components/SourceRemixLauncher';
import { TelemetryCards } from '@/components/TelemetryCards';
import { YouTubeConnectionPanel } from '@/components/YouTubeConnectionPanel';
import { deleteJob, duplicateJob, fetchJob, fetchJobs, fetchOperatorSession, makeJobPublic, regenerateMetadata, resumeJobFromStage, retryJob, publishJob, bulkPublishJobs } from '@/lib/api';
import { PublishModal } from '@/components/PublishModal';
import type { JobCollectionResponse, JobStatus, VideoJobDetail, VideoJobSummary } from '@/types/jobs';

interface DashboardShellProps {
  mode?: 'dashboard' | 'jobs';
}

function isActiveStatus(status: JobStatus): boolean {
  return !['COMPLETED', 'FAILED', 'CANCELLED'].includes(status);
}

function LoadingJobsState() {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="rounded-[30px] border border-white/10 bg-white/5 p-5 shadow-panel backdrop-blur">
          <div className="h-4 w-28 rounded-full bg-white/10" />
          <div className="mt-4 h-8 w-3/4 rounded-full bg-white/10" />
          <div className="mt-3 h-4 w-1/2 rounded-full bg-white/10" />
          <div className="mt-6 h-20 rounded-[24px] bg-white/10" />
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="h-24 rounded-[24px] bg-white/10" />
            <div className="h-24 rounded-[24px] bg-white/10" />
            <div className="h-24 rounded-[24px] bg-white/10" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function DashboardShell({ mode = 'dashboard' }: DashboardShellProps) {
  const { data: session, error: sessionError, isLoading: isSessionLoading, mutate: mutateSession } = useSWR('operator-session', fetchOperatorSession, {
    dedupingInterval: 5000,
    revalidateOnFocus: false
  });

  const authenticated = session?.authenticated ?? false;
  const { data: jobCollection, error: jobsError, isLoading: isJobsLoading, mutate: mutateJobs } = useSWR<JobCollectionResponse>(
    authenticated ? ['jobs', mode] : null,
    () => fetchJobs(mode === 'jobs' ? 40 : 24),
    {
      dedupingInterval: 2500,
      refreshWhenHidden: false,
      refreshInterval: (latestData) => (latestData?.jobs?.some((job) => isActiveStatus(job.status)) ? 4000 : 12000)
    }
  );

  const [reviewJobId, setReviewJobId] = useState<string | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [busyActionKey, setBusyActionKey] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const [publishTargetIds, setPublishTargetIds] = useState<string[]>([]);

  const { data: reviewJob, isLoading: isReviewLoading, mutate: mutateReview } = useSWR<VideoJobDetail>(
    authenticated && reviewJobId ? ['job-detail', reviewJobId] : null,
    () => fetchJob(reviewJobId as string),
    {
      dedupingInterval: 1500,
      refreshInterval: reviewJobId ? 4000 : 0
    }
  );

  const jobs = jobCollection?.jobs ?? [];
  const blockedJob = useMemo(
    () => jobs.find((job) => job.status === 'BLOCKED_BY_QUALITY_GATE') ?? null,
    [jobs]
  );

  useEffect(() => {
    if (!authenticated) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = !!target?.closest('input, textarea, select');

      if (event.key === '?' && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        setShowShortcuts((current) => !current);
        return;
      }

      if (event.key === 'Escape') {
        setShowShortcuts(false);
        if (reviewJobId) {
          setReviewJobId(null);
        }
        return;
      }

      if (isTyping) {
        return;
      }

      if (event.key.toLowerCase() === 'n') {
        event.preventDefault();
        const topicInput = document.getElementById('job-topic-input');
        topicInput?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        (topicInput as HTMLTextAreaElement | null)?.focus();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [authenticated, reviewJobId]);

  const heading = mode === 'jobs' ? 'Job history and live pipeline traces' : 'Autonomous video factory command deck';
  const subheading =
    mode === 'jobs'
      ? 'Track every run, inspect stage-by-stage progress, and jump into human review when the policy gate stalls a publish.'
      : 'A full-stack orchestration surface for research, voice synthesis, multimodal clip scoring, subtitle timing, FFmpeg composition, and YouTube delivery.';

  const handleSessionChange = () => {
    void mutateSession();
    void mutateJobs();
  };

  const handleCreatedJob = (job: VideoJobSummary) => {
    void mutateJobs(
      (current) => {
        if (!current) {
          return {
            jobs: [job],
            total_count: 1,
            page_size: mode === 'jobs' ? 40 : 24,
            active_count: 1,
            blocked_count: 0
          };
        }

        return {
          ...current,
          jobs: [job, ...current.jobs].slice(0, current.page_size),
          total_count: current.total_count + 1,
          active_count: current.active_count + 1
        };
      },
      { revalidate: false }
    );
    void mutateJobs();
  };

  const handleBulkCreated = (queuedJobs: VideoJobSummary[]) => {
    void mutateJobs(
      (current) => {
        if (!current) {
          return {
            jobs: queuedJobs,
            total_count: queuedJobs.length,
            page_size: mode === 'jobs' ? 40 : 24,
            active_count: queuedJobs.length,
            blocked_count: 0
          };
        }

        return {
          ...current,
          jobs: [...queuedJobs, ...current.jobs].slice(0, current.page_size),
          total_count: current.total_count + queuedJobs.length,
          active_count: current.active_count + queuedJobs.length
        };
      },
      { revalidate: false }
    );
    void mutateJobs();
  };

  const handleReviewResolved = () => {
    void mutateJobs();
    void mutateReview();
  };

  const patchJobSummary = (updatedJob: VideoJobDetail) => {
    void mutateJobs(
      (current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          jobs: current.jobs.map((job) =>
            job.id === updatedJob.id
              ? {
                  ...job,
                  title: updatedJob.title,
                  critique_text: updatedJob.critique_text,
                  status: updatedJob.status,
                  quality_score: updatedJob.quality_score,
                  publish_privacy: updatedJob.publish_privacy,
                  distribution_label: updatedJob.distribution_label,
                  youtube_url: updatedJob.youtube_url,
                  updated_at: updatedJob.updated_at,
                  error_summary: updatedJob.error_log ? updatedJob.error_log.slice(0, 220) : null,
                  scene_count: updatedJob.scenes_json?.length ?? job.scene_count,
                  visual_asset_count: updatedJob.visual_asset_manifest?.length ?? job.visual_asset_count
                }
              : job
          )
        };
      },
      { revalidate: false }
    );
  };

  const createPendingClone = (sourceJob: VideoJobSummary, newJobId: string): VideoJobSummary => {
    const now = new Date().toISOString();
    return {
      ...sourceJob,
      id: newJobId,
      status: 'PENDING',
      quality_score: null,
      youtube_url: null,
      critique_text: null,
      manual_override: false,
      created_at: now,
      updated_at: now,
      error_summary: null
    };
  };

  const enqueueCloneAction = async (
    actionKey: string,
    sourceJobId: string,
    request: (jobId: string) => Promise<{ job_id: string; status: string }>,
    successMessage: string
  ) => {
    const sourceJob = jobs.find((job) => job.id === sourceJobId);
    if (!sourceJob) {
      setActionMessage('That job is no longer available in the current list. Refresh and try again.');
      return;
    }

    setBusyActionKey(actionKey);
    setActionMessage(null);
    try {
      const response = await request(sourceJobId);
      handleCreatedJob(createPendingClone(sourceJob, response.job_id));
      setActionMessage(successMessage);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : 'The requested action could not be completed.');
    } finally {
      setBusyActionKey(null);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    await enqueueCloneAction(`retry:${jobId}`, jobId, retryJob, 'A fresh retry job was queued from the failed run.');
  };

  const handleDuplicateJob = async (jobId: string) => {
    await enqueueCloneAction(`duplicate:${jobId}`, jobId, duplicateJob, 'A duplicate job was queued successfully.');
  };

  const handleMakePublic = async (jobId: string) => {
    setBusyActionKey(`public:${jobId}`);
    setActionMessage(null);
    try {
      const updatedJob = await makeJobPublic(jobId);
      patchJobSummary(updatedJob);
      setActionMessage('The uploaded video is now set to public on YouTube.');
      void mutateJobs();
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : 'Unable to change the video visibility right now.');
    } finally {
      setBusyActionKey(null);
    }
  };

  const handleResumeFromStage = async (jobId: string) => {
    setBusyActionKey(`resume:${jobId}`);
    setActionMessage(null);
    try {
      const updatedJob = await resumeJobFromStage(jobId);
      patchJobSummary(updatedJob);
      setActionMessage('The job was resumed from its last good checkpoint.');
      void mutateJobs();
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : 'Unable to resume this failed job.');
    } finally {
      setBusyActionKey(null);
    }
  };

  const handleRegenerateMetadata = async (jobId: string) => {
    setBusyActionKey(`metadata:${jobId}`);
    setActionMessage(null);
    try {
      const updatedJob = await regenerateMetadata(jobId);
      patchJobSummary(updatedJob);
      setActionMessage('Metadata was regenerated and synced to YouTube when applicable.');
      void mutateJobs();
      if (reviewJobId === jobId) {
        void mutateReview();
      }
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : 'Unable to regenerate metadata right now.');
    } finally {
      setBusyActionKey(null);
    }
  };

  const handleSelectJob = (jobId: string, selected: boolean) => {
    setSelectedJobIds(prev => {
      const next = new Set(prev);
      if (selected) next.add(jobId);
      else next.delete(jobId);
      return next;
    });
  };

  const handlePublishClick = (jobId: string) => {
    setPublishTargetIds([jobId]);
    setPublishModalOpen(true);
  };

  const handleBulkPublishClick = () => {
    if (selectedJobIds.size > 0) {
      setPublishTargetIds(Array.from(selectedJobIds));
      setPublishModalOpen(true);
    }
  };

  const handlePublishConfirm = async (channelLabel: string) => {
    setPublishModalOpen(false);
    setActionMessage(null);
    setBusyActionKey('publishing');
    try {
      if (publishTargetIds.length === 1) {
        const result = await publishJob(publishTargetIds[0], channelLabel);
        setActionMessage(result.message);
      } else {
        const result = await bulkPublishJobs(publishTargetIds, channelLabel);
        setActionMessage(`Bulk published ${result.jobs_processed} jobs to ${channelLabel}.`);
        setSelectedJobIds(new Set());
      }
      void mutateJobs();
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : 'Unable to publish.');
    } finally {
      setBusyActionKey(null);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    const confirmed = window.confirm('Delete this job record and local artifacts? Uploaded YouTube videos will stay on YouTube.');
    if (!confirmed) {
      return;
    }

    setBusyActionKey(`delete:${jobId}`);
    setActionMessage(null);
    try {
      const response = await deleteJob(jobId);
      void mutateJobs(
        (current) => {
          if (!current) {
            return current;
          }
          const remainingJobs = current.jobs.filter((job) => job.id !== jobId);
          return {
            ...current,
            jobs: remainingJobs,
            total_count: Math.max(current.total_count - 1, 0),
            active_count: remainingJobs.filter((job) => isActiveStatus(job.status)).length,
            blocked_count: remainingJobs.filter((job) => job.status === 'BLOCKED_BY_QUALITY_GATE').length
          };
        },
        { revalidate: false }
      );
      if (reviewJobId === jobId) {
        setReviewJobId(null);
      }
      setActionMessage(response.message);
      void mutateJobs();
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : 'Unable to delete this job right now.');
    } finally {
      setBusyActionKey(null);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-mesh text-white">
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:88px_88px] opacity-20" />
      <div className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="rounded-[36px] border border-white/10 bg-white/[0.04] p-6 shadow-panel backdrop-blur lg:p-8">
          <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <p className="text-xs uppercase tracking-[0.32em] text-aqua">YouTube Automation Factory</p>
              <h1 className="balanced-heading mt-4 text-4xl font-semibold tracking-tight text-white sm:text-5xl">{heading}</h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-mist sm:text-base">{subheading}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3 xl:max-w-3xl">
              <div className="rounded-[28px] border border-white/10 bg-slate/60 px-5 py-4">
                <Film aria-hidden="true" className="h-5 w-5 text-ember" />
                <p className="mt-3 text-sm font-semibold text-white">Programmatic assembly</p>
                <p className="mt-1 text-xs leading-6 text-mist">FFmpeg-first composition with timed scene normalization and subtitle burn-in.</p>
              </div>
              <div className="rounded-[28px] border border-white/10 bg-slate/60 px-5 py-4">
                <Bot aria-hidden="true" className="h-5 w-5 text-aqua" />
                <p className="mt-3 text-sm font-semibold text-white">Multi-agent AI pipeline</p>
                <p className="mt-1 text-xs leading-6 text-mist">Gemini writes and judges. Kokoro narrates. Groq timestamps. Pexels fills the frame.</p>
              </div>
              <div className="rounded-[28px] border border-white/10 bg-slate/60 px-5 py-4">
                <Radar aria-hidden="true" className="h-5 w-5 text-lime" />
                <p className="mt-3 text-sm font-semibold text-white">Policy-aware shipping</p>
                <p className="mt-1 text-xs leading-6 text-mist">Low-authenticity uploads stop at the quality gate before they can hit your channel.</p>
              </div>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3 text-sm">
            <button
              type="button"
              onClick={() => setShowShortcuts(true)}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 px-4 py-2 text-mist transition hover:border-aqua/30 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
            >
              <HelpCircle aria-hidden="true" className="h-4 w-4" />
              Keyboard Shortcuts
            </button>
            {authenticated ? (
              <p className="rounded-full border border-lime/20 bg-lime/10 px-4 py-2 text-lime-100">
                Signed in as <span className="font-semibold text-white">{session?.username}</span>
              </p>
            ) : isSessionLoading ? (
              <p className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-mist">Checking operator session…</p>
            ) : null}
          </div>
        </header>

        {sessionError ? (
          <section className="mt-6 rounded-[32px] border border-rose/20 bg-rose/10 p-6 text-sm text-rose-100 shadow-panel backdrop-blur">
            The dashboard could not reach the backend session endpoint. Make sure the FastAPI server is running on `http://localhost:8000`.
          </section>
        ) : null}

        <OperatorAccessPanel session={session} onSessionChange={handleSessionChange} />

        {authenticated ? (
          <>
            {actionMessage ? (
              <section className="mt-6 rounded-[28px] border border-aqua/20 bg-aqua/10 px-5 py-4 text-sm text-aqua shadow-panel backdrop-blur">
                {actionMessage}
              </section>
            ) : null}

            <div className="mt-6">
              <TelemetryCards jobs={jobs} />
            </div>

            <Suspense
              fallback={
                <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 text-sm text-mist shadow-panel backdrop-blur">
                  Loading YouTube connection status…
                </section>
              }
            >
              <YouTubeConnectionPanel enabled={authenticated} />
            </Suspense>

            {mode === 'dashboard' ? (
              <section className="mt-6">
                <JobSubmissionForm onCreated={handleCreatedJob} />
              </section>
            ) : null}

            {mode === 'dashboard' ? <BulkNicheLauncher onCreated={handleBulkCreated} /> : null}

            {mode === 'dashboard' ? <SourceRemixLauncher onCreated={handleCreatedJob} /> : null}

            {blockedJob ? (
              <section className="mt-6 rounded-[32px] border border-fuchsia-300/20 bg-fuchsia-300/10 p-5 shadow-panel backdrop-blur">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-fuchsia-100">Review required</p>
                    <h2 className="balanced-heading mt-2 text-2xl font-semibold text-white">{blockedJob.title ?? blockedJob.topic}</h2>
                    <p className="mt-2 text-sm leading-7 text-fuchsia-50/90">{blockedJob.critique_text ?? 'The quality gate flagged this draft and is waiting for human intervention.'}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setReviewJobId(blockedJob.id)}
                    className="inline-flex items-center gap-2 rounded-3xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fuchsia-300/50"
                  >
                    Review Blocked Upload
                    <ArrowRight aria-hidden="true" className="h-4 w-4" />
                  </button>
                </div>
              </section>
            ) : null}

            <section className="mt-6 space-y-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-mist/80">Live jobs</p>
                  <h2 className="balanced-heading mt-2 text-2xl font-semibold text-white">
                    {mode === 'jobs' ? 'Every pipeline run in one place' : 'Historical and active jobs'}
                  </h2>
                  {jobCollection ? (
                    <p className="mt-2 text-sm text-mist">Showing the most recent {jobCollection.jobs.length} jobs out of {jobCollection.total_count} total.</p>
                  ) : null}
                </div>
                {mode === 'dashboard' ? (
                  <Link
                    href="/jobs"
                    className="rounded-full border border-white/10 px-4 py-2 text-sm text-mist transition hover:border-aqua/40 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
                  >
                    Open Jobs Console
                  </Link>
                ) : null}
              </div>

              {selectedJobIds.size > 0 && (
                <div className="flex items-center justify-between rounded-[24px] border border-aqua/30 bg-aqua/10 px-5 py-4 text-sm text-aqua shadow-panel backdrop-blur">
                  <span>{selectedJobIds.size} jobs selected ready to publish</span>
                  <button 
                    onClick={handleBulkPublishClick}
                    className="rounded-full bg-aqua px-4 py-2 text-slate font-bold hover:brightness-110 transition"
                  >
                    Bulk Publish Selected
                  </button>
                </div>
              )}

              {isJobsLoading ? (
                <LoadingJobsState />
              ) : jobsError ? (
                <div className="rounded-[30px] border border-rose/20 bg-rose/10 p-8 text-sm text-rose-100 shadow-panel backdrop-blur">
                  The dashboard could not load job summaries. Confirm the backend API and database are running, then refresh the page.
                </div>
              ) : jobs.length ? (
                <JobGrid
                  jobs={jobs}
                  detailed={mode === 'jobs'}
                  onReview={setReviewJobId}
                  onRetry={handleRetryJob}
                  onDuplicate={handleDuplicateJob}
                  onMakePublic={handleMakePublic}
                  onResumeFromStage={handleResumeFromStage}
                  onRegenerateMetadata={handleRegenerateMetadata}
                  onDelete={handleDeleteJob}
                  onPublish={handlePublishClick}
                  selectedJobIds={selectedJobIds}
                  onSelectJob={handleSelectJob}
                  busyActionKey={busyActionKey}
                />
              ) : (
                <div className="rounded-[30px] border border-white/10 bg-white/5 p-8 text-sm text-mist shadow-panel backdrop-blur">
                  <p className="text-lg font-semibold text-white">No jobs have been queued yet.</p>
                  <p className="mt-2 max-w-2xl leading-7">
                    Start with a concise topic, choose your target audience, and let the pipeline research, narrate, score footage, assemble the edit, and prepare the upload for review.
                  </p>
                </div>
              )}
            </section>
          </>
        ) : (
          <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-8 text-sm leading-7 text-mist shadow-panel backdrop-blur">
            Sign in as the operator to unlock job orchestration, YouTube connection management, and quality-gate review controls.
          </section>
        )}
      </div>

      <KeyboardShortcutsPanel open={showShortcuts} onClose={() => setShowShortcuts(false)} />

      <PublishModal 
        isOpen={publishModalOpen} 
        onClose={() => setPublishModalOpen(false)} 
        onConfirm={handlePublishConfirm} 
        isBulk={publishTargetIds.length > 1} 
        count={publishTargetIds.length} 
      />

      <QualityGateReview
        job={reviewJob ?? null}
        isLoading={isReviewLoading}
        onClose={() => setReviewJobId(null)}
        onResolved={handleReviewResolved}
      />
    </div>
  );
}
