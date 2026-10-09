'use client'

import { useState } from 'react'
import { Info, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react'
import type { ExpansionSource } from '@/app/page'

interface QueryExpansionBadgeProps {
  expansions: ExpansionSource[]
}

export function QueryExpansionBadge({ expansions }: QueryExpansionBadgeProps) {
  const [open, setOpen] = useState(false)

  if (expansions.length === 0) return null

  // Group entries by abbreviation
  const grouped: Record<string, ExpansionSource[]> = {}
  for (const entry of expansions) {
    if (!grouped[entry.abbrev]) grouped[entry.abbrev] = []
    grouped[entry.abbrev].push(entry)
  }

  return (
    <div className="text-xs text-[var(--claude-text-secondary)]">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 hover:text-[var(--claude-text-primary)] transition-colors"
        title="Zoekopdracht uitgebreid met afkortingen"
      >
        <Info className="w-3.5 h-3.5 text-[var(--claude-accent)]" />
        <span>Zoekopdracht uitgebreid</span>
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {open && (
        <div className="mt-2 p-3 rounded-lg border border-[var(--claude-border)] bg-[var(--claude-surface)] space-y-3">
          {Object.entries(grouped).map(([abbrev, entries]) => (
            <div key={abbrev}>
              <p className="font-medium text-[var(--claude-text-primary)] mb-1">
                {abbrev} <span className="text-[var(--claude-text-secondary)]">→</span>{' '}
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
  )
}
