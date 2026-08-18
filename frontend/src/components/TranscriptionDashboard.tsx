'use client';

import { useEffect, useMemo, useState, useTransition } from 'react';
import useSWR from 'swr';
import {
  AlertCircle,
  Archive,
  BookOpen,
  Check,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FileCheck,
  FileText,
  Flame,
  Globe,
  History,
  Layers,
  ListOrdered,
  ListVideo,
  LoaderCircle,
  Pause,
  Play,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Square,
  Trash2,
  Video,
  Wand2,
  X
} from 'lucide-react';

import { OperatorAccessPanel } from '@/components/OperatorAccessPanel';
import {
  analysePlaylist,
  cancelPlaylistBatch,
  cancelTranscriptJob,
  createPlaylistBatch,
  createSingleTranscriptJob,
  deletePlaylistBatch,
  deleteTranscriptJob,
  downloadPlaylistBatchZip,
  fetchOperatorSession,
  fetchPlaylistBatch,
  fetchPlaylistBatches,
  fetchRecentTranscriptJobs,
  fetchTranscriptJob,
  pausePlaylistBatch,
  pauseTranscriptJob,
  resumePlaylistBatch,
  resumeTranscriptJob,
  retryFailedPlaylistBatch,
  retryTranscriptJob,
  runAiCleaner,
  runAiSummarizer,
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

const ACTIVE_STATUSES = new Set(['PENDING', 'ACQUIRING', 'TRANSCRIBING', 'CLEANING', 'SUMMARIZING', 'EXPORTING']);

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
  if (status === 'PAUSED') return 'border-amber-400/30 bg-amber-400/10 text-amber-300';
  if (status === 'CANCELLED') return 'border-slate-500/30 bg-slate-500/10 text-slate-400';
  if (status === 'CLEANING' || status === 'SUMMARIZING') return 'border-purple-500/30 bg-purple-500/10 text-purple-300 animate-pulse';
  if (status === 'TRANSCRIBING') return 'border-cyan-400/30 bg-cyan-400/10 text-cyan-300 animate-pulse';
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

  // AI Agent Toggles
  const [enableAiCleanup, setEnableAiCleanup] = useState(true);
  const [enableAiSummary, setEnableAiSummary] = useState(true);

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
  const [modalTab, setModalTab] = useState<'raw' | 'clean' | 'summary'>('clean');
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

  // Live Preview Job Polling (if modal open on an active job)
  const { data: liveModalJob, mutate: mutateModalJob } = useSWR<TranscriptJob>(
    authenticated && previewJob?.id ? ['preview-job', previewJob.id] : null,
    () => fetchTranscriptJob(previewJob!.id),
    {
      refreshInterval: (latest) =>
        latest && ACTIVE_STATUSES.has(latest.status) ? 1500 : 0,
      revalidateOnFocus: false
    }
  );
  const activePreviewJob = liveModalJob ?? previewJob;

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
          text: `Analyzed "${result.title || 'Playlist'}". Found ${result.videos.length} videos.`,
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
          mode: sarvamMode,
          enable_ai_cleanup: enableAiCleanup,
          enable_ai_summary: enableAiSummary
        });
        setBatchId(result.id);
        localStorage.setItem('yt_active_batch_id', result.id);
        setMessage({
          text: `Queued ${result.total_videos} videos with ${engine.toUpperCase()} engine!`,
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
          mode: sarvamMode,
          enable_ai_cleanup: enableAiCleanup,
          enable_ai_summary: enableAiSummary
        });
        setSingleJobId(job.id);
        localStorage.setItem('yt_active_single_job_id', job.id);
        await mutateSingleJob();
        setMessage({
          text: `Single video queued with ${engine.toUpperCase()} engine!`,
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

  const handleRetryJob = async (jobId: string) => {
    try {
      await retryTranscriptJob(jobId);
      await mutateBatch();
      await mutateSingleJob();
      await mutateRecentJobs();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Retry failed.', type: 'error' });
    }
  };

  const handlePauseJob = async (jobId: string) => {
    try {
      await pauseTranscriptJob(jobId);
      await mutateBatch();
      await mutateSingleJob();
      await mutateRecentJobs();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Pause failed.', type: 'error' });
    }
  };

  const handleResumeJob = async (jobId: string) => {
    try {
      await resumeTranscriptJob(jobId);
      await mutateBatch();
      await mutateSingleJob();
      await mutateRecentJobs();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Resume failed.', type: 'error' });
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      await cancelTranscriptJob(jobId);
      await mutateBatch();
      await mutateSingleJob();
      await mutateRecentJobs();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Cancel failed.', type: 'error' });
    }
  };

  const handlePauseBatch = async (bId: string) => {
    try {
      await pausePlaylistBatch(bId);
      await mutateBatch();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Pause batch failed.', type: 'error' });
    }
  };

  const handleResumeBatch = async (bId: string) => {
    try {
      await resumePlaylistBatch(bId);
      await mutateBatch();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Resume batch failed.', type: 'error' });
    }
  };

  const handleCancelBatch = async (bId: string) => {
    try {
      await cancelPlaylistBatch(bId);
      await mutateBatch();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Cancel batch failed.', type: 'error' });
    }
  };

  const handleRetryFailedBatch = async (bId: string) => {
    try {
      await retryFailedPlaylistBatch(bId);
      await mutateBatch();
      if (activeTab === 'history') {
        await mutateHistory();
      }
      setMessage({ text: 'All failed videos re-queued for transcription!', type: 'success' });
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Retry failed videos failed.', type: 'error' });
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      await deleteTranscriptJob(jobId);
      if (polledSingleJob?.id === jobId) {
        setSingleJobId(null);
        localStorage.removeItem('yt_active_single_job_id');
      }
      if (previewJob?.id === jobId) {
        setPreviewJob(null);
      }
      await mutateBatch();
      await mutateSingleJob();
      await mutateRecentJobs();
      setMessage({ text: 'Job removed.', type: 'info' });
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Delete job failed.', type: 'error' });
    }
  };

  const handleDeleteBatch = async (bId: string) => {
    try {
      await deletePlaylistBatch(bId);
      if (batchId === bId) {
        setBatchId(null);
        localStorage.removeItem('yt_active_batch_id');
      }
      await mutateBatch();
      await mutateHistory();
      await mutateRecentJobs();
      setMessage({ text: 'Playlist batch deleted.', type: 'info' });
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Delete batch failed.', type: 'error' });
    }
  };

  const handleTriggerCleaner = async (jobId: string) => {
    try {
      await runAiCleaner(jobId);
      await mutateModalJob();
      await mutateSingleJob();
      await mutateBatch();
      await mutateRecentJobs();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Cleanup trigger failed.', type: 'error' });
    }
  };

  const handleTriggerSummarizer = async (jobId: string) => {
    try {
      await runAiSummarizer(jobId);
      await mutateModalJob();
      await mutateSingleJob();
      await mutateBatch();
      await mutateRecentJobs();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Summarizer trigger failed.', type: 'error' });
    }
  };

  const copyText = (text: string) => {
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
                <Sparkles className="h-3.5 w-3.5" /> High Performance Speech-To-Text & AI Agents
              </div>
              <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                YouTube Automation Hub
              </h1>
              <p className="mt-2 text-sm text-slate-400">
                Local GPU Faster-Whisper, Sarvam AI Indic STT, AI Stutter/Filler Cleanup, and Executive Summarization.
              </p>
            </div>

            {/* Top Navigation Tabs */}
            <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-slate-950/80 p-1.5 backdrop-blur-md">
              <button
                type="button"
                onClick={() => setActiveTab('playlist')}
                className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
                  activeTab === 'playlist'
                    ? 'bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/20'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                <ListVideo className="h-4 w-4" /> Bulk Playlist
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('single')}
                className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
                  activeTab === 'single'
                    ? 'bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/20'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                <Video className="h-4 w-4" /> Single Video
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('history')}
                className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
                  activeTab === 'history'
                    ? 'bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/20'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                <History className="h-4 w-4" /> History
              </button>
            </div>
          </div>
        </header>

        {/* Global Notification Banner */}
        {message ? (
          <div
            className={`mt-6 flex items-center gap-3 rounded-2xl border px-4 py-3 text-xs font-medium shadow-lg transition-all ${
              message.type === 'error'
                ? 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                : message.type === 'success'
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-300'
            }`}
          >
            {message.type === 'error' ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
            <p className="flex-1">{message.text}</p>
            <button type="button" onClick={() => setMessage(null)} className="text-slate-400 hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : null}

        {/* Main Content Area */}
        {!authenticated ? (
          <div className="mt-8">
            <OperatorAccessPanel session={session} onSessionChange={() => void mutateSession()} />
          </div>
        ) : (
          <div className="mt-8 space-y-8">
            {/* COMMON ENGINE & AI AGENT CONFIGURATION PANEL */}
            {activeTab !== 'history' ? (
              <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-cyan-400 flex items-center gap-2">
                  <Flame className="h-4 w-4" /> Step 1: Transcription Engine & AI Agent Settings
                </h3>

                {/* Engine Cards */}
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div
                    onClick={() => setEngine('local_whisper')}
                    className={`cursor-pointer rounded-2xl border p-4 transition ${
                      engine === 'local_whisper'
                        ? 'border-cyan-500 bg-cyan-500/10 shadow-lg shadow-cyan-500/10'
                        : 'border-white/5 bg-slate-950/40 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white text-sm">Local Whisper (Large v3 Turbo)</span>
                      <Server className="h-4 w-4 text-cyan-400" />
                    </div>
                    <p className="mt-1.5 text-xs text-slate-400">
                      NVIDIA RTX 3050 GPU CTranslate2 INT8 acceleration. Zero-hallucination VAD, 100% private, free & offline.
                    </p>
                  </div>

                  <div
                    onClick={() => setEngine('sarvam')}
                    className={`cursor-pointer rounded-2xl border p-4 transition ${
                      engine === 'sarvam'
                        ? 'border-emerald-500 bg-emerald-500/10 shadow-lg shadow-emerald-500/10'
                        : 'border-white/5 bg-slate-950/40 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white text-sm">Sarvam AI (saaras:v3)</span>
                      <Globe className="h-4 w-4 text-emerald-400" />
                    </div>
                    <p className="mt-1.5 text-xs text-slate-400">
                      State of the art for 23 Indian Indic languages + Indian English translation.
                    </p>
                  </div>

                  <div
                    onClick={() => setEngine('groq')}
                    className={`cursor-pointer rounded-2xl border p-4 transition ${
                      engine === 'groq'
                        ? 'border-amber-500 bg-amber-500/10 shadow-lg shadow-amber-500/10'
                        : 'border-white/5 bg-slate-950/40 hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white text-sm">Groq Cloud Whisper</span>
                      <Flame className="h-4 w-4 text-amber-400" />
                    </div>
                    <p className="mt-1.5 text-xs text-slate-400">
                      Ultra-fast Whisper Large v3 Turbo on Groq LPUs.
                    </p>
                  </div>
                </div>

                {/* Engine Specific Options (Sarvam Language / Mode) */}
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">
                      Language Code / Audio Dialect
                    </label>
                    <select
                      value={languageCode}
                      onChange={(e) => setLanguageCode(e.target.value)}
                      className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-xs text-white focus:border-cyan-500 focus:outline-none"
                    >
                      {INDIC_LANGUAGES.map((lang) => (
                        <option key={lang.code} value={lang.code}>
                          {lang.name} ({lang.nativeName}) - {lang.code}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1.5">
                      Transcription Output Mode
                    </label>
                    <select
                      value={sarvamMode}
                      onChange={(e) => setSarvamMode(e.target.value as SarvamMode)}
                      className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-xs text-white focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="transcribe">Standard Transcribe (Native Script)</option>
                      <option value="translate">Direct English Translation (Indic speech → English text)</option>
                      <option value="verbatim">Verbatim (Include all pauses & filler words)</option>
                      <option value="codemix">Code-Mixed (Hinglish/Tanglish natural mix)</option>
                      <option value="translit">Transliteration (Romanized English letters)</option>
                    </select>
                  </div>
                </div>

                {/* AI POST-PROCESSING AGENTS TOGGLES */}
                <div className="mt-6 border-t border-white/10 pt-4">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-purple-400 mb-3 flex items-center gap-2">
                    <Wand2 className="h-4 w-4" /> Autonomous AI Agents Suite
                  </label>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <label
                      className={`flex cursor-pointer items-start gap-3 rounded-2xl border p-3.5 transition ${
                        enableAiCleanup
                          ? 'border-purple-500/40 bg-purple-500/10'
                          : 'border-white/5 bg-slate-950/40 hover:border-white/15'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={enableAiCleanup}
                        onChange={(e) => setEnableAiCleanup(e.target.checked)}
                        className="mt-1 h-4 w-4 rounded border-white/20 bg-slate-950 accent-purple-500"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-white">✨ AI Transcript Cleanup Agent</span>
                          <span className="rounded bg-purple-500/20 px-2 py-0.5 text-[10px] text-purple-300 font-semibold">Recommended</span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
                          Eliminates stuttering loops, filler words (uh, um, like), fixes grammar & punctuation, and aligns cleaned timestamps.
                        </p>
                      </div>
                    </label>

                    <label
                      className={`flex cursor-pointer items-start gap-3 rounded-2xl border p-3.5 transition ${
                        enableAiSummary
                          ? 'border-purple-500/40 bg-purple-500/10'
                          : 'border-white/5 bg-slate-950/40 hover:border-white/15'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={enableAiSummary}
                        onChange={(e) => setEnableAiSummary(e.target.checked)}
                        className="mt-1 h-4 w-4 rounded border-white/20 bg-slate-950 accent-purple-500"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-white">📑 AI Executive Summarizer Agent</span>
                          <span className="rounded bg-purple-500/20 px-2 py-0.5 text-[10px] text-purple-300 font-semibold">High Value</span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
                          Generates executive summary, bullet points, action items, chapter breakdown timestamps, and notable quotes.
                        </p>
                      </div>
                    </label>
                  </div>
                </div>
              </section>
            ) : null}

            {/* TAB 1: BULK PLAYLIST TRANSCRIBER */}
            {activeTab === 'playlist' ? (
              <>
                {/* Playlist URL Analyzer */}
                <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-cyan-400">
                    <ListVideo className="h-4 w-4" /> Bulk YouTube Playlist Transcription
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    Paste any public or unlisted YouTube playlist URL to scan all videos and batch-transcribe.
                  </p>

                  <div className="mt-4 flex flex-col gap-3 sm:flex-row">
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
                      {isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                      Analyze Playlist
                    </button>
                  </div>
                </section>

                {/* Playlist Analysis Video Selector */}
                {analysis ? (
                  <section className="rounded-3xl border border-white/10 bg-slate-900/60 p-6 shadow-xl backdrop-blur-md">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-4">
                      <div>
                        <h3 className="text-base font-bold text-white">{analysis.title || 'Untitled Playlist'}</h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {selected.size} of {analysis.videos.length} videos selected for transcription
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
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

                {/* Active Batch Progress */}
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

                      <div className="flex items-center gap-2.5">
                        <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusStyle(batch.status as any)}`}>
                          {batch.status}
                        </span>

                        <button
                          type="button"
                          onClick={() => downloadPlaylistBatchZip(batch.id, batch.title)}
                          disabled={completedCount === 0}
                          className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-3.5 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 transition shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
                          title="Download All Transcripts as a ZIP Archive"
                        >
                          <Archive className="h-3.5 w-3.5" />
                          <span>📦 Download ZIP</span>
                        </button>

                        {batch.failed_videos > 0 ? (
                          <button
                            type="button"
                            onClick={() => handleRetryFailedBatch(batch.id)}
                            className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/40 bg-rose-500/10 px-3.5 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-500/20 transition shadow-sm"
                            title="Automatically Retry All Failed Videos in this Batch"
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            <span>Retry Failed ({batch.failed_videos})</span>
                          </button>
                        ) : null}

                        {batch.status === 'PROCESSING' || batch.status === 'QUEUED' ? (
                          <button
                            type="button"
                            onClick={() => handlePauseBatch(batch.id)}
                            className="inline-flex items-center gap-1 rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-400/20 transition"
                          >
                            <Pause className="h-3.5 w-3.5" /> Pause Batch
                          </button>
                        ) : null}

                        {batch.status === 'PAUSED' ? (
                          <button
                            type="button"
                            onClick={() => handleResumeBatch(batch.id)}
                            className="inline-flex items-center gap-1 rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-400/20 transition"
                          >
                            <Play className="h-3.5 w-3.5" /> Resume Batch
                          </button>
                        ) : null}

                        {batch.status !== 'COMPLETED' && batch.status !== 'CANCELLED' ? (
                          <button
                            type="button"
                            onClick={() => handleCancelBatch(batch.id)}
                            className="inline-flex items-center gap-1 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-500/20 transition"
                          >
                            <Square className="h-3.5 w-3.5" /> Cancel Batch
                          </button>
                        ) : null}

                        <button
                          type="button"
                          onClick={() => handleDeleteBatch(batch.id)}
                          className="inline-flex items-center gap-1 rounded-xl border border-white/10 bg-slate-950/60 p-2 text-slate-400 hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300 transition"
                          title="Delete entire batch"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-slate-950">
                      <div
                        className="h-full bg-gradient-to-r from-cyan-500 via-emerald-400 to-lime-400 transition-all duration-500"
                        style={{ width: `${overallProgress}%` }}
                      />
                    </div>

                    {/* Batch Playlist Summary Report (if generated) */}
                    {batch.batch_summary_markdown ? (
                      <div className="mt-5 rounded-2xl border border-purple-500/30 bg-purple-500/5 p-4">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-purple-300 flex items-center gap-1.5 mb-2">
                          <BookOpen className="h-4 w-4" /> Master Playlist AI Synthesis
                        </h4>
                        <div className="whitespace-pre-wrap text-xs text-slate-300 leading-relaxed font-sans max-h-60 overflow-y-auto pr-2">
                          {batch.batch_summary_markdown}
                        </div>
                      </div>
                    ) : null}

                    {/* Job Items */}
                    <div className="mt-5 space-y-2.5">
                      {batch.jobs.map((job) => (
                        <TranscriptRow
                          key={job.id}
                          job={job}
                          onRetry={handleRetryJob}
                          onPause={handlePauseJob}
                          onResume={handleResumeJob}
                          onCancel={handleCancelJob}
                          onDelete={handleDeleteJob}
                          onPreview={(j) => {
                            setPreviewJob(j);
                            setModalTab(j.clean_transcript_text ? 'clean' : j.summary_markdown ? 'summary' : 'raw');
                          }}
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
                  Paste any direct YouTube video URL to start immediate transcription with AI cleanup and summary.
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
                      onRetry={handleRetryJob}
                      onPause={handlePauseJob}
                      onResume={handleResumeJob}
                      onCancel={handleCancelJob}
                      onDelete={handleDeleteJob}
                      onPreview={(j) => {
                        setPreviewJob(j);
                        setModalTab(j.clean_transcript_text ? 'clean' : j.summary_markdown ? 'summary' : 'raw');
                      }}
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
                          onRetry={handleRetryJob}
                          onPause={handlePauseJob}
                          onResume={handleResumeJob}
                          onCancel={handleCancelJob}
                          onDelete={handleDeleteJob}
                          onPreview={(j) => {
                            setPreviewJob(j);
                            setModalTab(j.clean_transcript_text ? 'clean' : j.summary_markdown ? 'summary' : 'raw');
                          }}
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
                          <div className="flex items-center gap-2">
                            <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusStyle(item.status as any)}`}>
                              {item.status}
                            </span>
                            {item.failed_videos > 0 ? (
                              <button
                                type="button"
                                onClick={() => handleRetryFailedBatch(item.id)}
                                className="inline-flex items-center gap-1 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-300 hover:bg-rose-500/20 transition"
                                title="Retry Failed Videos in this Batch"
                              >
                                <RefreshCw className="h-3.5 w-3.5" />
                                <span>Retry ({item.failed_videos})</span>
                              </button>
                            ) : null}
                            <button
                              type="button"
                              onClick={() => downloadPlaylistBatchZip(item.id, item.title)}
                              disabled={item.completed_videos === 0}
                              className="inline-flex items-center gap-1 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 transition disabled:opacity-40 disabled:cursor-not-allowed"
                              title="Download All Transcripts as ZIP"
                            >
                              <Archive className="h-3.5 w-3.5" />
                              <span>📦 Download ZIP</span>
                            </button>
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
                            <button
                              type="button"
                              onClick={() => handleDeleteBatch(item.id)}
                              className="rounded-xl border border-white/10 bg-slate-900 p-2 text-slate-400 hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300 transition"
                              title="Delete Batch"
                            >
                              <X className="h-4 w-4" />
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

      {/* ENHANCED MULTI-TAB TRANSCRIPT PREVIEW MODAL */}
      {activePreviewJob ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col rounded-3xl border border-white/10 bg-slate-900 shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-white/10 p-5">
              <div className="min-w-0 pr-4">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-cyan-500/20 px-2.5 py-0.5 text-[11px] font-semibold text-cyan-300 font-mono">
                    {activePreviewJob.engine?.toUpperCase()}
                  </span>
                  {activePreviewJob.language ? (
                    <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-slate-300">
                      {activePreviewJob.language}
                    </span>
                  ) : null}
                  {activePreviewJob.clean_transcript_text ? (
                    <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[11px] text-purple-300 font-semibold flex items-center gap-1">
                      <Sparkles className="h-3 w-3" /> AI Cleaned
                    </span>
                  ) : null}
                  {activePreviewJob.summary_markdown ? (
                    <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[11px] text-purple-300 font-semibold flex items-center gap-1">
                      <BookOpen className="h-3 w-3" /> Summarized
                    </span>
                  ) : null}
                </div>
                <h3 className="mt-1 truncate text-lg font-bold text-white">{activePreviewJob.title}</h3>
                <p className="text-xs text-slate-400">
                  {activePreviewJob.channel_title || 'YouTube Video'} · {durationLabel(activePreviewJob.duration_seconds)}
                </p>
              </div>

              <button
                type="button"
                onClick={() => setPreviewJob(null)}
                className="rounded-full border border-white/10 bg-slate-950/60 p-2 text-slate-400 hover:text-white transition"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Sub-Tabs & Actions Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 bg-slate-950/60 px-5 py-3">
              {/* Tab Selector */}
              <div className="inline-flex rounded-xl border border-white/10 bg-slate-900 p-1">
                <button
                  type="button"
                  onClick={() => setModalTab('clean')}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition flex items-center gap-1.5 ${
                    modalTab === 'clean'
                      ? 'bg-purple-500 text-white shadow'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Sparkles className="h-3.5 w-3.5" /> Clean Transcript
                </button>
                <button
                  type="button"
                  onClick={() => setModalTab('summary')}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition flex items-center gap-1.5 ${
                    modalTab === 'summary'
                      ? 'bg-purple-500 text-white shadow'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <BookOpen className="h-3.5 w-3.5" /> AI Summary & Chapters
                </button>
                <button
                  type="button"
                  onClick={() => setModalTab('raw')}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition flex items-center gap-1.5 ${
                    modalTab === 'raw'
                      ? 'bg-cyan-500 text-slate-950 shadow'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <FileText className="h-3.5 w-3.5" /> Raw Transcript
                </button>
              </div>

              {/* On-Demand Trigger Buttons & Copy */}
              <div className="flex items-center gap-2">
                {!activePreviewJob.clean_transcript_text && activePreviewJob.transcript_text ? (
                  <button
                    type="button"
                    onClick={() => handleTriggerCleaner(activePreviewJob.id)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-purple-400/30 bg-purple-400/10 px-3 py-1.5 text-xs font-semibold text-purple-300 hover:bg-purple-400/20 transition"
                  >
                    <Wand2 className="h-3.5 w-3.5" /> Run AI Cleanup
                  </button>
                ) : null}

                {!activePreviewJob.summary_markdown && (activePreviewJob.clean_transcript_text || activePreviewJob.transcript_text) ? (
                  <button
                    type="button"
                    onClick={() => handleTriggerSummarizer(activePreviewJob.id)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-purple-400/30 bg-purple-400/10 px-3 py-1.5 text-xs font-semibold text-purple-300 hover:bg-purple-400/20 transition"
                  >
                    <BookOpen className="h-3.5 w-3.5" /> Generate Summary
                  </button>
                ) : null}

                <button
                  type="button"
                  onClick={() => {
                    const textToCopy =
                      modalTab === 'clean'
                        ? activePreviewJob.clean_transcript_text || activePreviewJob.transcript_text || ''
                        : modalTab === 'summary'
                        ? activePreviewJob.summary_markdown || ''
                        : activePreviewJob.transcript_text || '';
                    copyText(textToCopy);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:text-white transition"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>

            {/* Search Input (For Transcript Tabs) */}
            {modalTab !== 'summary' ? (
              <div className="border-b border-white/10 px-5 py-2.5 bg-slate-950/40 flex items-center gap-2">
                <Search className="h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search keywords in transcript..."
                  className="w-full bg-transparent text-xs text-white placeholder:text-slate-500 focus:outline-none"
                />
                {searchQuery ? (
                  <button type="button" onClick={() => setSearchQuery('')} className="text-slate-500 hover:text-white">
                    <X className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
            ) : null}

            {/* Modal Content Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-3 font-mono text-xs">
              {/* TAB 1: CLEAN TRANSCRIPT */}
              {modalTab === 'clean' ? (
                activePreviewJob.clean_segments && activePreviewJob.clean_segments.length > 0 ? (
                  activePreviewJob.clean_segments
                    .filter((seg) => !searchQuery || seg.text.toLowerCase().includes(searchQuery.toLowerCase()))
                    .map((seg, idx) => (
                      <div
                        key={idx}
                        className="rounded-xl border border-white/5 bg-slate-950/40 p-3 hover:border-purple-500/30 transition flex flex-col sm:flex-row sm:items-start gap-3"
                      >
                        <span className="shrink-0 rounded bg-purple-500/10 px-2 py-0.5 text-[11px] text-purple-300 font-semibold">
                          {Math.floor(seg.start / 60)}:{String(Math.floor(seg.start % 60)).padStart(2, '0')} -{' '}
                          {Math.floor(seg.end / 60)}:{String(Math.floor(seg.end % 60)).padStart(2, '0')}
                        </span>
                        <p className="text-slate-200 leading-relaxed font-sans text-sm">{seg.text}</p>
                      </div>
                    ))
                ) : activePreviewJob.clean_transcript_text ? (
                  <div className="whitespace-pre-wrap rounded-2xl bg-slate-950/60 p-4 text-slate-200 leading-7 font-sans text-sm">
                    {activePreviewJob.clean_transcript_text}
                  </div>
                ) : (
                  <div className="text-center py-12 space-y-3">
                    <p className="text-xs text-slate-400">AI Cleanup has not been executed on this transcript yet.</p>
                    <button
                      type="button"
                      onClick={() => handleTriggerCleaner(activePreviewJob.id)}
                      className="inline-flex items-center gap-2 rounded-xl bg-purple-500 px-4 py-2 text-xs font-semibold text-white hover:bg-purple-400 transition"
                    >
                      <Wand2 className="h-4 w-4" /> Run AI Cleanup Agent Now
                    </button>
                  </div>
                )
              ) : null}

              {/* TAB 2: AI SUMMARY & CHAPTERS */}
              {modalTab === 'summary' ? (
                activePreviewJob.summary_markdown ? (
                  <div className="whitespace-pre-wrap rounded-2xl bg-slate-950/60 p-5 text-slate-200 leading-relaxed font-sans text-sm space-y-4">
                    {activePreviewJob.summary_markdown}
                  </div>
                ) : (
                  <div className="text-center py-12 space-y-3">
                    <p className="text-xs text-slate-400">AI Executive Summary has not been generated yet.</p>
                    <button
                      type="button"
                      onClick={() => handleTriggerSummarizer(activePreviewJob.id)}
                      className="inline-flex items-center gap-2 rounded-xl bg-purple-500 px-4 py-2 text-xs font-semibold text-white hover:bg-purple-400 transition"
                    >
                      <BookOpen className="h-4 w-4" /> Generate AI Summary & Chapters
                    </button>
                  </div>
                )
              ) : null}

              {/* TAB 3: RAW TRANSCRIPT */}
              {modalTab === 'raw' ? (
                activePreviewJob.segments && activePreviewJob.segments.length > 0 ? (
                  activePreviewJob.segments
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
                        <p className="text-slate-200 leading-relaxed font-sans">{seg.text}</p>
                      </div>
                    ))
                ) : activePreviewJob.transcript_text ? (
                  <div className="whitespace-pre-wrap rounded-2xl bg-slate-950/60 p-4 text-slate-300 leading-6 font-sans">
                    {activePreviewJob.transcript_text}
                  </div>
                ) : (
                  <p className="text-center py-10 text-slate-500">No transcript available.</p>
                )
              ) : null}
            </div>

            {/* Modal Footer Downloads */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 bg-slate-950/80 p-4">
              <span className="text-xs text-slate-400 flex items-center gap-1.5">
                <Download className="h-3.5 w-3.5 text-cyan-400" /> Export Subtitles & Summary:
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <a
                  href={transcriptExportUrl(activePreviewJob.id, 'txt')}
                  download
                  className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 hover:text-white"
                >
                  TXT
                </a>
                <a
                  href={transcriptExportUrl(activePreviewJob.id, 'srt')}
                  download
                  className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 hover:text-white"
                >
                  SRT
                </a>
                <a
                  href={transcriptExportUrl(activePreviewJob.id, 'vtt')}
                  download
                  className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 hover:text-white"
                >
                  VTT
                </a>
                <a
                  href={transcriptExportUrl(activePreviewJob.id, 'json')}
                  download
                  className="rounded-lg border border-white/10 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 hover:text-white"
                >
                  JSON
                </a>
                {activePreviewJob.clean_transcript_text ? (
                  <a
                    href={transcriptExportUrl(activePreviewJob.id, 'clean_txt')}
                    download
                    className="rounded-lg border border-purple-500/30 bg-purple-500/10 px-2.5 py-1 text-[11px] text-purple-300 hover:text-white font-medium"
                  >
                    Clean TXT
                  </a>
                ) : null}
                {activePreviewJob.summary_markdown ? (
                  <a
                    href={transcriptExportUrl(activePreviewJob.id, 'summary_md')}
                    download
                    className="rounded-lg border border-purple-500/30 bg-purple-500/10 px-2.5 py-1 text-[11px] text-purple-300 hover:text-white font-medium"
                  >
                    Summary MD
                  </a>
                ) : null}
              </div>
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
  onPause,
  onResume,
  onCancel,
  onDelete,
  onPreview
}: {
  job: TranscriptJob;
  onRetry: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onCancel: (id: string) => void;
  onDelete?: (id: string) => void;
  onPreview: (job: TranscriptJob) => void;
}) {
  const isActive = ACTIVE_STATUSES.has(job.status);
  const isPaused = job.status === 'PAUSED';

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
            {job.clean_transcript_text ? (
              <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[9px] text-purple-300 font-semibold">
                ✨ Cleaned
              </span>
            ) : null}
            {job.summary_markdown ? (
              <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[9px] text-purple-300 font-semibold">
                📑 Summarized
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {job.channel_title || 'Unknown channel'} · {durationLabel(job.duration_seconds)}
            {job.language ? ` · ${job.language}` : ''}
            {job.stage_detail ? <span className="text-cyan-400"> · {job.stage_detail}</span> : null}
          </p>
        </div>

        {/* Status & Control Actions */}
        <div className="flex items-center gap-2 self-start md:self-auto">
          <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${statusStyle(job.status)}`}>
            {job.status} {isActive ? `${job.progress}%` : ''}
          </span>

          {isActive ? (
            <button
              type="button"
              onClick={() => onPause(job.id)}
              className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-1.5 text-amber-300 hover:bg-amber-400/20"
              title="Pause Job"
            >
              <Pause className="h-3.5 w-3.5" />
            </button>
          ) : null}

          {isPaused ? (
            <button
              type="button"
              onClick={() => onResume(job.id)}
              className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-1.5 text-emerald-300 hover:bg-emerald-400/20"
              title="Resume Job"
            >
              <Play className="h-3.5 w-3.5" />
            </button>
          ) : null}

          {isActive || isPaused ? (
            <button
              type="button"
              onClick={() => onCancel(job.id)}
              className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-1.5 text-rose-300 hover:bg-rose-500/20"
              title="Cancel Job"
            >
              <Square className="h-3.5 w-3.5" />
            </button>
          ) : null}

          {onDelete ? (
            <button
              type="button"
              onClick={() => onDelete(job.id)}
              className="rounded-lg border border-white/10 bg-slate-900/80 p-1.5 text-slate-400 hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300 transition"
              title="Remove / Delete Job"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
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
            <Eye className="h-3.5 w-3.5" /> View Transcript & Summary
          </button>

          {(['txt', 'srt', 'vtt', 'json'] as const).map((fmt) => (
            <a
              key={fmt}
              href={transcriptExportUrl(job.id, fmt)}
              download
              className="inline-flex items-center gap-1 rounded-xl border border-white/10 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:border-cyan-500/40 hover:text-white transition"
            >
              <Download className="h-3 w-3 text-cyan-400" />
              {fmt.toUpperCase()}
            </a>
          ))}

          {job.clean_transcript_text ? (
            <a
              href={transcriptExportUrl(job.id, 'clean_txt')}
              download
              className="inline-flex items-center gap-1 rounded-xl border border-purple-500/30 bg-purple-500/10 px-2.5 py-1.5 text-xs font-medium text-purple-300 hover:text-white transition"
            >
              <Sparkles className="h-3 w-3" /> Clean TXT
            </a>
          ) : null}

          {job.summary_markdown ? (
            <a
              href={transcriptExportUrl(job.id, 'summary_md')}
              download
              className="inline-flex items-center gap-1 rounded-xl border border-purple-500/30 bg-purple-500/10 px-2.5 py-1.5 text-xs font-medium text-purple-300 hover:text-white transition"
            >
              <BookOpen className="h-3 w-3" /> Summary MD
            </a>
          ) : null}
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
