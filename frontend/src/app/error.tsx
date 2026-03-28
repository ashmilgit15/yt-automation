'use client';

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="rounded-[32px] border border-rose/20 bg-rose/10 p-8 text-sm text-rose-100 shadow-panel backdrop-blur">
        <h1 className="text-2xl font-semibold text-white">Something interrupted the dashboard</h1>
        <p className="mt-3 leading-7">Refresh the page or retry the failed action. If this keeps happening, inspect the backend logs and API response.</p>
        <button
          type="button"
          onClick={reset}
          className="mt-6 rounded-3xl border border-white/15 bg-white/10 px-4 py-3 font-semibold text-white transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
