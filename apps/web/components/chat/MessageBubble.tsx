"use client"

import { Badge } from "@/components/ui/badge"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { CheckCircle2, Zap } from "lucide-react"

interface MessageBubbleProps {
  role: "user" | "assistant"
  content: string
  agentType?: string
  timestamp?: Date
  metadata?: Record<string, any>
}

const agentLabels: Record<string, string> = {
  task: "Задача",
  meeting: "Встреча",
  message: "Сообщение",
  knowledge: "Знание",
  rag_query: "Поиск",
  default: "Ответ"
}

const agentIcons: Record<string, string> = {
  task: "✅",
  meeting: "📅",
  message: "💬",
  knowledge: "📚",
  rag_query: "🔍",
  default: "🤖"
}

export function MessageBubble({ role, content, agentType, timestamp, metadata }: MessageBubbleProps) {
  const isUser = role === "user"
  const chainResponses = metadata?.chain_responses || []

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3 animate-in fade-in slide-in-from-bottom-1 duration-200`}
    >
      <div className={`max-w-[80%] ${isUser ? "order-2" : "order-1"}`}>
        <div
          className={`rounded-2xl px-4 py-2 shadow-sm text-[15px] ${
            isUser
              ? "bg-primary text-primary-foreground ml-auto rounded-tr-none"
              : "bg-muted text-foreground mr-auto rounded-tl-none border border-border/50"
          }`}
        >
          {!isUser && agentType && (
            <div className="mb-2 flex items-center gap-2">
              <Badge variant="secondary" className="text-xs flex items-center gap-1.5">
                <span>{agentIcons[agentType] || "🤖"}</span>
                <span>{agentLabels[agentType] || agentType}</span>
                {metadata?.chain_responses && metadata.chain_responses.length > 0 && (
                  <Zap className="w-3 h-3 text-yellow-500" />
                )}
              </Badge>
              {chainResponses.length > 0 && (
                <div className="flex gap-1">
                  {chainResponses.map((chain: any, idx: number) => (
                    <Badge key={idx} variant="outline" className="text-xs">
                      {agentIcons[chain.agent_type] || "→"} {agentLabels[chain.agent_type] || chain.agent_type}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
          
          {/* Отображение действий */}
          {!isUser && metadata?.actions && metadata.actions.length > 0 && (
            <div className="mb-2 space-y-1">
              {metadata.actions.map((action: any, idx: number) => (
                <div key={idx} className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <CheckCircle2 className="w-3 h-3 text-green-500" />
                  {action.type === "task_created" && (
                    <span>Задача создана: {action.task_id?.substring(0, 8)}...</span>
                  )}
                  {action.type === "tasks_created_from_meeting" && (
                    <span>Создано {action.tasks?.length || 0} задач из встречи</span>
                  )}
                  {action.type === "meeting_processed" && (
                    <span>Встреча обработана: {action.meeting_id?.substring(0, 8)}...</span>
                  )}
                  {action.type === "knowledge_saved" && (
                    <span>Знание сохранено: {action.doc_id?.substring(0, 8)}...</span>
                  )}
                  {action.type === "message_scheduled" && (
                    <span>Сообщение запланировано</span>
                  )}
                  {action.type === "rag_search" && (
                    <span>Найдено результатов: {action.results_count || 0}</span>
                  )}
                </div>
              ))}
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
