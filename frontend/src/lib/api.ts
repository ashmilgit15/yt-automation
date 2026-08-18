import axios from 'axios';

import type { OperatorLoginPayload, OperatorSession } from '@/types/auth';
import type { YouTubeConnectionStatus } from '@/types/integrations';
import type {
  CreatePlaylistBatchOptions,
  CreateSingleTranscriptOptions,
  PlaylistAnalysis,
  PlaylistBatch,
  PlaylistBatchSummary,
  TranscriptJob
} from '@/types/transcripts';
import type { BulkCreateJobPayload, BulkJobCreateResponse, CreateJobPayload, JobCollectionResponse, SourceRemixJobCreatePayload, VideoJobDetail } from '@/types/jobs';

const baseURL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000/api/v1';

export const api = axios.create({
  baseURL,
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
});

function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim().length > 0) {
      return detail;
    }
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'Something went wrong. Please try again.';
}

export async function fetchOperatorSession(): Promise<OperatorSession> {
  const response = await api.get<OperatorSession>('/auth/session');
  return response.data;
}

export async function loginOperator(payload: OperatorLoginPayload): Promise<OperatorSession> {
  try {
    const response = await api.post<OperatorSession>('/auth/login', payload);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function logoutOperator(): Promise<OperatorSession> {
  try {
    const response = await api.post<OperatorSession>('/auth/logout');
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function fetchJobs(pageSize = 24): Promise<JobCollectionResponse> {
  const response = await api.get<JobCollectionResponse>('/jobs', {
    params: {
      page_size: pageSize
    }
  });
  return response.data;
}

export async function fetchJob(jobId: string): Promise<VideoJobDetail> {
  const response = await api.get<VideoJobDetail>(`/jobs/${jobId}`);
  return response.data;
}

export async function createJob(payload: CreateJobPayload): Promise<{ job_id: string; status: string }> {
  try {
    const response = await api.post<{ job_id: string; status: string }>('/jobs', payload);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function createBulkJobs(payload: BulkCreateJobPayload): Promise<BulkJobCreateResponse> {
  try {
    const response = await api.post<BulkJobCreateResponse>('/jobs/bulk', payload);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function createSourceRemixJob(payload: SourceRemixJobCreatePayload): Promise<{ job_id: string; status: string }> {
  try {
    const response = await api.post<{ job_id: string; status: string }>('/jobs/source-remix', payload);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function reviewJob(jobId: string, approved: boolean, notes?: string): Promise<VideoJobDetail> {
  try {
    const response = await api.post<VideoJobDetail>(`/jobs/${jobId}/review`, { approved, notes });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function retryJob(jobId: string): Promise<{ job_id: string; status: string }> {
  try {
    const response = await api.post<{ job_id: string; status: string }>(`/jobs/${jobId}/retry`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function duplicateJob(jobId: string): Promise<{ job_id: string; status: string }> {
  try {
    const response = await api.post<{ job_id: string; status: string }>(`/jobs/${jobId}/duplicate`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function makeJobPublic(jobId: string): Promise<VideoJobDetail> {
  try {
    const response = await api.post<VideoJobDetail>(`/jobs/${jobId}/make-public`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function publishJob(jobId: string, channelLabel: string): Promise<{ job_id: string; status: string; message: string }> {
  try {
    const response = await api.post<{ job_id: string; status: string; message: string }>(`/jobs/${jobId}/publish`, { channel_label: channelLabel });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function bulkPublishJobs(jobIds: string[], channelLabel: string): Promise<{ jobs_processed: number; status: string }> {
  try {
    const response = await api.post<{ jobs_processed: number; status: string }>('/jobs/bulk-publish', { job_ids: jobIds, channel_label: channelLabel });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function fetchYouTubeChannels(): Promise<{ channels: Array<{ id: number; channel_label: string; created_at: string; updated_at: string }> }> {
  try {
    const response = await api.get<{ channels: Array<{ id: number; channel_label: string; created_at: string; updated_at: string }> }>('/integrations/youtube/channels');
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function deleteYouTubeChannel(channelId: number): Promise<void> {
  try {
    await api.delete(`/integrations/youtube/channels/${channelId}`);
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function resumeJobFromStage(jobId: string): Promise<VideoJobDetail> {
  try {
    const response = await api.post<VideoJobDetail>(`/jobs/${jobId}/resume-from-stage`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function regenerateMetadata(jobId: string): Promise<VideoJobDetail> {
  try {
    const response = await api.post<VideoJobDetail>(`/jobs/${jobId}/regenerate-metadata`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function deleteJob(jobId: string): Promise<{ job_id: string; status: string; message: string }> {
  try {
    const response = await api.delete<{ job_id: string; status: string; message: string }>(`/jobs/${jobId}`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function fetchYouTubeConnectionStatus(
  channelLabel = 'default'
): Promise<YouTubeConnectionStatus> {
  const response = await api.get<YouTubeConnectionStatus>('/integrations/youtube/status', {
    params: {
      channel_label: channelLabel
    }
  });
  return response.data;
}

export function buildYouTubeOauthStartUrl(channelLabel = 'default'): string {
  const url = new URL(`${baseURL}/integrations/youtube/oauth/start`);
  url.searchParams.set('channel_label', channelLabel);
  return url.toString();
}

export async function analysePlaylist(playlist_url: string): Promise<PlaylistAnalysis> {
  try {
    const response = await api.post<PlaylistAnalysis>('/playlists/analyze', { playlist_url });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function fetchPlaylistBatches(limit = 15): Promise<PlaylistBatchSummary[]> {
  try {
    const response = await api.get<PlaylistBatchSummary[]>('/playlists', {
      params: { limit }
    });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function createPlaylistBatch(options: CreatePlaylistBatchOptions): Promise<PlaylistBatch> {
  try {
    const response = await api.post<PlaylistBatch>('/playlists', {
      playlist_url: options.playlist_url,
      selected_video_ids: options.selected_video_ids,
      authorised_to_process: true,
      engine: options.engine ?? 'local_whisper',
      language_code: options.language_code ?? 'unknown',
      mode: options.mode ?? 'transcribe'
    });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function createSingleTranscriptJob(options: CreateSingleTranscriptOptions): Promise<TranscriptJob> {
  try {
    const response = await api.post<TranscriptJob>('/transcripts/single', {
      video_url: options.video_url,
      authorised_to_process: true,
      engine: options.engine ?? 'local_whisper',
      language_code: options.language_code ?? 'unknown',
      mode: options.mode ?? 'transcribe'
    });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export async function fetchPlaylistBatch(batchId: string): Promise<PlaylistBatch> {
  const response = await api.get<PlaylistBatch>(`/playlists/${batchId}`);
  return response.data;
}

export async function fetchTranscriptJob(jobId: string): Promise<TranscriptJob> {
  const response = await api.get<TranscriptJob>(`/transcripts/${jobId}`);
  return response.data;
}

export async function fetchRecentTranscriptJobs(limit = 30): Promise<TranscriptJob[]> {
  const response = await api.get<TranscriptJob[]>('/transcripts/recent', {
    params: { limit }
  });
  return response.data;
}

export async function retryTranscriptJob(jobId: string): Promise<TranscriptJob> {
  try {
    const response = await api.post<TranscriptJob>(`/transcripts/${jobId}/retry`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error));
  }
}

export function transcriptExportUrl(jobId: string, format: 'txt' | 'srt' | 'vtt' | 'json'): string {
  return `${baseURL}/transcripts/${jobId}/export/${format}`;
}

