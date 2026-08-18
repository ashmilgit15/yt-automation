export type TranscriptStatus =
  | 'PENDING'
  | 'ACQUIRING'
  | 'TRANSCRIBING'
  | 'EXPORTING'
  | 'COMPLETED'
  | 'FAILED';

export type PlaylistStatus = 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'PARTIAL';

export type TranscriptionEngine = 'local_whisper' | 'sarvam' | 'groq';

export type SarvamMode =
  | 'transcribe'
  | 'translate'
  | 'verbatim'
  | 'codemix'
  | 'translit';

export interface IndicLanguageOption {
  code: string;
  name: string;
  nativeName: string;
}

export const INDIC_LANGUAGES: IndicLanguageOption[] = [
  { code: 'unknown', name: 'Auto Detect Language', nativeName: 'Auto' },
  { code: 'hi-IN', name: 'Hindi', nativeName: 'हिन्दी' },
  { code: 'en-IN', name: 'English (Indian)', nativeName: 'English' },
  { code: 'bn-IN', name: 'Bengali', nativeName: 'বাংলা' },
  { code: 'ta-IN', name: 'Tamil', nativeName: 'தமிழ்' },
  { code: 'te-IN', name: 'Telugu', nativeName: 'తెలుగు' },
  { code: 'kn-IN', name: 'Kannada', nativeName: 'ಕನ್ನಡ' },
  { code: 'ml-IN', name: 'Malayalam', nativeName: 'മലയാളം' },
  { code: 'mr-IN', name: 'Marathi', nativeName: 'मराठी' },
  { code: 'gu-IN', name: 'Gujarati', nativeName: 'ગુજરાતી' },
  { code: 'pa-IN', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ' },
  { code: 'od-IN', name: 'Odia', nativeName: 'ଓଡ଼ିଆ' },
  { code: 'as-IN', name: 'Assamese', nativeName: 'অসমীয়া' },
  { code: 'ur-IN', name: 'Urdu', nativeName: 'اردو' },
  { code: 'ne-IN', name: 'Nepali', nativeName: 'नेपाली' },
  { code: 'sa-IN', name: 'Sanskrit', nativeName: 'संस्कृतम्' },
  { code: 'kok-IN', name: 'Konkani', nativeName: 'कोंकणी' },
  { code: 'mai-IN', name: 'Maithili', nativeName: 'मैथिली' }
];

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
  playlist_batch_id?: string | null;
  engine: TranscriptionEngine;
  status: TranscriptStatus;
  progress: number;
  stage_detail?: string | null;
  language: string | null;
  mode?: SarvamMode | null;
  transcript_text: string | null;
  segments: Array<{ start: number; end: number; text: string; words?: Array<{ start: number; end: number; word: string }> }> | null;
  error_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlaylistBatch {
  id: string;
  playlist_id: string;
  source_url: string;
  title: string | null;
  engine: TranscriptionEngine;
  status: PlaylistStatus;
  total_videos: number;
  completed_videos: number;
  failed_videos: number;
  created_at: string;
  updated_at: string;
  jobs: TranscriptJob[];
}

export interface PlaylistBatchSummary {
  id: string;
  playlist_id: string;
  source_url: string;
  title: string | null;
  engine: TranscriptionEngine;
  status: PlaylistStatus;
  total_videos: number;
  completed_videos: number;
  failed_videos: number;
  created_at: string;
  updated_at: string;
}

export interface CreatePlaylistBatchOptions {
  playlist_url: string;
  selected_video_ids: string[];
  engine?: TranscriptionEngine;
  language_code?: string;
  mode?: SarvamMode;
}

export interface CreateSingleTranscriptOptions {
  video_url: string;
  engine?: TranscriptionEngine;
  language_code?: string;
  mode?: SarvamMode;
}
