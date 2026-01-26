"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Mic, MicOff, Loader2, CheckCircle2, Clock, AlertCircle } from "lucide-react"
import { apiGet } from "@/lib/api"
import { Task } from "@/types/tasks"

type TaskWithStatus = Task & {
  intent?: string
  priority?: "High" | "Medium" | "Low"
}
import { Meeting } from "@/types/meetings"
import Link from "next/link"

interface RecordingStatus {
  is_recording: boolean
  pid?: number
}

export default function DashboardPage() {
  const [isRecording, setIsRecording] = useState(false)
  const [recordingStatus, setRecordingStatus] = useState<"idle" | "starting" | "recording" | "stopping">("idle")
  const [tasks, setTasks] = useState<TaskWithStatus[]>([])
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [loading, setLoading] = useState(true)

  // Проверка статуса записи
  const checkRecordingStatus = async () => {
    try {
      const response = await apiGet<RecordingStatus>("/api/meetings/status")
      setIsRecording(response.is_recording || false)
      setRecordingStatus(response.is_recording ? "recording" : "idle")
    } catch (error) {
      console.error("Ошибка проверки статуса записи:", error)
    }
  }

  // Загрузка задач
  const loadTasks = async () => {
    try {
      const response = await apiGet<{ tasks: TaskWithStatus[] }>("/api/tasks")
      const activeTasks = (response.tasks || []).filter(t => t.status === "pending").slice(0, 5)
      setTasks(activeTasks)
    } catch (error) {
      console.error("Ошибка загрузки задач:", error)
      setTasks([])
    }
  }

  // Загрузка встреч
  const loadMeetings = async () => {
    try {
      const response = await apiGet<{ meetings: Meeting[] }>("/api/meetings")
      const recentMeetings = (response.meetings || []).slice(0, 5)
      setMeetings(recentMeetings)
    } catch (error) {
      console.error("Ошибка загрузки встреч:", error)
      setMeetings([])
    }
  }

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await Promise.all([
        checkRecordingStatus(),
        loadTasks(),
        loadMeetings()
      ])
      setLoading(false)
    }
    loadData()
    
    // Обновляем статус записи каждые 3 секунды
    const interval = setInterval(checkRecordingStatus, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleStartRecording = async () => {
    setRecordingStatus("starting")
    try {
      const response = await fetch("/api/meetings/start", { method: "POST" })
      if (response.ok) {
        await checkRecordingStatus()
      } else {
        setRecordingStatus("idle")
      }
    } catch (error) {
      console.error("Ошибка запуска записи:", error)
      setRecordingStatus("idle")
    }
  }

  const handleStopRecording = async () => {
    setRecordingStatus("stopping")
    try {
      const response = await fetch("/api/meetings/stop", { method: "POST" })
      if (response.ok) {
        await checkRecordingStatus()
      } else {
        setRecordingStatus("recording")
      }
    } catch (error) {
      console.error("Ошибка остановки записи:", error)
      setRecordingStatus("recording")
    }
  }

  const formatDate = (dateInput: string | Date | null | undefined) => {
    if (!dateInput) return "—"
    const date = dateInput instanceof Date ? dateInput : new Date(dateInput)
    if (isNaN(date.getTime())) return "—"
    return date.toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit"
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
        {/* Виджет: Текущий статус записи */}
        <Card className="shadow-md border-2 animate-in fade-in slide-in-from-top duration-300">
          <CardHeader className="bg-gradient-to-r from-red-50 to-orange-50 dark:from-red-950/20 dark:to-orange-950/20">
            <CardTitle className="text-lg font-bold flex items-center gap-2">
              {isRecording ? (
                <>
                  <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                  Запись идет
                </>
              ) : (
                <>
                  <MicOff className="w-5 h-5" />
                  Ожидание
                </>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="space-y-4">
              <div className="text-sm text-muted-foreground">
                {isRecording ? "Встреча записывается" : "Готов к записи"}
              </div>
              <Button
                onClick={isRecording ? handleStopRecording : handleStartRecording}
                disabled={recordingStatus === "starting" || recordingStatus === "stopping"}
                variant={isRecording ? "destructive" : "default"}
                className="w-full"
              >
                {recordingStatus === "starting" || recordingStatus === "stopping" ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {recordingStatus === "starting" ? "Запуск..." : "Остановка..."}
                  </>
                ) : isRecording ? (
                  <>
                    <MicOff className="w-4 h-4 mr-2" />
                    Остановить запись
                  </>
                ) : (
                  <>
                    <Mic className="w-4 h-4 mr-2" />
                    Начать запись
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Виджет: Активные задачи */}
        <Card className="shadow-md border-2 md:col-span-2 lg:col-span-1 animate-in fade-in slide-in-from-left duration-300 delay-75">
          <CardHeader className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/20 dark:to-indigo-950/20">
            <CardTitle className="text-lg font-bold flex items-center justify-between">
              <span>Активные задачи</span>
              <Link href="/tasks">
                <Button variant="ghost" size="sm">Все</Button>
              </Link>
            </CardTitle>
            <CardDescription>
              {tasks.length} из {tasks.length} задач
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="space-y-3">
              {tasks.length === 0 ? (
                <div className="text-sm text-muted-foreground text-center py-4">
                  Нет активных задач
                </div>
              ) : (
                tasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-start gap-3 p-3 border rounded-lg hover:border-primary/50 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{task.text || task.intent}</div>
                      {task.deadline && (
                        <div className="text-xs text-muted-foreground mt-1">
                          {formatDate(task.deadline)}
                        </div>
                      )}
                    </div>
                    {task.priority && (
                      <Badge
                        variant={
                          task.priority === "High" ? "destructive" :
                          task.priority === "Medium" ? "default" : "secondary"
                        }
                        className="text-xs"
                      >
                        {task.priority}
                      </Badge>
                    )}
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        {/* Виджет: Последние встречи */}
        <Card className="shadow-md border-2 md:col-span-2 animate-in fade-in slide-in-from-right duration-300 delay-150">
          <CardHeader className="bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-950/20 dark:to-pink-950/20">
            <CardTitle className="text-lg font-bold flex items-center justify-between">
              <span>Последние встречи</span>
              <Link href="/meetings">
                <Button variant="ghost" size="sm">Все</Button>
              </Link>
            </CardTitle>
            <CardDescription>
              {meetings.length} последних встреч
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="space-y-3">
              {meetings.length === 0 ? (
                <div className="text-sm text-muted-foreground text-center py-4">
                  Нет встреч
                </div>
              ) : (
                meetings.map((meeting) => (
                  <Link
                    key={meeting.id}
                    href={`/meetings/${meeting.id}`}
                    className="block p-3 border rounded-lg hover:border-primary/50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">
                          {meeting.summary ? meeting.summary.substring(0, 60) + "..." : "Встреча без саммари"}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          {formatDate(meeting.createdAt)}
                        </div>
                      </div>
                      <Badge
                        variant={
                          meeting.status === "sent" ? "default" :
                          meeting.status === "pending_approval" ? "secondary" :
                          meeting.status === "processing" ? "outline" : "destructive"
                        }
                        className="text-xs"
                      >
                        {meeting.status === "sent" ? "Отправлено" :
                         meeting.status === "pending_approval" ? "Ожидает" :
                         meeting.status === "processing" ? "Обработка" : 
                         meeting.status === "completed" ? "Готово" : meeting.status}
                      </Badge>
                    </div>
                  </Link>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
