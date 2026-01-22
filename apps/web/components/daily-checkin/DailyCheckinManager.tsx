"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { apiPost, apiRequest } from "@/lib/api"

interface DailyCheckin {
  id: string
  contact_id: string
  checkin_date: string | null
  question_sent_at: string | null
  response_received_at: string | null
  response_text: string | null
  clarification_asked: number
  status: string
  created_at: string | null
}

export function DailyCheckinManager() {
  const [checkins, setCheckins] = useState<DailyCheckin[]>([])
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)

  const loadCheckins = async () => {
    setLoading(true)
    try {
      const data = await apiRequest<DailyCheckin[]>("/api/daily-checkin")
      setCheckins(data)
    } catch (error) {
      console.error("Ошибка при загрузке опросов:", error)
    } finally {
      setLoading(false)
    }
  }

  const sendDailyQuestions = async () => {
    setSending(true)
    try {
      const result = await apiPost<{ sent: number; failed: number }>(
        "/api/daily-checkin?action=send",
        {}
      )
      alert(`Отправлено: ${result.sent}, Ошибок: ${result.failed}`)
      await loadCheckins()
    } catch (error) {
      alert(`Ошибка: ${error instanceof Error ? error.message : "Неизвестная ошибка"}`)
    } finally {
      setSending(false)
    }
  }

  useEffect(() => {
    loadCheckins()
  }, [])

  const getStatusBadge = (status: string) => {
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      pending: "outline",
      sent: "secondary",
      responded: "default",
      completed: "default"
    }
    const labels: Record<string, string> = {
      pending: "Ожидает",
      sent: "Отправлен",
      responded: "Получен ответ",
      completed: "Завершен"
    }
    return (
      <Badge variant={variants[status] || "default"}>
        {labels[status] || status}
      </Badge>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Ежедневные опросы</CardTitle>
          <CardDescription>
            Отправка вопросов команде и просмотр ответов
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button 
            onClick={sendDailyQuestions} 
            disabled={sending}
            className="w-full"
          >
            {sending ? "Отправка..." : "Отправить вопросы на сегодня"}
          </Button>
          
          <Button 
            onClick={loadCheckins} 
            disabled={loading}
            variant="outline"
            className="w-full"
          >
            {loading ? "Загрузка..." : "Обновить список"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>История опросов</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-muted-foreground">
              Загрузка...
            </div>
          ) : checkins.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              Нет опросов
            </div>
          ) : (
            <div className="space-y-4">
              {checkins.map((checkin) => (
                <Card key={checkin.id}>
                  <CardContent className="pt-6">
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <p className="font-medium">Контакт ID: {checkin.contact_id}</p>
                        {checkin.checkin_date && (
                          <p className="text-sm text-muted-foreground">
                            Дата: {new Date(checkin.checkin_date).toLocaleDateString('ru-RU')}
                          </p>
                        )}
                      </div>
                      {getStatusBadge(checkin.status)}
                    </div>
                    
                    {checkin.question_sent_at && (
                      <p className="text-sm text-muted-foreground mb-2">
                        Вопрос отправлен: {new Date(checkin.question_sent_at).toLocaleString('ru-RU')}
                      </p>
                    )}
                    
                    {checkin.response_received_at && (
                      <p className="text-sm text-muted-foreground mb-2">
                        Ответ получен: {new Date(checkin.response_received_at).toLocaleString('ru-RU')}
                      </p>
                    )}
                    
                    {checkin.response_text && (
                      <div className="mt-4 p-4 bg-muted rounded-lg">
                        <p className="text-sm font-medium mb-2">Ответ:</p>
                        <p className="text-sm whitespace-pre-wrap">{checkin.response_text}</p>
                      </div>
                    )}
                    
                    {checkin.clarification_asked > 0 && (
                      <Badge variant="outline" className="mt-2">
                        Уточнений: {checkin.clarification_asked}
                      </Badge>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
