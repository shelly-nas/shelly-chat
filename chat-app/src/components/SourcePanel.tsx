'use client'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChevronLeftIcon, ChevronRightIcon, ExternalLinkIcon } from '@radix-ui/react-icons'

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

interface SourcePanelProps {
  contexts: SourceContext[]
  currentIndex: number
  onIndexChange: (index: number) => void
  onOpenFile: (path: string) => void
}

export function SourcePanel({
  contexts,
  currentIndex,
  onIndexChange,
  onOpenFile,
}: SourcePanelProps) {
  if (!contexts.length) {
    return (
      <Card className="h-full">
        <CardHeader>
          <CardTitle>Sources</CardTitle>
          <CardDescription>No sources available</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const currentSource = contexts[currentIndex]
  const fileName = currentSource.file_path.split('/').pop() || currentSource.file_path

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex-shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">
            Sources ({currentIndex + 1}/{contexts.length})
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onIndexChange(Math.max(0, currentIndex - 1))}
              disabled={currentIndex === 0}
            >
              <ChevronLeftIcon className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onIndexChange(Math.min(contexts.length - 1, currentIndex + 1))}
              disabled={currentIndex === contexts.length - 1}
            >
              <ChevronRightIcon className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <CardDescription className="text-xs font-medium">
                {fileName}
              </CardDescription>
              {currentSource.chunk_type && (
                <span className={`px-1.5 py-0.5 text-[10px] rounded font-medium ${
                  currentSource.chunk_type === 'parent'
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                    : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                }`}>
                  {currentSource.chunk_type === 'parent' ? 'Parent' : 'Child'}
                </span>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                if (currentSource.source_url) {
                  window.open(currentSource.source_url, '_blank', 'noopener,noreferrer')
                } else {
                  onOpenFile(currentSource.file_path)
                }
              }}
              className="h-6 px-2"
            >
              <ExternalLinkIcon className="h-3 w-3" />
            </Button>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>Relevantie: {
              (() => {
                const score = currentSource.similarity;
                let percentage;
                
                if (score === undefined || score === null) {
                  return "N/A";
                }
                
                // Handle different score types based on range and context
                if (score <= 1 && score >= 0) {
                  // Standard similarity scores (0-1) where higher = more similar
                  percentage = score * 100;
                } else if (score > 1 && score <= 5) {
                  // Distance or negative log scores (1-5) where lower = more similar
                  // Convert to 0-100% where score 1 = 100%, score 5 = 0%
                  percentage = Math.max(0, ((5 - score) / 4) * 100);
                } else if (score < 0) {
                  // Negative scores (often from rerankers) where higher (less negative) = more similar
                  // Convert -10 to 0 range to 0-100%
                  const minScore = -10;
                  const maxScore = 0;
                  percentage = Math.max(0, Math.min(100, ((score - minScore) / (maxScore - minScore)) * 100));
                } else {
                  // Very large scores - treat as inverse relevance
                  percentage = Math.max(0, Math.min(100, 100 / Math.max(1, Math.log10(score + 1))));
                }
                
                return `${Math.round(Math.max(0, Math.min(100, percentage)))}%`;
              })()
            }</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 p-4 pt-0 min-h-0 overflow-hidden">
        <ScrollArea className="h-full w-full">
          <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap break-words">
            {currentSource.content}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}