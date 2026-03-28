'use client';

import type { ChangeEvent } from 'react';
import { useState, useTransition } from 'react';
import { LockKeyhole, LogOut, ShieldCheck } from 'lucide-react';

import { loginOperator, logoutOperator } from '@/lib/api';
import type { OperatorSession } from '@/types/auth';

interface OperatorAccessPanelProps {
  session: OperatorSession | undefined;
  onSessionChange: () => void;
}

export function OperatorAccessPanel({ session, onSessionChange }: OperatorAccessPanelProps) {
  const [username, setUsername] = useState('operator');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const authenticated = session?.authenticated ?? false;

  const handleLogin = () => {
    setMessage(null);
    startTransition(async () => {
      try {
        await loginOperator({ username, password });
        setMessage('Operator session is active.');
        onSessionChange();
      } catch (error) {
        const fallback = error instanceof Error ? error.message : 'Unable to sign in.';
        setMessage(fallback);
      }
    });
  };

  const handleLogout = () => {
    setMessage(null);
    startTransition(async () => {
      try {
        await logoutOperator();
        setMessage('You signed out of the operator session.');
        onSessionChange();
      } catch (error) {
        const fallback = error instanceof Error ? error.message : 'Unable to sign out.';
        setMessage(fallback);
      }
    });
  };

  return (
    <section className="mt-6 rounded-[32px] border border-white/10 bg-white/5 p-6 shadow-panel backdrop-blur lg:p-7">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs uppercase tracking-[0.28em] text-lime">Operator Access</p>
          <h2 className="balanced-heading mt-3 text-2xl font-semibold text-white">Protect the control plane before you automate anything</h2>
          <p className="mt-2 text-sm leading-7 text-mist">
            Modern production dashboards lock job orchestration, review overrides, and credential changes behind an operator session. Sign in here to unlock the workflow safely.
          </p>
        </div>

        {authenticated ? (
          <div className="rounded-[24px] border border-lime/20 bg-lime/10 px-4 py-3 text-sm text-lime-100">
            Signed in as <span className="font-semibold text-white">{session?.username}</span>
          </div>
        ) : null}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[28px] border border-white/10 bg-slate/55 p-5">
          {authenticated ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-white">
                <ShieldCheck aria-hidden="true" className="h-5 w-5 text-lime" />
                <div>
                  <p className="font-semibold">Operator session active</p>
                  <p className="text-sm text-mist">The dashboard can now enqueue jobs, review blocks, and manage YouTube credentials.</p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                disabled={isPending}
                className="inline-flex items-center gap-2 rounded-3xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40 disabled:opacity-60"
              >
                <LogOut aria-hidden="true" className="h-4 w-4" />
                Sign Out
              </button>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Username</span>
                <input
                  type="text"
                  name="operatorUsername"
                  autoComplete="username"
                  spellCheck={false}
                  className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
                  value={username}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setUsername(event.target.value)}
                />
              </label>

              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.22em] text-mist/80">Password</span>
                <input
                  type="password"
                  name="operatorPassword"
                  autoComplete="current-password"
                  placeholder="Enter your operator password…"
                  className="w-full rounded-3xl border border-white/10 bg-slate/80 px-5 py-4 text-sm text-white transition focus:border-aqua/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/30"
                  value={password}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setPassword(event.target.value)}
                />
              </label>

              <button
                type="button"
                onClick={handleLogin}
                disabled={isPending}
                className="sm:col-span-2 inline-flex items-center justify-center gap-2 rounded-3xl bg-gradient-to-r from-lime/80 to-aqua px-4 py-3 text-sm font-semibold text-slate transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime/30 disabled:opacity-60"
              >
                <LockKeyhole aria-hidden="true" className="h-4 w-4" />
                {isPending ? 'Signing In…' : 'Unlock Dashboard'}
              </button>
            </div>
          )}

          <p aria-live="polite" className="mt-4 text-sm text-mist">
            {message}
          </p>
        </div>

        <div className="rounded-[28px] border border-white/10 bg-slate/55 p-5">
          <p className="text-xs uppercase tracking-[0.22em] text-aqua">Before you ship</p>
          <ul className="mt-4 space-y-3 text-sm leading-7 text-mist">
            <li>1. Change the default operator password in `.env`.</li>
            <li>2. Keep the dashboard private behind your own domain or VPN.</li>
            <li>3. Only connect the YouTube account you want the worker to publish to.</li>
          </ul>
          {session?.warning ? (
            <div className="mt-5 rounded-[22px] border border-amber-300/20 bg-amber-300/10 px-4 py-4 text-sm text-amber-50">
              {session.warning}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
