export type JobStatus =
  | 'PENDING'
  | 'RESEARCHING'
  | 'AUDIO'
  | 'VISUALS'
  | 'COMPOSING'
  | 'READY_TO_PUBLISH'
  | 'UPLOADING'
  | 'COMPLETED'
  | 'FAILED'
  | 'BLOCKED_BY_QUALITY_GATE'
  | 'CANCELLED';

export type Orientation = 'portrait' | 'landscape';
export type PublishPrivacy = 'public' | 'private' | 'unlisted';

export interface ScenePayload {
  sentence: string;
  visual_keyword: string;
  start_seconds?: number | null;
  end_seconds?: number | null;
}

export interface AssetManifestItem {
  scene_index: number;
  sentence: string;
  visual_keyword: string;
  pexels_video_id: number;
  thumbnail_url: string;
  download_url: string;
  local_path: string;
  score: number;
  reason?: string;
}

export interface VideoJobSummary {
  id: string;
  topic: string;
  target_audience: string | null;
  duration_seconds: number;
  orientation: Orientation;
  status: JobStatus;
  quality_score: number | null;
  publish_privacy: PublishPrivacy;
  distribution_label: string;
  batch_label: string | null;
  batch_index: number | null;
  youtube_url: string | null;
  title: string | null;
  critique_text: string | null;
  manual_override: boolean;
  created_at: string;
  updated_at: string;
  scene_count: number;
  visual_asset_count: number;
  error_summary: string | null;
}

export interface VideoJobDetail extends VideoJobSummary {
  youtube_video_id: string | null;
  error_log: string | null;
  description: string | null;
  script_text: string | null;
  scenes_json: ScenePayload[] | null;
  visual_asset_manifest: AssetManifestItem[] | null;
  critique_json: Record<string, unknown> | null;
  artifact_paths: Record<string, unknown> | null;
  usage_metrics: Record<string, unknown> | null;
}

export interface JobCollectionResponse {
  jobs: VideoJobSummary[];
  total_count: number;
  page_size: number;
  active_count: number;
  blocked_count: number;
}

export interface CreateJobPayload {
  topic: string;
  target_audience?: string;
  duration_seconds: number;
  orientation: Orientation;
  publish_privacy: PublishPrivacy;
}

export interface BulkCreateJobPayload {
  niche: string;
  target_audience?: string;
  duration_seconds: number;
  orientation: Orientation;
  publish_privacy: PublishPrivacy;
  videos_count: number;
}

export interface BulkQueuedJob {
  job_id: string;
  topic: string;
  target_audience: string | null;
  status: JobStatus;
  batch_index: number;
}

export interface BulkJobCreateResponse {
  batch_id: string;
  batch_label: string;
  videos_count: number;
  jobs: BulkQueuedJob[];
}

export interface SourceRemixJobCreatePayload {
  topic: string;
  target_audience?: string;
  duration_seconds: number;
  orientation: Orientation;
  publish_privacy: PublishPrivacy;
  shots_count: number;
}
