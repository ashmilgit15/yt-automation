import type { Metadata, Viewport } from 'next';
import Link from 'next/link';
import { IBM_Plex_Mono, Space_Grotesk } from 'next/font/google';
import type { ReactNode } from 'react';

import './globals.css';

const display = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-display'
});

const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono'
});

export const metadata: Metadata = {
  title: 'Bulk YouTube Transcriber',
  description: 'Dashboard for an AI-driven video automation pipeline.',
  applicationName: 'Bulk YouTube Transcriber'
};

export const viewport: Viewport = {
  themeColor: '#07111c',
  colorScheme: 'dark'
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <head>
        <link rel="preconnect" href="https://images.pexels.com" />
        <link rel="dns-prefetch" href="https://images.pexels.com" />
      </head>
      <body className="font-[var(--font-display)] antialiased">
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <nav className="sticky top-0 z-40 border-b border-white/10 bg-ink/70 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 text-sm text-mist sm:px-6 lg:px-8">
            <Link href="/" className="font-semibold uppercase tracking-[0.28em] text-white transition hover:text-aqua focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40">
              VFactory
            </Link>
            <div className="flex items-center gap-4">
              <Link href="/" className="transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40">
                Dashboard
              </Link>
              <Link href="/jobs" className="transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aqua/40">
                Jobs
              </Link>
            </div>
          </div>
        </nav>
        <main id="main-content">{children}</main>
      </body>
    </html>
  );
}
