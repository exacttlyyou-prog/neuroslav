"use client"

import { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { apiGet } from "@/lib/api"

interface Meeting {
  id: string
  summary: string | null
  participants: any[] | null
  status: string
  created_at: string | null
}

export function MeetingHistory() {
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")

  useEffect(() => {
    loadMeetings()
  }, [])

  async function loadMeetings() {
    try {
      setLoading(true)
      const response = await apiGet<{ meetings: Meeting[] }>("/api/meetings")
      // Принудительная сортировка на фронтенде: новые сверху
      const sortedMeetings = (response.meetings || []).sort((a, b) => {
        const dateA = a.created_at ? new Date(a.created_at).getTime() : 0
        const dateB = b.created_at ? new Date(b.created_at).getTime() : 0
        return dateB - dateA
      })
      setMeetings(sortedMeetings)
    } catch (error) {
      console.error("Ошибка при загрузке встреч:", error)
    } finally {
      setLoading(false)
    }
  }

  function formatDate(dateString: string | null) {
    if (!dateString) return "—"
    const date = new Date(dateString)
    return date.toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  function stripHtml(html: string | null) {
    if (!html) return ""
    return html.replace(/<[^>]*>?/gm, "")
  }

  function getStatusBadge(status: string) {
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      pending_approval: "secondary",
      sent: "default",
      processing: "outline",
      completed: "default",
      error: "destructive",
    }
    const labels: Record<string, string> = {
      pending_approval: "Ожидает",
      sent: "Отправлено",
      processing: "Обработка",
      completed: "Готово",
      error: "Ошибка",
    }
    return (
      <Badge 
        variant={variants[status] || "secondary"} 
        className="shrink-0 bg-background/40 border-border/50 backdrop-blur-sm"
      >
        {labels[status] || status}
      </Badge>
    )
  }

  const filteredMeetings = meetings.filter((meeting) => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      meeting.summary?.toLowerCase().includes(query) ||
      meeting.participants?.some((p) =>
        (typeof p === "string" ? p : p.name)?.toLowerCase().includes(query)
      )
    )
  })

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 bg-muted rounded-lg animate-pulse" />
        ))}
      </div>
    )
  }

  if (meetings.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>Нет обработанных встреч</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <Input
          placeholder="Поиск по встрече..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="rounded-xl glass border-border/50 bg-background/30 backdrop-blur-sm"
        />
      </div>

      <div className="space-y-3">
        {filteredMeetings.map((meeting) => (
          <Card key={meeting.id} className="glass-strong">
            <CardContent className="p-5">
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {meeting.summary && (
                      <p className="text-sm leading-relaxed mb-3 line-clamp-3 text-foreground/90">
                        {stripHtml(meeting.summary)}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span className="font-medium">{formatDate(meeting.created_at)}</span>
                      {meeting.participants && meeting.participants.length > 0 && (
                        <>
                          <span className="opacity-50">•</span>
                          <span className="opacity-80">
                            {meeting.participants.length}{" "}
                            {meeting.participants.length === 1
                              ? "участник"
                              : "участников"}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  {getStatusBadge(meeting.status)}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {filteredMeetings.length === 0 && searchQuery && (
        <div className="text-center py-8 text-muted-foreground">
          <p>Ничего не найдено</p>
        </div>
      )}
    </div>
  )
}
