'use client';

import { useEffect, useMemo, useState, useTransition } from 'react';
import useSWR from 'swr';
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Flame,
  Globe,
  History,
  Layers,
  ListVideo,
  LoaderCircle,
  Play,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Video,
  X
} from 'lucide-react';

import { OperatorAccessPanel } from '@/components/OperatorAccessPanel';
import {
  analysePlaylist,
  createPlaylistBatch,
  createSingleTranscriptJob,
  fetchOperatorSession,
  fetchPlaylistBatch,
  fetchPlaylistBatches,
  fetchRecentTranscriptJobs,
  fetchTranscriptJob,
  retryTranscriptJob,
  transcriptExportUrl
} from '@/lib/api';
import {
  INDIC_LANGUAGES,
  type PlaylistAnalysis,
  type PlaylistBatch,
  type PlaylistBatchSummary,
  type SarvamMode,
  type TranscriptJob,
  type TranscriptionEngine
} from '@/types/transcripts';

const ACTIVE_STATUSES = new Set(['PENDING', 'ACQUIRING', 'TRANSCRIBING', 'EXPORTING']);

function durationLabel(seconds: number | null): string {
  if (seconds === null) return 'Duration unavailable';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secondsPart = seconds % 60;
  return [hours ? `${hours}h` : null, minutes ? `${minutes}m` : null, `${secondsPart}s`].filter(Boolean).join(' ');
}

function statusStyle(status: TranscriptJob['status']): string {
  if (status === 'COMPLETED') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
  if (status === 'FAILED') return 'border-rose-500/30 bg-rose-500/10 text-rose-300';
  if (status === 'TRANSCRIBING') return 'border-amber-400/30 bg-amber-400/10 text-amber-300 animate-pulse';
  return 'border-cyan-400/30 bg-cyan-400/10 text-cyan-300';
}

export function TranscriptionDashboard() {
  const { data: session, mutate: mutateSession, error: sessionError } = useSWR(
    'operator-session',
    fetchOperatorSession,
    { revalidateOnFocus: false }
  );
  const authenticated = session?.authenticated ?? false;

  // Active Tab: 'playlist' | 'single' | 'history'
  const [activeTab, setActiveTab] = useState<'playlist' | 'single' | 'history'>('playlist');

  // Common Engine Options
  const [engine, setEngine] = useState<TranscriptionEngine>('local_whisper');
  const [languageCode, setLanguageCode] = useState<string>('unknown');
  const [sarvamMode, setSarvamMode] = useState<SarvamMode>('transcribe');
  const [authorisedConsent, setAuthorisedConsent] = useState(true);

  // Playlist State
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [analysis, setAnalysis] = useState<PlaylistAnalysis | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchId, setBatchId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; type: 'info' | 'error' | 'success' } | null>(null);
  const [isPending, startTransition] = useTransition();

  // Single Video State
  const [singleVideoUrl, setSingleVideoUrl] = useState('');
  const [singleJobId, setSingleJobId] = useState<string | null>(null);

  // History Sub-tab State
  const [historySubTab, setHistorySubTab] = useState<'videos' | 'batches'>('videos');

  // Transcript Preview Modal State
  const [previewJob, setPreviewJob] = useState<TranscriptJob | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [copied, setCopied] = useState(false);

  // Restore active sessions from localStorage on client mount
  useEffect(() => {
    try {
      const savedBatchId = localStorage.getItem('yt_active_batch_id');
      if (savedBatchId) setBatchId(savedBatchId);

      const savedSingleJobId = localStorage.getItem('yt_active_single_job_id');
      if (savedSingleJobId) setSingleJobId(savedSingleJobId);
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  // Save active IDs to localStorage
  useEffect(() => {
    if (batchId) {
      localStorage.setItem('yt_active_batch_id', batchId);
    }
  }, [batchId]);

  useEffect(() => {
    if (singleJobId) {
      localStorage.setItem('yt_active_single_job_id', singleJobId);
    }
  }, [singleJobId]);

  // Live Batch Polling
  const { data: batch, mutate: mutateBatch } = useSWR<PlaylistBatch>(
    authenticated && batchId ? ['playlist-batch', batchId] : null,
    () => fetchPlaylistBatch(batchId as string),
    {
      refreshInterval: (latest) =>
        latest?.jobs.some((job) => ACTIVE_STATUSES.has(job.status)) ? 2000 : 0,
      revalidateOnFocus: true
    }
  );

  // Live Single Video Polling
  const { data: polledSingleJob, mutate: mutateSingleJob } = useSWR<TranscriptJob>(
    authenticated && singleJobId ? ['transcript-job', singleJobId] : null,
    () => fetchTranscriptJob(singleJobId as string),
    {
      refreshInterval: (latest) =>
        latest && ACTIVE_STATUSES.has(latest.status) ? 1200 : 0,
      revalidateOnFocus: true
    }
  );

  // Historical Batches
  const { data: batchHistory, mutate: mutateHistory } = useSWR<PlaylistBatchSummary[]>(
    authenticated && activeTab === 'history' && historySubTab === 'batches' ? 'playlist-batches-history' : null,
    () => fetchPlaylistBatches(30),
    { revalidateOnFocus: true }
  );

  // Historical Single & Batch Transcripts
  const { data: recentJobs, mutate: mutateRecentJobs } = useSWR<TranscriptJob[]>(
    authenticated && activeTab === 'history' && historySubTab === 'videos' ? 'recent-transcripts-history' : null,
    () => fetchRecentTranscriptJobs(50),
    { revalidateOnFocus: true }
  );

  const allSelected = analysis && selected.size === analysis.videos.length;
  const completedCount = batch?.completed_videos ?? 0;
  const totalCount = batch?.total_videos ?? 0;
  const overallProgress = totalCount
    ? Math.round(((completedCount + (batch?.failed_videos ?? 0)) / totalCount) * 100)
    : 0;

  const handleAnalyse = () => {
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await analysePlaylist(playlistUrl);
        setAnalysis(result);
        setSelected(new Set(result.videos.map((v) => v.video_id)));
        setBatchId(null);
        setMessage({
          text: `Analyzed playlist "${result.title || 'Untitled'}". Found ${result.videos.length} videos.`,
          type: 'success'
        });
      } catch (error) {
        setMessage({
          text: error instanceof Error ? error.message : 'Unable to analyze this playlist.',
          type: 'error'
        });
      }
    });
  };

  const handleQueueBatch = () => {
    if (!analysis || selected.size === 0) return;
    if (!authorisedConsent) {
      setMessage({ text: 'Please confirm the authorization checkbox to proceed.', type: 'error' });
      return;
    }
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await createPlaylistBatch({
          playlist_url: analysis.playlist_url,
          selected_video_ids: [...selected],
          engine,
          language_code: languageCode,
          mode: sarvamMode
        });
        setBatchId(result.id);
        localStorage.setItem('yt_active_batch_id', result.id);
        setMessage({
          text: `Queued ${result.total_videos} videos with ${engine.toUpperCase()} engine.`,
          type: 'success'
        });
      } catch (error) {
        setMessage({
          text: error instanceof Error ? error.message : 'Unable to start the transcription batch.',
          type: 'error'
        });
      }
    });
  };

  const handleSingleTranscribe = () => {
    if (!singleVideoUrl.trim()) return;
    if (!authorisedConsent) {
      setMessage({ text: 'Please confirm the authorization checkbox to proceed.', type: 'error' });
      return;
    }
    setMessage(null);
    startTransition(async () => {
      try {
        const job = await createSingleTranscriptJob({
          video_url: singleVideoUrl.trim(),
          engine,
          language_code: languageCode,
          mode: sarvamMode
        });
        setSingleJobId(job.id);
        localStorage.setItem('yt_active_single_job_id', job.id);
        await mutateSingleJob();
        setMessage({
          text: `Single video queued for transcription with ${engine.toUpperCase()} engine!`,
          type: 'success'
        });
      } catch (error) {
        setMessage({
          text: error instanceof Error ? error.message : 'Unable to start single transcription.',
          type: 'error'
        });
      }
    });
  };

  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(analysis?.videos.map((v) => v.video_id)));

  const retry = async (jobId: string) => {
    try {
      await retryTranscriptJob(jobId);
      await mutateBatch();
      await mutateSingleJob();
      await mutateRecentJobs();
    } catch (error) {
      setMessage({
        text: error instanceof Error ? error.message : 'Unable to retry this transcript.',
        type: 'error'
      });
    }
  };

  const copyTranscript = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main className="min-h-screen bg-[#0d1117] text-slate-100 antialiased selection:bg-cyan-500/30">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header */}
        <header className="relative overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/70 to-slate-950/90 p-6 shadow-2xl backdrop-blur-xl lg:p-8">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-cyan-400">
                <Sparkles className="h-3.5 w-3.5" /> High Performance Speech-To-Text
              </div>
              <h1 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">
                Bulk YouTube Transcriber
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                Analyze playlists or individual videos, transcribe using <strong>Local Faster-Whisper (GPU)</strong> or <strong>Sarvam AI STT (Saaras v3 - 23 Indic Languages & English)</strong>, and export cleanly formatted TXT, SRT, VTT, and JSON files.
              </p>
            </div>
            {authenticated ? (
              <div className="flex items-center gap-2 self-start md:self-auto rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-2.5 text-xs text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
                <span>Operator Active</span>
              </div>
            ) : null}
          </div>
        </header>

        {sessionError ? (
          <div className="mt-6 flex items-center gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
            <AlertCircle className="h-5 w-5 shrink-0 text-rose-400" />
            <span>The dashboard cannot connect to the FastAPI backend at <code>http://localhost:8000/api/v1</code>.</span>
          </div>
        ) : null}

        <OperatorAccessPanel session={session} onSessionChange={() => void mutateSession()} />

        {!authenticated ? (
          <div className="mt-8 rounded-3xl border border-white/10 bg-slate-900/40 p-8 text-center backdrop-blur">
            <ShieldCheck className="mx-auto h-12 w-12 text-slate-500" />
            <h3 className="mt-3 text-lg font-medium text-white">Sign In to Transcribe</h3>
            <p className="mt-1 text-sm text-slate-400">
              Sign in with your operator credentials above to start analyzing playlists and queueing transcription jobs.
            </p>
          </div>
        ) : (
          <div className="mt-8 space-y-6">
            {/* Top Navigation Tabs */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
              <div className="flex gap-2 rounded-2xl border border-white/10 bg-slate-900/60 p-1 backdrop-blur">
                <button
                  type="button"
                  onClick={() => setActiveTab('playlist')}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
                    activeTab === 'playlist'
                      ? 'bg-cyan-500 text-slate-950 shadow-md font-semibold'
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <ListVideo className="h-4 w-4" /> Bulk Playlist
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('single')}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
                    activeTab === 'single'
                      ? 'bg-cyan-500 text-slate-950 shadow-md font-semibold'
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Video className="h-4 w-4" /> Single Video
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('history')}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
                    activeTab === 'history'
                      ? 'bg-cyan-500 text-slate-950 shadow-md font-semibold'
                      : 'text-slate-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <History className="h-4 w-4" /> Batch History
                </button>
              </div>

              {/* Status Alert Messages */}
              {message ? (
                <div
                  className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-xs font-medium ${
                    message.type === 'success'
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      : message.type === 'error'
                      ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                      : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
                  }`}
                >
                  <span>{message.text}</span>
                  <button type="button" onClick={() => setMessage(null)} className="ml-1 opacity-70 hover:opacity-100">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : null}
            </div>

            {/* Transcription Engine & Settings Card */}
            <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-4">
                <div>
                  <h3 className="text-base font-semibold text-white flex items-center gap-2">
                    <Layers className="h-4 w-4 text-cyan-400" /> Transcription Engine & Model
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Select your speech recognition provider, language, and translation options.
                  </p>
                </div>
              </div>

              {/* Engine Selection Tiles */}
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {/* Local Faster-Whisper */}
                <button
                  type="button"
                  onClick={() => setEngine('local_whisper')}
                  className={`flex flex-col items-start rounded-2xl border p-4 text-left transition ${
                    engine === 'local_whisper'
                      ? 'border-cyan-500 bg-cyan-500/10 ring-1 ring-cyan-500'
                      : 'border-white/10 bg-slate-950/40 hover:border-white/20'
                  }`}
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-cyan-400">
                      <Server className="h-3.5 w-3.5" /> Local Faster-Whisper
                    </span>
                    <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-300">GPU / CPU</span>
                  </div>
                  <p className="mt-2 text-xs text-slate-300 font-medium">Free & Offline CTranslate2</p>
                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
                    Runs on your RTX 3050. No external API keys or cost required.
                  </p>
                </button>

                {/* Sarvam AI STT */}
                <button
                  type="button"
                  onClick={() => setEngine('sarvam')}
                  className={`flex flex-col items-start rounded-2xl border p-4 text-left transition ${
                    engine === 'sarvam'
                      ? 'border-amber-400 bg-amber-400/10 ring-1 ring-amber-400'
                      : 'border-white/10 bg-slate-950/40 hover:border-white/20'
                  }`}
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-400">
                      <Globe className="h-3.5 w-3.5" /> Sarvam AI STT
                    </span>
                    <span className="rounded bg-amber-400/20 px-1.5 py-0.5 text-[10px] text-amber-300 font-semibold">
                      saaras:v3
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-slate-300 font-medium">23 Indic Languages & Translation</p>
                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
                    Industry leading accuracy for Hindi, Tamil, Bengali, Telugu, Hinglish + English.
                  </p>
                </button>

                {/* Groq Cloud Whisper */}
                <button
                  type="button"
                  onClick={() => setEngine('groq')}
                  className={`flex flex-col items-start rounded-2xl border p-4 text-left transition ${
                    engine === 'groq'
                      ? 'border-purple-400 bg-purple-400/10 ring-1 ring-purple-400'
                      : 'border-white/10 bg-slate-950/40 hover:border-white/20'
                  }`}
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-purple-400">
                      <Flame className="h-3.5 w-3.5" /> Groq Cloud Whisper
                    </span>
                    <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-slate-300">Fast Cloud</span>
                  </div>
                  <p className="mt-2 text-xs text-slate-300 font-medium">Whisper Large v3 Turbo</p>
                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
                    High speed LPU cloud transcription. Requires Groq API Key.
                  </p>
                </button>
              </div>

              {/* Language & Output Mode Controls */}
              <div className="mt-4 grid gap-3 sm:grid-cols-2 pt-2">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Audio Language
                  </label>
                  <select
                    value={languageCode}
                    onChange={(e) => setLanguageCode(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-950 px-3.5 py-2.5 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                  >
                    {INDIC_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.name} {lang.nativeName !== lang.name ? `(${lang.nativeName})` : ''}
                      </option>
                    ))}
                  </select>
                </div>

                {engine === 'sarvam' ? (
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">
                      Sarvam Output Mode
                    </label>
                    <select
                      value={sarvamMode}
                      onChange={(e) => setSarvamMode(e.target.value as SarvamMode)}
                      className="w-full rounded-xl border border-white/10 bg-slate-950 px-3.5 py-2.5 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="transcribe">Standard Transcription (Native Script)</option>
                      <option value="translate">Translate to English (Indic Speech → English Text)</option>
                      <option value="verbatim">Verbatim (Exact Word-For-Word with Fillers)</option>
                      <option value="codemix">Code-Mixed (Natural Script / Hinglish)</option>
                      <option value="translit">Transliteration (Romanized Script)</option>
                    </select>
                  </div>
                ) : null}
              </div>
            </section>

            {/* TAB 1: BULK PLAYLIST TRANSCRIBER */}
            {activeTab === 'playlist' ? (
              <>
                {/* Step 1: Input Playlist URL */}
                <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-cyan-400">
                    <span>1. Analyze YouTube Playlist</span>
                  </div>
                  <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                    <input
                      type="url"
                      value={playlistUrl}
                      onChange={(e) => setPlaylistUrl(e.target.value)}
                      placeholder="https://www.youtube.com/playlist?list=PL..."
                      className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3.5 text-sm text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={handleAnalyse}
                      disabled={!playlistUrl.trim() || isPending}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 px-6 py-3.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
                    >
                      {isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                      Analyze Playlist
                    </button>
                  </div>
                </section>

                {/* Step 2: Select Videos & Start Queue */}
                {analysis ? (
                  <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-4">
                      <div>
                        <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">
                          2. Select Authorized Videos
                        </span>
                        <h2 className="mt-1 text-xl font-bold text-white">{analysis.title || 'YouTube Playlist'}</h2>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {analysis.videos.length} videos found · {selected.size} selected for transcription
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={toggleAll}
                          className="rounded-xl border border-white/10 bg-slate-950/60 px-3.5 py-2 text-xs font-medium text-slate-300 hover:text-white"
                        >
                          {allSelected ? 'Clear All' : 'Select All'}
                        </button>
                        <button
                          type="button"
                          onClick={handleQueueBatch}
                          disabled={selected.size === 0 || isPending || !authorisedConsent}
                          className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-2 text-xs font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
                        >
                          <ShieldCheck className="h-4 w-4" />
                          Queue Batch ({selected.size})
                        </button>
                      </div>
                    </div>

                    {/* Legal Attestation */}
                    <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border border-amber-400/20 bg-amber-400/5 p-3.5 text-xs text-amber-200/90">
                      <input
                        type="checkbox"
                        checked={authorisedConsent}
                        onChange={(e) => setAuthorisedConsent(e.target.checked)}
                        className="mt-0.5 h-4 w-4 rounded border-white/20 bg-slate-950 accent-cyan-500"
                      />
                      <span>
                        I confirm that I own or am authorized to process and transcribe audio from the selected videos in compliance with content terms and privacy guidelines.
                      </span>
                    </label>

                    {/* Video Selection Grid / List */}
                    <div className="mt-4 max-h-[480px] space-y-2 overflow-y-auto pr-1">
                      {analysis.videos.map((video) => {
                        const isChecked = selected.has(video.video_id);
                        return (
                          <label
                            key={video.video_id}
                            className={`flex cursor-pointer items-center gap-3.5 rounded-2xl border p-3 transition ${
                              isChecked
                                ? 'border-cyan-500/40 bg-cyan-500/5'
                                : 'border-white/5 bg-slate-950/40 hover:border-white/15'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() =>
                                setSelected((cur) => {
                                  const next = new Set(cur);
                                  next.has(video.video_id) ? next.delete(video.video_id) : next.add(video.video_id);
                                  return next;
                                })
                              }
                              className="h-4 w-4 rounded border-white/20 bg-slate-950 accent-cyan-500"
                            />
                            {video.thumbnail_url ? (
                              <img
                                src={video.thumbnail_url}
                                alt=""
                                className="h-12 w-20 shrink-0 rounded-lg object-cover bg-slate-800"
                              />
                            ) : (
                              <div className="flex h-12 w-20 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-slate-600">
                                <Video className="h-5 w-5" />
                              </div>
                            )}
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium text-white">{video.title}</p>
                              <p className="text-xs text-slate-400 mt-0.5">
                                {video.channel_title || 'Unknown Channel'} · {durationLabel(video.duration_seconds)}
                              </p>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </section>
                ) : null}

                {/* Step 3: Active Batch Progress */}
                {batch ? (
                  <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400">
                            Active Batch
                          </span>
                          <span className="rounded-full border border-white/10 bg-slate-950 px-2 py-0.5 text-[10px] text-slate-300 font-mono">
                            {batch.engine?.toUpperCase()}
                          </span>
                        </div>
                        <h2 className="mt-1 text-xl font-bold text-white">{batch.title || 'Playlist Batch'}</h2>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {completedCount} of {totalCount} completed · {batch.failed_videos} failed
                        </p>
                      </div>
                      <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${statusStyle(batch.status as any)}`}>
                        {batch.status}
                      </span>
                    </div>

                    {/* Progress Bar */}
                    <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-slate-950">
                      <div
                        className="h-full bg-gradient-to-r from-cyan-500 via-emerald-400 to-lime-400 transition-all duration-500"
                        style={{ width: `${overallProgress}%` }}
                      />
                    </div>

                    {/* Job Items */}
                    <div className="mt-5 space-y-2.5">
                      {batch.jobs.map((job) => (
                        <TranscriptRow
                          key={job.id}
                          job={job}
                          onRetry={retry}
                          onPreview={(j) => setPreviewJob(j)}
                        />
                      ))}
                    </div>
                  </section>
                ) : null}
              </>
            ) : null}

            {/* TAB 2: SINGLE VIDEO TRANSCRIBER */}
            {activeTab === 'single' ? (
              <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-cyan-400">
                  <Video className="h-4 w-4" /> Direct Single Video Transcription
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  Paste any direct YouTube video URL to start immediate transcription without needing a playlist.
                </p>

                <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                  <input
                    type="url"
                    value={singleVideoUrl}
                    onChange={(e) => setSingleVideoUrl(e.target.value)}
                    placeholder="https://www.youtube.com/watch?v=..."
                    className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3.5 text-sm text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleSingleTranscribe}
                    disabled={!singleVideoUrl.trim() || isPending || !authorisedConsent}
                    className="inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 px-6 py-3.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
                  >
                    {isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    Start Transcribing
                  </button>
                </div>

                <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border border-amber-400/20 bg-amber-400/5 p-3.5 text-xs text-amber-200/90">
                  <input
                    type="checkbox"
                    checked={authorisedConsent}
                    onChange={(e) => setAuthorisedConsent(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-white/20 bg-slate-950 accent-cyan-500"
                  />
                  <span>
                    I confirm that I have permission to acquire and process this YouTube video.
                  </span>
                </label>

                {polledSingleJob ? (
                  <div className="mt-6 border-t border-white/10 pt-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
                        <Sparkles className="h-3.5 w-3.5" /> Active Single Video Task
                      </h4>
                      <button
                        type="button"
                        onClick={() => {
                          setSingleJobId(null);
                          localStorage.removeItem('yt_active_single_job_id');
                        }}
                        className="text-xs text-slate-400 hover:text-slate-200 transition"
                      >
                        Clear Task
                      </button>
                    </div>
                    <TranscriptRow
                      job={polledSingleJob}
                      onRetry={retry}
                      onPreview={(j) => setPreviewJob(j)}
                    />
                  </div>
                ) : null}
              </section>
            ) : null}

            {/* TAB 3: BATCH & VIDEO HISTORY */}
            {activeTab === 'history' ? (
              <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-4">
                  <div>
                    <h3 className="text-base font-semibold text-white flex items-center gap-2">
                      <History className="h-4 w-4 text-cyan-400" /> Transcription History
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      View all previously transcribed single videos and playlist batches.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Sub-tab Switcher */}
                    <div className="inline-flex rounded-xl border border-white/10 bg-slate-950/80 p-1">
                      <button
                        type="button"
                        onClick={() => setHistorySubTab('videos')}
                        className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                          historySubTab === 'videos'
                            ? 'bg-cyan-500 text-slate-950'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        Single Videos ({recentJobs?.length ?? 0})
                      </button>
                      <button
                        type="button"
                        onClick={() => setHistorySubTab('batches')}
                        className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                          historySubTab === 'batches'
                            ? 'bg-cyan-500 text-slate-950'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        Playlist Batches ({batchHistory?.length ?? 0})
                      </button>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        void mutateHistory();
                        void mutateRecentJobs();
                      }}
                      className="rounded-xl border border-white/10 bg-slate-950/60 p-2 text-slate-300 hover:text-white"
                      title="Refresh History"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Subtab 1: Recent Single Videos */}
                {historySubTab === 'videos' ? (
                  <div className="mt-4 space-y-2.5">
                    {recentJobs && recentJobs.length > 0 ? (
                      recentJobs.map((job) => (
                        <TranscriptRow
                          key={job.id}
                          job={job}
                          onRetry={retry}
                          onPreview={(j) => setPreviewJob(j)}
                        />
                      ))
                    ) : (
                      <p className="text-center py-8 text-xs text-slate-500">
                        No previous single video transcriptions found.
                      </p>
                    )}
                  </div>
                ) : null}

                {/* Subtab 2: Playlist Batches */}
                {historySubTab === 'batches' ? (
                  <div className="mt-4 space-y-2.5">
                    {batchHistory && batchHistory.length > 0 ? (
                      batchHistory.map((item) => (
                        <div
                          key={item.id}
                          className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-white/5 bg-slate-950/50 p-4 hover:border-cyan-500/30 transition"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-sm text-white truncate">
                                {item.title || 'Untitled Batch'}
                              </span>
                              <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] text-slate-300 font-mono">
                                {item.engine?.toUpperCase() || 'LOCAL_WHISPER'}
                              </span>
                            </div>
                            <p className="text-xs text-slate-400 mt-1">
                              {item.completed_videos} / {item.total_videos} videos completed · Created on{' '}
                              {new Date(item.created_at).toLocaleDateString()}
                            </p>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusStyle(item.status as any)}`}>
                              {item.status}
                            </span>
                            <button
                              type="button"
                              onClick={() => {
                                setBatchId(item.id);
                                localStorage.setItem('yt_active_batch_id', item.id);
                                setActiveTab('playlist');
                              }}
                              className="rounded-xl bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-400 transition"
                            >
                              Open Batch
                            </button>
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-center py-8 text-xs text-slate-500">
                        No previous batches found.
                      </p>
                    )}
                  </div>
                ) : null}
              </section>
            ) : null}
          </div>
        )}
      </div>

      {/* TRANSCRIPT PREVIEW MODAL */}
      {previewJob ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="relative flex max-h-[85vh] w-full max-w-4xl flex-col rounded-3xl border border-white/10 bg-slate-900 shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-white/10 p-5">
              <div className="min-w-0 pr-4">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-cyan-500/20 px-2.5 py-0.5 text-[11px] font-semibold text-cyan-300 font-mono">
                    {previewJob.engine?.toUpperCase() || 'LOCAL_WHISPER'}
                  </span>
                  {previewJob.language ? (
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">
                      Lang: {previewJob.language}
                    </span>
                  ) : null}
                </div>
                <h3 className="mt-2 text-lg font-bold text-white truncate">{previewJob.title}</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {previewJob.channel_title || 'Unknown channel'} · {durationLabel(previewJob.duration_seconds)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setPreviewJob(null);
                  setSearchQuery('');
                }}
                className="rounded-full border border-white/10 p-2 text-slate-400 hover:text-white hover:bg-white/10 transition"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Actions Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-slate-950/60 px-5 py-3">
              <div className="relative flex-1 min-w-[200px]">
                <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search in transcript text..."
                  className="w-full rounded-xl border border-white/10 bg-slate-900 pl-9 pr-4 py-1.5 text-xs text-white placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => copyTranscript(previewJob.transcript_text || '')}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 transition"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? 'Copied' : 'Copy All'}
                </button>

                {/* Export Direct Downloads */}
                {(['txt', 'srt', 'vtt', 'json'] as const).map((fmt) => (
                  <a
                    key={fmt}
                    href={transcriptExportUrl(previewJob.id, fmt)}
                    download
                    className="inline-flex items-center gap-1 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 transition"
                  >
                    <Download className="h-3.5 w-3.5" />
                    {fmt.toUpperCase()}
                  </a>
                ))}
              </div>
            </div>

            {/* Modal Transcript Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-3 font-mono text-xs">
              {previewJob.segments && previewJob.segments.length > 0 ? (
                previewJob.segments
                  .filter((seg) => !searchQuery || seg.text.toLowerCase().includes(searchQuery.toLowerCase()))
                  .map((seg, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-white/5 bg-slate-950/40 p-3 hover:border-cyan-500/20 transition flex flex-col sm:flex-row sm:items-start gap-3"
                    >
                      <span className="shrink-0 rounded bg-cyan-500/10 px-2 py-0.5 text-[11px] text-cyan-400 font-semibold">
                        {Math.floor(seg.start / 60)}:{String(Math.floor(seg.start % 60)).padStart(2, '0')} -{' '}
                        {Math.floor(seg.end / 60)}:{String(Math.floor(seg.end % 60)).padStart(2, '0')}
                      </span>
                      <p className="text-slate-200 leading-relaxed">{seg.text}</p>
                    </div>
                  ))
              ) : previewJob.transcript_text ? (
                <div className="whitespace-pre-wrap rounded-2xl bg-slate-950/60 p-4 text-slate-300 leading-6">
                  {previewJob.transcript_text}
                </div>
              ) : (
                <p className="text-center py-10 text-slate-500">No transcript text available yet.</p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function TranscriptRow({
  job,
  onRetry,
  onPreview
}: {
  job: TranscriptJob;
  onRetry: (id: string) => void;
  onPreview: (job: TranscriptJob) => void;
}) {
  const isActive = ACTIVE_STATUSES.has(job.status);

  return (
    <article className="rounded-2xl border border-white/10 bg-slate-950/60 p-4 transition hover:border-white/20">
      <div className="flex flex-col gap-3 md:flex-row md:items-center justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate font-semibold text-sm text-white">{job.title}</p>
            {job.engine ? (
              <span className="rounded bg-white/10 px-1.5 py-0.2 text-[10px] text-slate-300 font-mono">
                {job.engine}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {job.channel_title || 'Unknown channel'} · {durationLabel(job.duration_seconds)}
            {job.language ? ` · ${job.language}` : ''}
            {job.stage_detail ? <span className="text-cyan-400"> · {job.stage_detail}</span> : null}
          </p>
        </div>

        <div className="flex items-center gap-2 self-start md:self-auto">
          <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${statusStyle(job.status)}`}>
            {job.status} {isActive ? `${job.progress}%` : ''}
          </span>
        </div>
      </div>

      {/* Progress Bar for Active Tasks */}
      {isActive ? (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-900">
          <div className="h-full bg-cyan-400 transition-all duration-300" style={{ width: `${job.progress}%` }} />
        </div>
      ) : null}

      {job.error_summary ? (
        <p className="mt-2.5 rounded-xl border border-rose-500/20 bg-rose-500/10 p-2.5 text-xs text-rose-200">
          {job.error_summary}
        </p>
      ) : null}

      {/* Completed Actions & Exports */}
      {job.status === 'COMPLETED' ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
          <button
            type="button"
            onClick={() => onPreview(job)}
            className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400 transition"
          >
            <Eye className="h-3.5 w-3.5" /> View Transcript
          </button>

          {(['txt', 'srt', 'vtt', 'json'] as const).map((fmt) => (
            <a
              key={fmt}
              href={transcriptExportUrl(job.id, fmt)}
              download
              className="inline-flex items-center gap-1 rounded-xl border border-white/10 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-cyan-500/40 hover:text-white transition"
            >
              <Download className="h-3 w-3 text-cyan-400" />
              {fmt.toUpperCase()}
            </a>
          ))}
        </div>
      ) : null}

      {job.status === 'FAILED' ? (
        <button
          type="button"
          onClick={() => onRetry(job.id)}
          className="mt-3 inline-flex items-center gap-1.5 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-400/20 transition"
        >
          <RefreshCw className="h-3 w-3" /> Retry Task
        </button>
      ) : null}
    </article>
  );
}
