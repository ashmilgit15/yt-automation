export type TranscriptStatus = 'PENDING' | 'ACQUIRING' | 'TRANSCRIBING' | 'EXPORTING' | 'COMPLETED' | 'FAILED';
export type PlaylistStatus = 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'PARTIAL';

export interface PlaylistVideo {
  video_id: string;
  title: string;
  channel_title: string | null;
  duration_seconds: number | null;
  thumbnail_url: string | null;
  position: number;
}

export interface PlaylistAnalysis {
  playlist_id: string;
  playlist_url: string;
  title: string | null;
  videos: PlaylistVideo[];
}

export interface TranscriptJob extends PlaylistVideo {
  id: string;
  status: TranscriptStatus;
  progress: number;
  language: string | null;
  transcript_text: string | null;
  segments: Array<{ start: number; end: number; text: string }> | null;
  error_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlaylistBatch {
  id: string;
  playlist_id: string;
  source_url: string;
  title: string | null;
  status: PlaylistStatus;
  total_videos: number;
  completed_videos: number;
  failed_videos: number;
  created_at: string;
  updated_at: string;
  jobs: TranscriptJob[];
}
