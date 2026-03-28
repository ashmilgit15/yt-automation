'use client';

interface KeyboardShortcutsPanelProps {
  open: boolean;
  onClose: () => void;
}

const shortcuts = [
  { keys: 'N', description: 'Focus the new job topic box' },
  { keys: 'Ctrl/Cmd + Enter', description: 'Queue the current job from the topic field' },
  { keys: '?', description: 'Open or close this shortcuts panel' },
  { keys: 'Esc', description: 'Close the review modal or shortcuts panel' }
];

export function KeyboardShortcutsPanel({ open, onClose }: KeyboardShortcutsPanelProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40 bg-ink/70 px-4 py-8 backdrop-blur-sm">
      <div className="mx-auto max-w-2xl rounded-[32px] border border-white/10 bg-[#08121d] p-6 shadow-panel lg:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-aqua">Keyboard Shortcuts</p>
            <h2 className="mt-3 text-2xl font-semibold text-white">Faster ways to drive the dashboard</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 px-3 py-2 text-sm text-white transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40"
          >
            Close
          </button>
        </div>

        <div className="mt-6 space-y-3">
          {shortcuts.map((shortcut) => (
            <div key={shortcut.keys} className="flex items-center justify-between gap-4 rounded-[24px] border border-white/10 bg-white/5 px-4 py-4">
              <p className="text-sm text-mist">{shortcut.description}</p>
              <kbd className="rounded-full border border-white/10 bg-slate/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-white">
                {shortcut.keys}
              </kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
