export interface YouTubeConnectionStatus {
  channel_label: string;
  connected: boolean;
  credential_source: 'database' | 'environment' | 'none';
  has_client_secrets: boolean;
  authorization_ready: boolean;
  redirect_uri: string;
  scopes_json: string[] | null;
  message: string;
}

export interface YouTubeChannel {
  id: number;
  channel_label: string;
  created_at: string;
  updated_at: string;
}

export interface YouTubeChannelListResponse {
  channels: YouTubeChannel[];
}
