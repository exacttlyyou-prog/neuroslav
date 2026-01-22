"use client"

import { MessageBubble } from "./MessageBubble"

export interface Message {
  role: "user" | "assistant"
  content: string
  agentType?: string
  timestamp: Date
  metadata?: Record<string, any>
}

interface MessageListProps {
  messages: Message[]
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <p className="text-sm">Начните диалог, чтобы увидеть сообщения</p>
      </div>
    )
  }

  return (
    <div className="space-y-4 pb-4">
      {messages.map((message, idx) => (
        <MessageBubble
          key={idx}
          role={message.role}
          content={message.content}
          agentType={message.agentType}
          timestamp={message.timestamp}
        />
      ))}
    </div>
  )
}
