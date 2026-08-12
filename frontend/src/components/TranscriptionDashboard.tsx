'use client';

import { useEffect, useMemo, useState, useTransition } from 'react';
import useSWR from 'swr';
import { CheckCircle2, FileText, LoaderCircle, RefreshCw, ShieldCheck, Upload } from 'lucide-react';

import { OperatorAccessPanel } from '@/components/OperatorAccessPanel';
import { analysePlaylist, createPlaylistBatch, fetchOperatorSession, fetchPlaylistBatch, retryTranscriptJob, transcriptExportUrl } from '@/lib/api';
import type { PlaylistAnalysis, PlaylistBatch, TranscriptJob } from '@/types/transcripts';

const ACTIVE_STATUSES = new Set(['PENDING', 'ACQUIRING', 'TRANSCRIBING', 'EXPORTING']);

function durationLabel(seconds: number | null): string {
  if (seconds === null) return 'Duration unavailable';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secondsPart = seconds % 60;
  return [hours ? `${hours}h` : null, minutes ? `${minutes}m` : null, `${secondsPart}s`].filter(Boolean).join(' ');
}

function statusStyle(status: TranscriptJob['status']): string {
  if (status === 'COMPLETED') return 'border-lime/30 bg-lime/10 text-lime-100';
  if (status === 'FAILED') return 'border-rose/30 bg-rose/10 text-rose-100';
  return 'border-aqua/30 bg-aqua/10 text-aqua';
}

export function TranscriptionDashboard() {
  const { data: session, mutate: mutateSession, error: sessionError } = useSWR('operator-session', fetchOperatorSession, { revalidateOnFocus: false });
  const authenticated = session?.authenticated ?? false;
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [analysis, setAnalysis] = useState<PlaylistAnalysis | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchId, setBatchId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const { data: batch, mutate: mutateBatch } = useSWR<PlaylistBatch>(
    authenticated && batchId ? ['playlist-batch', batchId] : null,
    () => fetchPlaylistBatch(batchId as string),
    { refreshInterval: (latest) => latest?.jobs.some((job) => ACTIVE_STATUSES.has(job.status)) ? 3500 : 0, revalidateOnFocus: false }
  );

  const allSelected = analysis && selected.size === analysis.videos.length;
  const completedCount = batch?.completed_videos ?? 0;
  const totalCount = batch?.total_videos ?? 0;
  const overallProgress = totalCount ? Math.round(((completedCount + (batch?.failed_videos ?? 0)) / totalCount) * 100) : 0;

  const handleAnalyse = () => {
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await analysePlaylist(playlistUrl);
        setAnalysis(result);
        setSelected(new Set(result.videos.map((video) => video.video_id)));
        setBatchId(null);
        setMessage(`Found ${result.videos.length} videos. Select the authorised videos to queue.`);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Unable to analyse this playlist.');
      }
    });
  };

  const handleQueue = () => {
    if (!analysis || selected.size === 0) return;
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await createPlaylistBatch(analysis.playlist_url, [...selected]);
        setBatchId(result.id);
        setMessage(`${result.total_videos} authorised videos were queued for local transcription.`);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : 'Unable to start the transcription batch.');
      }
    });
  };

  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(analysis?.videos.map((video) => video.video_id)));
  const retry = async (jobId: string) => {
    try {
      await retryTranscriptJob(jobId);
      await mutateBatch();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to retry this transcript.');
    }
  };

  return (
    <main className="min-h-screen bg-mesh text-white">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="rounded-[36px] border border-white/10 bg-white/[0.04] p-6 shadow-panel backdrop-blur lg:p-8">
          <p className="text-xs uppercase tracking-[0.32em] text-aqua">Authorised media workflow</p>
          <h1 className="balanced-heading mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">Bulk YouTube Transcriber</h1>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-mist sm:text-base">
            Analyse a playlist, choose videos you are authorised to process, then transcribe them locally with faster-whisper. Download every completed result as TXT, SRT, VTT, or JSON.
          </p>
        </header>

        {sessionError ? <p className="mt-6 rounded-3xl border border-rose/30 bg-rose/10 p-4 text-rose-100">The dashboard cannot reach the FastAPI backend.</p> : null}
        <OperatorAccessPanel session={session} onSessionChange={() => void mutateSession()} />

        {!authenticated ? <p className="mt-6 rounded-3xl border border-white/10 bg-white/5 p-6 text-mist">Sign in to analyse a playlist and start the local worker queue.</p> : null}

        {authenticated ? <>
          <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur">
            <p className="text-xs uppercase tracking-[0.26em] text-aqua">1. Analyse playlist</p>
            <div className="mt-4 flex flex-col gap-3 md:flex-row">
              <input value={playlistUrl} onChange={(event) => setPlaylistUrl(event.target.value)} placeholder="https://www.youtube.com/playlist?list=…" className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white" />
              <button type="button" onClick={handleAnalyse} disabled={!playlistUrl.trim() || isPending} className="inline-flex items-center justify-center gap-2 rounded-2xl bg-aqua px-5 py-4 font-semibold text-slate disabled:opacity-60">
                {isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />} Analyse playlist
              </button>
            </div>
            {message ? <p aria-live="polite" className="mt-4 text-sm text-mist">{message}</p> : null}
          </section>

          {analysis ? <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div><p className="text-xs uppercase tracking-[0.26em] text-lime">2. Confirm selection</p><h2 className="mt-2 text-2xl font-semibold">{analysis.title ?? 'Playlist'}</h2><p className="mt-1 text-sm text-mist">{analysis.videos.length} videos found · {selected.size} selected</p></div>
              <div className="flex gap-3"><button type="button" onClick={toggleAll} className="rounded-full border border-white/10 px-4 py-2 text-sm text-mist">{allSelected ? 'Clear all' : 'Select all'}</button><button type="button" onClick={handleQueue} disabled={!selected.size || isPending} className="inline-flex items-center gap-2 rounded-full bg-lime px-4 py-2 text-sm font-semibold text-slate disabled:opacity-60"><ShieldCheck className="h-4 w-4" />Queue selected</button></div>
            </div>
            <label className="mt-5 flex gap-3 rounded-2xl border border-amber-300/20 bg-amber-300/10 p-4 text-sm leading-6 text-amber-50"><input type="checkbox" checked readOnly className="mt-1 h-4 w-4 accent-lime" />By clicking “Queue selected,” I confirm I own these videos or otherwise have permission to obtain and process their audio.</label>
            <div className="mt-5 max-h-[480px] space-y-2 overflow-y-auto pr-1">
              {analysis.videos.map((video) => <label key={video.video_id} className="flex cursor-pointer items-center gap-4 rounded-2xl border border-white/10 bg-slate/50 p-3 hover:border-aqua/30"><input type="checkbox" checked={selected.has(video.video_id)} onChange={() => setSelected((current) => { const next = new Set(current); next.has(video.video_id) ? next.delete(video.video_id) : next.add(video.video_id); return next; })} className="h-4 w-4 accent-aqua" />{video.thumbnail_url ? <img src={video.thumbnail_url} alt="" className="h-12 w-20 rounded-lg object-cover" /> : null}<span className="min-w-0 flex-1"><span className="block truncate font-medium text-white">{video.title}</span><span className="text-xs text-mist">{video.channel_title ?? 'Unknown channel'} · {durationLabel(video.duration_seconds)}</span></span></label>)}
            </div>
          </section> : null}

          {batch ? <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs uppercase tracking-[0.26em] text-aqua">Live batch</p><h2 className="mt-2 text-2xl font-semibold">{batch.title ?? 'Transcript batch'}</h2><p className="mt-1 text-sm text-mist">{completedCount} completed · {batch.failed_videos} failed · {totalCount} total</p></div><span className="rounded-full border border-aqua/30 bg-aqua/10 px-3 py-2 text-sm text-aqua">{batch.status}</span></div>
            <div className="mt-5 h-3 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-gradient-to-r from-aqua to-lime" style={{ width: `${overallProgress}%` }} /></div>
            <div className="mt-6 space-y-3">{batch.jobs.map((job) => <TranscriptRow key={job.id} job={job} onRetry={retry} />)}</div>
          </section> : null}
        </> : null}
      </div>
    </main>
  );
}

function TranscriptRow({ job, onRetry }: { job: TranscriptJob; onRetry: (id: string) => void }) {
  return <article className="rounded-2xl border border-white/10 bg-slate/50 p-4"><div className="flex flex-col gap-4 md:flex-row md:items-center"><div className="min-w-0 flex-1"><p className="truncate font-semibold text-white">{job.title}</p><p className="mt-1 text-xs text-mist">{job.channel_title ?? 'Unknown channel'} · {durationLabel(job.duration_seconds)} {job.language ? `· ${job.language}` : ''}</p></div><span className={`w-fit rounded-full border px-3 py-1 text-xs font-medium ${statusStyle(job.status)}`}>{job.status} {ACTIVE_STATUSES.has(job.status) ? `${job.progress}%` : ''}</span></div>{ACTIVE_STATUSES.has(job.status) ? <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-aqua" style={{ width: `${job.progress}%` }} /></div> : null}{job.error_summary ? <p className="mt-3 text-xs leading-5 text-rose-100">{job.error_summary}</p> : null}{job.status === 'FAILED' ? <button type="button" onClick={() => onRetry(job.id)} className="mt-3 inline-flex items-center gap-2 rounded-full border border-amber-300/30 px-3 py-2 text-xs text-amber-50"><RefreshCw className="h-3 w-3" />Retry</button> : null}{job.status === 'COMPLETED' ? <div className="mt-3 flex flex-wrap gap-2">{(['txt', 'srt', 'vtt', 'json'] as const).map((format) => <a key={format} href={transcriptExportUrl(job.id, format)} className="inline-flex items-center gap-1 rounded-full border border-white/10 px-3 py-2 text-xs text-mist hover:border-aqua/40 hover:text-white"><Upload className="h-3 w-3" />{format.toUpperCase()}</a>)}</div> : null}</article>;
}
