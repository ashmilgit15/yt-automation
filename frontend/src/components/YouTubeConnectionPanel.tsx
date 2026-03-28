'use client';

import { useEffect, useState, type ChangeEvent } from 'react';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { CircleCheckBig, KeyRound, RefreshCw, TriangleAlert, Trash2 } from 'lucide-react';

import { buildYouTubeOauthStartUrl, fetchYouTubeChannels, deleteYouTubeChannel } from '@/lib/api';

interface YouTubeConnectionPanelProps {
  enabled: boolean;
}

export function YouTubeConnectionPanel({ enabled }: YouTubeConnectionPanelProps) {
  const searchParams = useSearchParams();
  const oauthState = searchParams.get('youtube_oauth');
  const oauthMessage = searchParams.get('message');
  const [newChannelLabel, setNewChannelLabel] = useState('');

  const { data, error, isLoading, mutate } = useSWR(
    enabled ? 'youtube-channels' : null,
    fetchYouTubeChannels,
    {
      refreshInterval: 15000,
      dedupingInterval: 4000
    }
  );

  useEffect(() => {
    if (oauthState && enabled) {
      void mutate();
    }
  }, [enabled, mutate, oauthState]);

  if (!enabled) {
    return null;
  }

  const connectNew = () => {
    if (newChannelLabel.trim()) {
      window.location.assign(buildYouTubeOauthStartUrl(newChannelLabel.trim()));
    }
  };

  const handleDelete = async (id: number) => {
    if (window.confirm('Delete this channel connection?')) {
      await deleteYouTubeChannel(id);
      void mutate();
    }
  };

  return (
    <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur lg:p-7">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs uppercase tracking-[0.28em] text-ember">YouTube Upload Connection</p>
          <h2 className="balanced-heading mt-3 text-2xl font-semibold text-white">Connect your channels once, publish anywhere</h2>
          <p className="mt-2 text-sm leading-7 text-mist">
            Connect multiple YouTube channels. When a job is ready to publish, you can choose which channel it uploads to.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void mutate()}
            className="inline-flex items-center gap-2 rounded-3xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
          >
            <RefreshCw aria-hidden="true" className="h-4 w-4" />
            Refresh Status
          </button>
        </div>
      </div>

      <div aria-live="polite" className="mt-5">
        {error ? (
          <div className="mb-4 rounded-[24px] border border-rose/20 bg-rose/10 px-4 py-4 text-sm text-rose-100">
            The dashboard could not read the YouTube connection status. Check the backend session and API health, then refresh this panel.
          </div>
        ) : null}
        {oauthState ? (
          <div
            className={`mb-4 rounded-[24px] border px-4 py-4 text-sm ${
              oauthState === 'success'
                ? 'border-lime/20 bg-lime/10 text-lime-100'
                : 'border-rose/20 bg-rose/10 text-rose-100'
            }`}
          >
            {oauthMessage ?? (oauthState === 'success' ? 'YouTube connection completed.' : 'YouTube connection failed.')}
          </div>
        ) : null}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-[28px] border border-white/10 bg-slate/55 p-5">
          <h3 className="mb-4 text-sm font-semibold text-white">Connected Channels</h3>
          
          {isLoading ? (
            <p className="text-sm text-mist">Loading channels...</p>
          ) : data?.channels && data.channels.length > 0 ? (
            <div className="space-y-3">
              {data.channels.map(channel => (
                <div key={channel.id} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <CircleCheckBig className="h-5 w-5 text-lime" />
                    <div>
                      <p className="text-sm font-semibold text-white">{channel.channel_label}</p>
                      <p className="text-xs text-mist/70">Connected {new Date(channel.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  <button 
                    onClick={() => handleDelete(channel.id)}
                    className="p-2 text-mist hover:text-rose-400 transition"
                    title="Remove connection"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-4 text-sm text-amber-100">
              No channels connected yet. Connect a channel below.
            </div>
          )}
        </div>

        <div className="rounded-[28px] border border-white/10 bg-slate/55 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-aqua">Add New Channel</p>
          
          <div className="mt-4 space-y-4">
            <label className="block space-y-2">
              <span className="text-xs text-mist">Channel Label (e.g. "Main Tech Channel")</span>
              <input
                value={newChannelLabel}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setNewChannelLabel(e.target.value)}
                placeholder="Enter channel label..."
                className="w-full rounded-2xl border border-white/10 bg-slate/80 px-4 py-3 text-sm text-white transition focus:border-ember/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/30"
              />
            </label>
            <button
              type="button"
              onClick={connectNew}
              disabled={!newChannelLabel.trim()}
              className="w-full inline-flex justify-center items-center gap-2 rounded-2xl bg-gradient-to-r from-ember to-aqua px-4 py-3 text-sm font-semibold text-slate transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <KeyRound aria-hidden="true" className="h-4 w-4" />
              Connect with Google
            </button>
          </div>

          <p className="mt-5 text-xs text-mist">
            The backend will redirect you to Google's sign-in screen to authorize access to YouTube. Ensure `client_secrets.json` is configured.
          </p>
        </div>
      </div>
    </section>
  );
}
