"use client"

import { useState, useEffect, useRef, useCallback } from 'react'
import { useTheme } from 'next-themes'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import {
  Settings,
  Sun,
  Moon,
  Monitor,
  Palette,
  Info,
  RefreshCw,
  Loader2,
  DatabaseZap,
  RotateCcw,
  BookText,
} from 'lucide-react'

type ServiceStatus = 'healthy' | 'unhealthy' | 'unreachable' | 'unknown' | 'loading'
type IndexStatus = 'idle' | 'running' | 'done' | 'error'

interface StatusResult {
  backend: ServiceStatus
  qdrant: ServiceStatus
  ollama: ServiceStatus
}

interface SettingsPanelProps {
  className?: string
  isChatLoading?: boolean
  queryExpansionEnabled?: boolean
  onQueryExpansionChange?: (enabled: boolean) => void
}

const DOT_COLOR: Record<ServiceStatus, string> = {
  healthy: 'bg-green-500',
  unhealthy: 'bg-red-500',
  unreachable: 'bg-red-500',
  unknown: 'bg-gray-400',
  loading: 'bg-gray-400',
}

const STATUS_LABEL: Record<ServiceStatus, string> = {
  healthy: 'Online',
  unhealthy: 'Ongezond',
  unreachable: 'Niet bereikbaar',
  unknown: 'Onbekend',
  loading: 'Controleren...',
}

const STATUS_COLOR: Record<ServiceStatus, string> = {
  healthy: 'text-green-600 dark:text-green-400',
  unhealthy: 'text-red-600 dark:text-red-400',
  unreachable: 'text-red-600 dark:text-red-400',
  unknown: 'text-[var(--claude-text-secondary)]',
  loading: 'text-[var(--claude-text-secondary)]',
}

function StatusRow({ label, status }: { label: string; status: ServiceStatus }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-[var(--claude-text-secondary)]">{label}</span>
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${DOT_COLOR[status]}`} />
        <span className={`text-sm font-medium ${STATUS_COLOR[status]}`}>
          {STATUS_LABEL[status]}
        </span>
      </div>
    </div>
  )
}

export function SettingsPanel({ className = '', isChatLoading = false, queryExpansionEnabled = true, onQueryExpansionChange }: SettingsPanelProps) {
  const { theme, setTheme, systemTheme } = useTheme()
  const [isOpen, setIsOpen] = useState(false)
  const [status, setStatus] = useState<StatusResult>({ backend: 'loading', qdrant: 'loading', ollama: 'loading' })
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)
  const [isChecking, setIsChecking] = useState(false)

  // Indexing state
  const [indexStatus, setIndexStatus] = useState<IndexStatus>('idle')
  const [indexMessage, setIndexMessage] = useState('')
  const [activeIndexAction, setActiveIndexAction] = useState<'normal' | 'full' | 'abbreviations' | null>(null)
  const [progressCurrent, setProgressCurrent] = useState(0)
  const [progressTotal, setProgressTotal] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const feedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const currentTheme = theme === 'system' ? systemTheme : theme

  const checkStatus = async () => {
    setIsChecking(true)
    try {
      const res = await fetch('/api/health')
      const data = await res.json()
      setStatus({
        backend: data.backend ?? 'unknown',
        qdrant: data.qdrant ?? 'unknown',
        ollama: data.ollama ?? 'unknown',
      })
    } catch {
      setStatus({ backend: 'unreachable', qdrant: 'unknown', ollama: 'unknown' })
    } finally {
      setIsChecking(false)
      setCheckedAt(new Date())
    }
  }

  // Check on mount for the dot indicator
  useEffect(() => {
    checkStatus()
  }, [])

  // Re-check when dialog opens, but not while a chat request is in flight
  useEffect(() => {
    if (isOpen && !isChatLoading) checkStatus()
  }, [isOpen])

  // Stop polling helper
  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  // Reset index status to idle after 5 s (for done/error feedback)
  const scheduleReset = useCallback(() => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current)
    feedbackTimerRef.current = setTimeout(() => {
      setIndexStatus('idle')
      setIndexMessage('')
      setActiveIndexAction(null)
    }, 5000)
  }, [])

  // Poll /api/index/status every 2 s while running
  const startPoll = useCallback(() => {
    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch('/api/index/status')
        const data = await res.json()
        setIndexStatus(data.status)
        setIndexMessage(data.message ?? '')
        setProgressCurrent(data.progress_current ?? 0)
        setProgressTotal(data.progress_total ?? 0)
        if (data.status === 'done' || data.status === 'error') {
          stopPoll()
          scheduleReset()
        }
      } catch {
        // network hiccup — keep polling
      }
    }, 2000)
  }, [stopPoll, scheduleReset])

  // Clean up on unmount or dialog close
  useEffect(() => {
    return () => {
      stopPoll()
      if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current)
    }
  }, [stopPoll])

  useEffect(() => {
    if (!isOpen) {
      stopPoll()
      return
    }
    // On open, sync with backend — if indexing finished while panel was closed, pick it up
    fetch('/api/index/status')
      .then(r => r.json())
      .then(data => {
        setIndexStatus(data.status)
        setIndexMessage(data.message ?? '')
        setProgressCurrent(data.progress_current ?? 0)
        setProgressTotal(data.progress_total ?? 0)
        if (data.status === 'running') {
          startPoll()
        } else if (data.status === 'done' || data.status === 'error') {
          scheduleReset()
        }
      })
      .catch(() => {})
  }, [isOpen, stopPoll, startPoll, scheduleReset])

  const handleIndex = async (action: 'normal' | 'full' | 'abbreviations') => {
    try {
      const res = await fetch('/api/index', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_reindex: action === 'full',
          build_abbreviations: action === 'abbreviations',
        }),
      })
      if (res.status === 409) {
        setIndexMessage('Indexering is al bezig.')
        return
      }
      if (!res.ok) {
        setIndexStatus('error')
        setIndexMessage('Kon indexering niet starten.')
        scheduleReset()
        return
      }
      setActiveIndexAction(action)
      setIndexStatus('running')
      setIndexMessage('Indexering gestart...')
      startPoll()
    } catch {
      setIndexStatus('error')
      setIndexMessage('Verbindingsfout.')
      scheduleReset()
    }
  }

  const themeOptions = [
    { value: 'light', label: 'Licht', icon: Sun },
    { value: 'dark', label: 'Donker', icon: Moon },
    { value: 'system', label: 'Systeem', icon: Monitor },
  ]

  // Dot color is red if any service is not healthy, green if all healthy
  const allHealthy = status.backend === 'healthy' && status.qdrant === 'healthy' && status.ollama === 'healthy'
  const anyLoading = status.backend === 'loading' || status.qdrant === 'loading' || status.ollama === 'loading'
  const dotColor = anyLoading ? 'bg-gray-400' : allHealthy ? 'bg-green-500' : 'bg-red-500'

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={`relative h-8 w-8 p-0 hover:bg-[var(--claude-surface)] ${className}`}
          title="Instellingen"
        >
          <Settings className="h-4 w-4" />
          <span className={`absolute top-0.5 right-0.5 w-2 h-2 rounded-full ${dotColor} ring-1 ring-[var(--claude-bg)]`} />
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-[425px] bg-[var(--claude-bg)] border-[var(--claude-border)]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[var(--claude-text-primary)]">
            <Palette className="h-5 w-5" />
            Voorkeuren
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* System status */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium text-[var(--claude-text-primary)]">
                Systeemstatus
              </Label>
              <button
                onClick={checkStatus}
                disabled={isChecking || isChatLoading}
                className="text-[var(--claude-text-secondary)] hover:text-[var(--claude-text-primary)] disabled:opacity-40 transition-colors"
                title={isChatLoading ? 'Bezig met chat verzoek' : 'Opnieuw controleren'}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isChecking ? 'animate-spin' : ''}`} />
              </button>
            </div>
            <Card className="px-3 py-2 bg-[var(--claude-surface)] border-[var(--claude-border)] divide-y divide-[var(--claude-border)]">
              <StatusRow label="Backend" status={status.backend} />
              <StatusRow label="Qdrant" status={status.qdrant} />
              <StatusRow label="Ollama" status={status.ollama} />
            </Card>
            {checkedAt && (
              <p className="text-xs text-[var(--claude-text-secondary)]">
                {isChatLoading ? 'Status wordt niet bijgewerkt tijdens chat verzoek' : `Gecontroleerd om ${checkedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`}
              </p>
            )}
          </div>

          {/* Index sync */}
          <div className="space-y-2">
            <Label className="text-sm font-medium text-[var(--claude-text-primary)]">
              Index synchroniseren
            </Label>
            <div className="grid grid-cols-3 gap-2">
              {([
                { action: 'normal', icon: DatabaseZap, label: 'Herindexeer', title: 'Haalt nieuwe en gewijzigde documenten op' },
                { action: 'full', icon: RotateCcw, label: 'Volledig', title: 'Verwijdert de bestaande index en begint opnieuw' },
                { action: 'abbreviations', icon: BookText, label: 'Afkortingen', title: 'Herbouwt alleen het afkortingenwoordenboek' },
              ] as const).map(({ action, icon: Icon, label, title }) => (
                <button
                  key={action}
                  onClick={() => handleIndex(action)}
                  disabled={indexStatus === 'running'}
                  title={title}
                  className={`
                    flex flex-col items-center gap-2 p-3 rounded-lg border transition-all disabled:opacity-50 disabled:cursor-not-allowed
                    ${indexStatus === 'running' && activeIndexAction === action
                      ? 'border-[var(--claude-accent)] bg-[var(--claude-accent)]/10'
                      : 'border-[var(--claude-border)] hover:border-[var(--claude-text-secondary)]'
                    }
                  `}
                >
                  {indexStatus === 'running' && activeIndexAction === action ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Icon className="h-4 w-4" />
                  )}
                  <span className="text-xs font-medium">{label}</span>
                </button>
              ))}
            </div>
            {indexStatus === 'running' && progressTotal > 0 && (
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-[var(--claude-text-secondary)]">
                  <span>Documenten ingebed</span>
                  <span>{progressCurrent} / {progressTotal}</span>
                </div>
                <div className="w-full h-1.5 bg-[var(--claude-border)] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[var(--claude-accent)] rounded-full transition-all duration-300"
                    style={{ width: `${Math.round((progressCurrent / progressTotal) * 100)}%` }}
                  />
                </div>
              </div>
            )}
            {indexMessage && (
              <p className={`text-xs ${
                indexStatus === 'done'
                  ? 'text-green-600 dark:text-green-400'
                  : indexStatus === 'error'
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-[var(--claude-text-secondary)]'
              }`}>
                {indexMessage}
              </p>
            )}
          </div>

          {/* Query expansion toggle */}
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm font-medium text-[var(--claude-text-primary)]">
                Zoekopdracht uitbreiden
              </Label>
              <p className="text-xs text-[var(--claude-text-secondary)] mt-0.5">
                Afkortingen automatisch verrijken via afkorting-woordenboek
              </p>
            </div>
            <button
              onClick={() => onQueryExpansionChange?.(!queryExpansionEnabled)}
              className={`
                relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 transition-colors duration-200
                ${queryExpansionEnabled
                  ? 'bg-[var(--claude-accent)] border-[var(--claude-accent)]'
                  : 'bg-[var(--claude-border)] border-[var(--claude-border)]'
                }
              `}
              title={queryExpansionEnabled ? 'Uitschakelen' : 'Inschakelen'}
            >
              <span
                className={`
                  inline-block h-4 w-4 mt-0.5 rounded-full bg-white shadow-sm transition-transform duration-200
                  ${queryExpansionEnabled ? 'translate-x-5' : 'translate-x-0.5'}
                `}
              />
            </button>
          </div>

          {/* Theme selection */}
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium text-[var(--claude-text-primary)]">
              Weergave
            </Label>
            <div className="grid grid-cols-3 gap-2">
              {themeOptions.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  onClick={() => setTheme(value)}
                  className={`
                    flex flex-col items-center gap-2 p-3 rounded-lg border transition-all
                    ${theme === value
                      ? 'border-[var(--claude-accent)] bg-[var(--claude-accent)]/10'
                      : 'border-[var(--claude-border)] hover:border-[var(--claude-text-secondary)]'
                    }
                  `}
                >
                  <Icon className="h-4 w-4" />
                  <span className="text-xs font-medium">{label}</span>
                </button>
              ))}
            </div>
          </div>

          <Card className="p-3 bg-[var(--claude-surface)] border-[var(--claude-border)]">
            <div className="flex items-start gap-3">
              <Info className="h-4 w-4 text-[var(--claude-accent)] mt-0.5" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-[var(--claude-text-primary)]">
                  Huidig thema: {currentTheme === 'light' ? 'licht' : currentTheme === 'dark' ? 'donker' : 'systeem'}
                </p>
                <p className="text-xs text-[var(--claude-text-secondary)]">
                  {theme === 'system'
                    ? 'Past automatisch aan bij uw systeemvoorkeur'
                    : `${theme === 'light' ? 'Lichte' : 'Donkere'} modus gebruikt`
                  }
                </p>
              </div>
            </div>
          </Card>

          <div className="pt-2 border-t border-[var(--claude-border)]">
            <div className="space-y-2">
              <p className="text-xs text-[var(--claude-text-secondary)]">
                Ypsilon RAG Assistent v1.0
              </p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default SettingsPanel
