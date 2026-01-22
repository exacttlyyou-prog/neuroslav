"use client"

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { MessageList, Message } from "./MessageList"
import { QuickActions } from "./QuickActions"
import { apiPost } from "@/lib/api"

interface ChatResponse {
  agent_type: string
  response: string
  actions: Array<{ type: string; [key: string]: any }>
  metadata: Record<string, any>
}

export function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || loading) return
    await handleSendMessage(input.trim())
  }

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleProcessLastMeeting = async () => {
    const message = "Обработай последнюю встречу"
    setInput(message)
    
    // Автоматически отправляем через небольшую задержку
    setTimeout(() => {
      handleSendMessage(message)
    }, 100)
  }

  const handleSendMessage = async (messageText: string) => {
    if (!messageText.trim() || loading) return

    const userMessage: Message = {
      role: "user",
      content: messageText.trim(),
      timestamp: new Date()
    }

    setMessages((prev) => [...prev, userMessage])
    setInput("")
    setLoading(true)

    try {
      const response = await apiPost<ChatResponse>("/api/chat", {
        message: userMessage.content,
        history: messages.map((m) => ({
          role: m.role,
          content: m.content,
          agent_type: m.agentType
        }))
      })

      const assistantMessage: Message = {
        role: "assistant",
        content: response.response,
        agentType: response.agent_type,
        timestamp: new Date(),
        metadata: response.metadata
      }

      setMessages((prev) => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage: Message = {
        role: "assistant",
        content: `Ошибка: ${error instanceof Error ? error.message : "Неизвестная ошибка"}`,
        timestamp: new Date()
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const handleShowTasks = () => {
    setInput("Покажи мои задачи")
  }

  const handleSearchKnowledge = () => {
    setInput("Найди информацию о ")
  }

  return (
    <div className="flex h-[calc(100vh-200px)] gap-4">
      {/* Основной чат */}
      <div className="flex-1 flex flex-col border rounded-lg">
        {/* История сообщений */}
        <div className="flex-1 overflow-y-auto p-4 chat-scroll">
          <MessageList messages={messages} />
          {loading && (
            <div className="flex justify-start mb-4">
              <div className="bg-muted rounded-lg px-4 py-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <div className="w-2 h-2 bg-current rounded-full animate-pulse" />
                  <span>Обработка...</span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Поле ввода */}
        <div className="border-t p-4">
          <div className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Напишите сообщение..."
              rows={2}
              className="resize-none rounded-lg"
              disabled={loading}
            />
            <Button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="self-end"
            >
              Отправить
            </Button>
          </div>
        </div>
      </div>

      {/* Боковая панель с быстрыми действиями */}
      <div className="w-64">
        <QuickActions
          onProcessLastMeeting={handleProcessLastMeeting}
          onShowTasks={handleShowTasks}
          onSearchKnowledge={handleSearchKnowledge}
        />
      </div>
    </div>
  )
}
