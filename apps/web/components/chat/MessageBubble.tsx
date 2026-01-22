"use client"

import { Badge } from "@/components/ui/badge"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

interface MessageBubbleProps {
  role: "user" | "assistant"
  content: string
  agentType?: string
  timestamp?: Date
}

const agentLabels: Record<string, string> = {
  task: "Задача",
  meeting: "Встреча",
  message: "Сообщение",
  knowledge: "Знание",
  rag_query: "Поиск",
  default: "Ответ"
}

export function MessageBubble({ role, content, agentType, timestamp }: MessageBubbleProps) {
  const isUser = role === "user"

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? "order-2" : "order-1"}`}>
        <div
          className={`rounded-lg px-4 py-3 ${
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-foreground"
          }`}
        >
          {!isUser && agentType && (
            <div className="mb-2">
              <Badge variant="secondary" className="text-xs">
                {agentLabels[agentType] || agentType}
              </Badge>
            </div>
          )}
          <div className="text-sm leading-relaxed prose prose-sm max-w-none [&_strong]:font-semibold [&_em]:italic [&_a]:text-primary [&_a]:underline">
            {isUser ? (
              <p className="whitespace-pre-wrap">{content}</p>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            )}
          </div>
          {timestamp && (
            <div className={`text-xs mt-2 ${isUser ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
              {timestamp.toLocaleTimeString("ru-RU", {
                hour: "2-digit",
                minute: "2-digit"
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
