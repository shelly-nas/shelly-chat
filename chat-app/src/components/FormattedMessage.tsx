import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ExternalLink } from 'lucide-react'

interface FormattedMessageProps {
  content: string
  role: 'user' | 'assistant'
}

export function FormattedMessage({ content, role }: FormattedMessageProps) {
  if (role === 'user') {
    return (
      <div className="text-sm md:text-base whitespace-pre-wrap break-words">
        {content}
      </div>
    )
  }

  // Format the assistant response with custom styling
  const formatAssistantMessage = (text: string) => {
    return text + '\n\n---\n\n**Belangrijk:** *Voor volledigheid en accuracy wordt geadviseerd de originele brondocumenten te raadplegen.*'
  }

  const formattedContent = formatAssistantMessage(content)

  return (
    <div className="formatted-message">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Custom components for different markdown elements
          p: ({ children }) => (
            <p className="mb-3 text-sm md:text-base leading-relaxed text-[var(--claude-text-primary)] last:mb-0">
              {children}
            </p>
          ),
          
          strong: ({ children }) => (
            <strong className="font-semibold text-[var(--claude-text-primary)]">
              {children}
            </strong>
          ),
          
          em: ({ children }) => (
            <em className="italic text-[var(--claude-text-secondary)]">
              {children}
            </em>
          ),
          
          ul: ({ children }) => (
            <ul className="mb-3 ml-4 space-y-1 list-disc text-sm md:text-base">
              {children}
            </ul>
          ),
          
          ol: ({ children }) => (
            <ol className="mb-3 ml-4 space-y-1 list-decimal text-sm md:text-base">
              {children}
            </ol>
          ),
          
          li: ({ children }) => (
            <li className="text-[var(--claude-text-primary)] leading-relaxed">
              {children}
            </li>
          ),
          
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-[var(--claude-accent)] pl-4 my-3 italic text-[var(--claude-text-secondary)]">
              {children}
            </blockquote>
          ),
          
          code: ({ node, className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '')
            
            if (!match) {
              // Inline code
              return (
                <code 
                  className="px-1.5 py-0.5 bg-[var(--claude-surface)] border border-[var(--claude-border)] rounded text-sm font-mono text-[var(--claude-accent)]"
                  {...props}
                >
                  {children}
                </code>
              )
            }
            
            // Code block
            return (
              <div className="my-3 rounded-lg bg-[var(--claude-surface)] border border-[var(--claude-border)] overflow-hidden">
                <div className="px-3 py-2 bg-[var(--claude-border)] text-xs font-medium text-[var(--claude-text-secondary)] border-b border-[var(--claude-border)]">
                  {match[1]}
                </div>
                <pre className="p-3 overflow-x-auto">
                  <code className="text-sm font-mono text-[var(--claude-text-primary)]">
                    {children}
                  </code>
                </pre>
              </div>
            )
          },
          
          hr: () => (
            <hr className="my-6 border-0 h-px bg-gradient-to-r from-transparent via-[var(--claude-border)] to-transparent" />
          ),
          
          h1: ({ children }) => (
            <h1 className="text-xl font-bold mb-3 text-[var(--claude-text-primary)]">
              {children}
            </h1>
          ),
          
          h2: ({ children }) => (
            <h2 className="text-lg font-semibold mb-2 text-[var(--claude-text-primary)]">
              {children}
            </h2>
          ),
          
          h3: ({ children }) => (
            <h3 className="text-md font-medium mb-2 text-[var(--claude-text-primary)]">
              {children}
            </h3>
          ),
          
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--claude-accent)] hover:text-[var(--claude-accent-hover)] underline decoration-1 underline-offset-2 inline-flex items-center gap-1"
            >
              {children}
              <ExternalLink className="w-3 h-3" />
            </a>
          ),
        }}
      >
        {formattedContent}
      </ReactMarkdown>
      
      <style jsx>{`
        .formatted-message :global(.source-ref) {
          @apply inline-flex items-center justify-center w-6 h-5 text-xs font-medium bg-[var(--claude-accent)]/10 text-[var(--claude-accent)] border border-[var(--claude-accent)]/20 rounded-full mx-0.5;
        }
        
        .formatted-message :global(.source-ref:hover) {
          @apply bg-[var(--claude-accent)]/20 border-[var(--claude-accent)]/40 cursor-pointer;
        }
      `}</style>
    </div>
  )
}