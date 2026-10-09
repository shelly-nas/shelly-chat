'use client'

import { useState } from 'react'
import { Wand2, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import type { ExpansionSource } from '@/app/page'

interface QueryExpansionBubbleProps {
  expansions: ExpansionSource[]
}

export function QueryExpansionBubble({ expansions }: QueryExpansionBubbleProps) {
  const [open, setOpen] = useState(false)

  if (expansions.length === 0) return null

  // Group by abbreviation
  const grouped: Record<string, ExpansionSource[]> = {}
  for (const entry of expansions) {
    if (!grouped[entry.abbrev]) grouped[entry.abbrev] = []
    grouped[entry.abbrev].push(entry)
  }

  const abbrevList = Object.keys(grouped)

  return (
    <div className="mt-2 text-left">
      <div className="inline-block max-w-[85%]">
        <button
          onClick={() => setOpen(v => !v)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-dashed border-[var(--claude-border)] bg-[var(--claude-surface)]/50 text-[var(--claude-text-secondary)] opacity-70 hover:opacity-100 transition-opacity text-xs"
        >
          <Wand2 className="w-3 h-3 flex-shrink-0" />
          <span>
            Zoekopdracht automatisch uitgebreid:{' '}
            <span className="font-medium text-[var(--claude-text-primary)]">
              {abbrevList.join(', ')}
            </span>
          </span>
          {open ? <ChevronUp className="w-3 h-3 flex-shrink-0" /> : <ChevronDown className="w-3 h-3 flex-shrink-0" />}
        </button>

        {open && (
          <div className="mt-1 p-3 rounded-xl border border-dashed border-[var(--claude-border)] bg-[var(--claude-surface)]/50 opacity-80 space-y-3 text-xs">
            {Object.entries(grouped).map(([abbrev, entries]) => (
              <div key={abbrev}>
                <p className="font-medium text-[var(--claude-text-primary)] mb-1.5">
                  {abbrev}{' '}
                  <span className="text-[var(--claude-text-secondary)] font-normal">→</span>{' '}
                  {entries[0].term}
                </p>
                <div className="space-y-2 pl-2 border-l border-[var(--claude-border)]">
                  {entries.map((entry, i) => (
                    <div key={i}>
                      <a
                        href={entry.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-[var(--claude-accent)] hover:underline"
                      >
                        <ExternalLink className="w-3 h-3 flex-shrink-0" />
                        {entry.file_name}
                      </a>
                      <blockquote className="mt-0.5 text-[var(--claude-text-secondary)] italic line-clamp-2 pl-1">
                        {entry.snippet}
                      </blockquote>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
