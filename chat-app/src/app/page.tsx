'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SourcePanel } from '@/components/SourcePanel'
import { SettingsPanel } from '@/components/SettingsPanel'
import { FormattedMessage } from '@/components/FormattedMessage'
import { QueryExpansionBubble } from '@/components/QueryExpansionBubble'
import {
  Send,
  RotateCcw,
  Bot,
  User,
  FileText,
  Sparkles,
  Loader2
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface SourceContext {
  content: string
  file_path: string
  source_url?: string
  page_number: number
  start_line: number
  end_line: number
  section_context: string
  similarity: number
  source_num: number
  chunk_type?: 'parent' | 'child'
}

export interface ExpansionSource {
  abbrev: string
  term: string
  source_url: string
  file_name: string
  snippet: string
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp?: Date
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [contexts, setContexts] = useState<SourceContext[]>([])
  const [currentSourceIndex, setCurrentSourceIndex] = useState(0)
  const [metrics, setMetrics] = useState<any>(null)
  const [showMobileSources, setShowMobileSources] = useState(false)
  const [expansionsByMsg, setExpansionsByMsg] = useState<Map<string, ExpansionSource[]>>(new Map())
  const [queryExpansionEnabled, setQueryExpansionEnabled] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true
    return localStorage.getItem('queryExpansionEnabled') !== 'false'
  })
  const abortRef = useRef<AbortController | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleNewChat = useCallback(async () => {
    abortRef.current?.abort()
    try {
      await fetch('/api/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: 'default' }),
      })
    } catch (error) {
      console.error('Failed to reset session:', error)
    }
    setMessages([])
    setContexts([])
    setCurrentSourceIndex(0)
    setMetrics(null)
    setExpansionsByMsg(new Map())
  }, [])

  const handleOpenFile = useCallback(async (path: string) => {
    try {
      await fetch(`/api/open-pdf?path=${encodeURIComponent(path)}`)
    } catch (error) {
      console.error('Failed to open file:', error)
    }
  }, [])

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    const query = input.trim()
    if (!query || isLoading) return

    setInput('')
    setIsLoading(true)
    setCurrentSourceIndex(0)

    const userMsgId = crypto.randomUUID()
    const userMsg: Message = {
      id: userMsgId,
      role: 'user',
      content: query,
      timestamp: new Date()
    }
    const assistantMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: new Date()
    }
    setMessages(prev => [...prev, userMsg, assistantMsg])

    abortRef.current = new AbortController()

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, session_id: 'default', query_expansion_enabled: queryExpansionEnabled }),
        signal: abortRef.current.signal,
      })

      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const handleEvent = (eventType: string, payload: string) => {
        if (eventType === 'expansions') {
          const parsed: ExpansionSource[] = JSON.parse(payload)
          if (parsed.length > 0) {
            setExpansionsByMsg(prev => new Map(prev).set(userMsgId, parsed))
          }
        } else if (eventType === 'token') {
          const token: string = JSON.parse(payload)
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantMsg.id ? { ...m, content: m.content + token } : m
            )
          )
        } else if (eventType === 'contexts') {
          setContexts(JSON.parse(payload))
        } else if (eventType === 'metrics') {
          setMetrics(JSON.parse(payload))
        } else if (eventType === 'done') {
          setIsLoading(false)
        } else if (eventType === 'error') {
          const errorData = JSON.parse(payload)
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantMsg.id
                ? { ...m, content: errorData.message || 'Er is een fout opgetreden.' }
                : m
            )
          )
          setIsLoading(false)
        }
      }

      // Parse one complete SSE record ("event: ...\ndata: ...") into a handler
      // call. Records are delimited by a blank line; a single record may span
      // multiple network chunks, so we only process whole records here.
      const processRecord = (record: string) => {
        let eventType = ''
        const dataLines: string[] = []
        for (const line of record.split('\n')) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
        }
        if (!eventType || dataLines.length === 0) return
        handleEvent(eventType, dataLines.join('\n'))
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Split off every complete record (terminated by a blank line),
        // keeping any trailing partial record in the buffer for the next read.
        let sep: number
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const record = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          processRecord(record)
        }
      }

      // Flush any final record that arrived without a trailing blank line.
      if (buffer.trim()) processRecord(buffer)
    } catch (error: any) {
      console.error('Chat fout:', error)
      if (error.name !== 'AbortError') {
        setMessages(prev => {
          const lastMsg = prev[prev.length - 1]
          if (lastMsg?.role === 'assistant') {
            return prev.map((m, idx) => 
              idx === prev.length - 1 
                ? { ...m, content: 'Er is een fout opgetreden. Probeer het later opnieuw.' }
                : m
            )
          }
          return prev
        })
      }
    } finally {
      setIsLoading(false)
    }
  }, [input, isLoading, queryExpansionEnabled])

  return (
    <div className="flex h-screen bg-[var(--claude-bg)] transition-colors duration-200 overflow-hidden">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full">
        {/* Header */}
        <header className="border-b border-[var(--claude-border)] bg-[var(--claude-bg)]/80 backdrop-blur-sm sticky top-0 z-10 flex-shrink-0">
          <div className="px-4 md:px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-to-br from-[var(--claude-accent)] to-blue-600 rounded-full flex items-center justify-center">
                  <Bot className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[var(--claude-text-primary)]">
                    Ypsilon Assistent
                  </h1>
                  <p className="text-xs text-[var(--claude-text-secondary)] hidden sm:block">
                    AI-geavanceerde documentzoeking
                  </p>
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              {contexts.length > 0 && (
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="md:hidden text-[var(--claude-text-secondary)] hover:bg-[var(--claude-surface)]"
                  onClick={() => setShowMobileSources(true)}
                >
                  <FileText className="w-4 h-4 mr-1" />
                  {contexts.length}
                </Button>
              )}
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={handleNewChat}
                disabled={isLoading}
                className="text-[var(--claude-text-secondary)] hover:bg-[var(--claude-surface)]"
                title="Nieuw Gesprek"
              >
                <RotateCcw className="w-4 h-4" />
              </Button>
              <SettingsPanel
                isChatLoading={isLoading}
                queryExpansionEnabled={queryExpansionEnabled}
                onQueryExpansionChange={(enabled) => {
                  setQueryExpansionEnabled(enabled)
                  localStorage.setItem('queryExpansionEnabled', String(enabled))
                }}
              />
            </div>
          </div>
        </header>

        {/* Messages Area */}
        <div className="flex-1 min-h-0 overflow-hidden">
          <ScrollArea className="h-full w-full custom-scrollbar">
            <div className="max-w-4xl mx-auto px-4 md:px-6 py-6 min-h-full">
              {messages.length === 0 && (
                <div className="text-center pt-16 pb-8 animate-fadeIn">
                  <div className="w-16 h-16 bg-gradient-to-br from-[var(--claude-accent)] to-blue-600 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Sparkles className="w-8 h-8 text-white" />
                  </div>
                  <h2 className="text-2xl font-semibold mb-2 text-[var(--claude-text-primary)]">
                    Welkom bij Ypsilon Assistent
                  </h2>
                  <p className="text-[var(--claude-text-secondary)] mb-8 max-w-md mx-auto">
                    Stel vragen over uw geïndexeerde documenten en krijg AI-geavanceerde antwoorden met bronverwijzingen.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl mx-auto">
                    {[
                      "Wat zijn de taken van de beheerder van de week?",
                      "Hoe werk het Renovate proces?",
                      "Hoeveel mensen zitten er in team Ypsilon?",
                      "Welke test framework wordt er gebruikt?",
                      "Hoe is een VI versleuteld in EAD?"
                    ].map((suggestion, index) => (
                      <button
                        key={index}
                        onClick={() => setInput(suggestion)}
                        className="p-3 text-left rounded-lg border border-[var(--claude-border)] hover:border-[var(--claude-accent)] transition-all duration-200 hover:bg-[var(--claude-surface)] group"
                      >
                        <span className="text-sm text-[var(--claude-text-primary)] group-hover:text-[var(--claude-accent)]">
                          {suggestion}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              
              <div className="space-y-6">
                {messages.map((message) => (
                  <div key={message.id} className="animate-fadeIn">
                    {/* Message bubble */}
                    <div className={message.role === 'user' ? 'text-right' : 'text-left'}>
                      <div className={`
                        inline-block max-w-[85%] p-4 rounded-2xl
                        ${message.role === 'user'
                          ? 'bg-[var(--claude-accent)] text-white rounded-br-md'
                          : 'bg-[var(--claude-surface)] border border-[var(--claude-border)] text-[var(--claude-text-primary)] rounded-bl-md'
                        }
                      `}>
                        {message.role === 'assistant' && message.content === '' && isLoading ? (
                          <div className="flex items-center gap-2 text-[var(--claude-text-secondary)]">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span className="text-sm">Aan het denken...</span>
                          </div>
                        ) : (
                          <FormattedMessage
                            content={message.content}
                            role={message.role}
                          />
                        )}
                      </div>

                      {message.timestamp && (
                        <div className={`
                          text-xs text-[var(--claude-text-secondary)] mt-1 px-1
                          ${message.role === 'user' ? 'text-right' : 'text-left'}
                        `}>
                          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      )}
                    </div>

                    {/* Expansion bubble — shown after the user message it belongs to */}
                    {message.role === 'user' && expansionsByMsg.has(message.id) && (
                      <QueryExpansionBubble expansions={expansionsByMsg.get(message.id)!} />
                    )}
                  </div>
                ))}
              </div>
              
              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>
        </div>

        {/* Input Area */}
        <div className="border-t border-[var(--claude-border)] bg-[var(--claude-bg)] p-4">
          <div className="max-w-4xl mx-auto">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Stel een vraag over uw documenten..."
                disabled={isLoading}
                className="flex-1 h-12 px-4 border-[var(--claude-border)] bg-[var(--claude-surface)] text-[var(--claude-text-primary)] placeholder:text-[var(--claude-text-secondary)] focus:border-[var(--claude-accent)] focus:ring-1 focus:ring-[var(--claude-accent)] rounded-xl"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSubmit(e as any)
                  }
                }}
              />
              <Button 
                type="submit" 
                disabled={isLoading || !input.trim()} 
                size="sm"
                className="h-12 w-12 p-0 bg-[var(--claude-accent)] hover:bg-[var(--claude-accent-hover)] text-white rounded-xl"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
            
            {metrics && (
              <div className="text-xs text-[var(--claude-text-secondary)] mt-2 text-right">
                Response in {Math.round(metrics.wall_time_s)}s • {metrics.model}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Sources Sidebar - Hidden on mobile */}
      {contexts.length > 0 && (
        <div className="hidden lg:flex w-80 border-l border-[var(--claude-border)] bg-[var(--claude-surface)]/50 flex-col h-full">
          <div className="p-4 border-b border-[var(--claude-border)] flex-shrink-0">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="w-4 h-4 text-[var(--claude-accent)]" />
              <h3 className="font-medium text-[var(--claude-text-primary)]">Bronnen</h3>
              <span className="text-xs bg-[var(--claude-accent)]/10 text-[var(--claude-accent)] px-2 py-1 rounded-full">
                {contexts.length}
              </span>
            </div>
            <p className="text-xs text-[var(--claude-text-secondary)]">
              Gerefereerde documenten voor dit gesprek
            </p>
          </div>
          <div className="flex-1 p-4 min-h-0 overflow-hidden">
            <SourcePanel
              contexts={contexts}
              currentIndex={currentSourceIndex}
              onIndexChange={setCurrentSourceIndex}
              onOpenFile={handleOpenFile}
            />
          </div>
        </div>
      )}

      {/* Mobile Sources Dialog */}
      <Dialog open={showMobileSources} onOpenChange={setShowMobileSources}>
        <DialogContent className="max-w-[95vw] max-h-[80vh] p-0 bg-[var(--claude-bg)] border-[var(--claude-border)] flex flex-col">
          <DialogHeader className="p-4 pb-2 border-b border-[var(--claude-border)] flex-shrink-0">
            <DialogTitle className="flex items-center gap-2 text-[var(--claude-text-primary)]">
              <FileText className="w-4 h-4 text-[var(--claude-accent)]" />
              Bronnen ({contexts.length})
            </DialogTitle>
          </DialogHeader>
          <div className="px-4 pb-4 flex-1 min-h-0 overflow-hidden">
            <SourcePanel
              contexts={contexts}
              currentIndex={currentSourceIndex}
              onIndexChange={setCurrentSourceIndex}
              onOpenFile={handleOpenFile}
            />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
