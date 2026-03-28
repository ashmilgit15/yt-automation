'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { fetchYouTubeChannels } from '@/lib/api';

export function PublishModal({ isOpen, onClose, onConfirm, isBulk, count }: { isOpen: boolean, onClose: () => void, onConfirm: (channel: string) => void, isBulk: boolean, count: number }) {
  const { data } = useSWR('youtube-channels', fetchYouTubeChannels);
  const channels = data?.channels || [];
  const [selectedChannel, setSelectedChannel] = useState(channels[0]?.channel_label || '');

  useEffect(() => {
    if (channels.length > 0 && !selectedChannel) {
      setSelectedChannel(channels[0].channel_label);
    }
  }, [channels, selectedChannel]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-ink/80 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-slate/90 border border-white/10 rounded-3xl shadow-panel p-8 w-full max-w-md">
        <h2 className="text-xl font-bold text-white mb-4">
          {isBulk ? `Publish ${count} Jobs` : 'Publish Job'}
        </h2>
        <p className="text-sm text-mist mb-6">Select the YouTube channel to upload to.</p>

        {channels.length === 0 ? (
          <p className="text-rose-400 mb-4">No connected channels found. Connect a channel in the dashboard first.</p>
        ) : (
          <select 
            value={selectedChannel} 
            onChange={e => setSelectedChannel(e.target.value)}
            className="w-full mb-6 rounded-2xl border border-white/10 bg-white/5 p-4 text-white focus:outline-none focus:ring-2 focus:ring-aqua/40"
          >
            <option value="" disabled>Select a channel...</option>
            {channels.map(c => (
              <option key={c.id} value={c.channel_label}>{c.channel_label}</option>
            ))}
          </select>
        )}

        <div className="flex gap-4 justify-end">
          <button onClick={onClose} className="px-6 py-3 rounded-full bg-white/5 text-mist hover:text-white transition">Cancel</button>
          <button 
            disabled={!selectedChannel}
            onClick={() => onConfirm(selectedChannel)} 
            className="px-6 py-3 rounded-full bg-gradient-to-r from-aqua to-emerald-300 text-slate font-bold disabled:opacity-50 transition hover:brightness-110"
          >
            Confirm Publish
          </button>
        </div>
      </div>
    </div>
  );
}
