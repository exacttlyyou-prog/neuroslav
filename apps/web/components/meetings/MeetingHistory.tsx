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
      setMeetings(response.meetings || [])
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
          className="rounded-lg"
        />
      </div>

      <div className="space-y-3">
        {filteredMeetings.map((meeting) => (
          <Card key={meeting.id} className="hover-lift">
            <CardContent className="p-4">
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    {meeting.summary && (
                      <p className="text-sm line-clamp-2 mb-2">
                        {meeting.summary}
                      </p>
                    )}
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{formatDate(meeting.created_at)}</span>
                      {meeting.participants && meeting.participants.length > 0 && (
                        <>
                          <span>•</span>
                          <span>
                            {meeting.participants.length}{" "}
                            {meeting.participants.length === 1
                              ? "участник"
                              : "участников"}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <Badge variant="secondary" className="shrink-0">
                    {meeting.status === "completed" ? "Готово" : meeting.status}
                  </Badge>
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
