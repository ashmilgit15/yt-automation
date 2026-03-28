'use client';

import { Activity, Bot, RadioTower, ShieldAlert } from 'lucide-react';

import type { VideoJobSummary } from '@/types/jobs';

function sumVisualAssets(jobs: VideoJobSummary[]): number {
  return jobs.reduce((accumulator, job) => accumulator + job.visual_asset_count, 0);
}

export function TelemetryCards({ jobs }: { jobs: VideoJobSummary[] }) {
  const active = jobs.filter((job) => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(job.status)).length;
  const blocked = jobs.filter((job) => job.status === 'BLOCKED_BY_QUALITY_GATE').length;
  const published = jobs.filter((job) => job.status === 'COMPLETED').length;
  const sceneCount = sumVisualAssets(jobs);

  const cards = [
    {
      label: 'Active Pipelines',
      value: active,
      icon: Activity,
      accent: 'from-aqua/30 to-transparent'
    },
    {
      label: 'Published Outputs',
      value: published,
      icon: RadioTower,
      accent: 'from-lime/30 to-transparent'
    },
    {
      label: 'Blocked for Review',
      value: blocked,
      icon: ShieldAlert,
      accent: 'from-rose/30 to-transparent'
    },
    {
      label: 'Curated Scene Assets',
      value: sceneCount,
      icon: Bot,
      accent: 'from-ember/30 to-transparent'
    }
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map(({ label, value, icon: Icon, accent }) => (
        <div
          key={label}
          className={`rounded-[28px] border border-white/10 bg-gradient-to-br ${accent} px-5 py-5 shadow-panel backdrop-blur`}
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-mist/80">{label}</p>
              <p className="mt-3 text-3xl font-semibold text-white">{value}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/80">
              <Icon className="h-5 w-5" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
