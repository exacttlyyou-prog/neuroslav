"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChatInterface } from "@/components/chat/ChatInterface"
import { Button } from "@/components/ui/button"
import { MeetingHistory } from "@/components/meetings/MeetingHistory"
import { TaskList } from "@/components/tasks/TaskList"
import { useState, useEffect } from "react"
import { Mic, MicOff, Loader2 } from "lucide-react"

export default function Home() {
  // #region agent log
  useEffect(() => {
    const bodyStyles = window.getComputedStyle(document.body);
    fetch('http://127.0.0.1:7242/ingest/3fac9a8f-3caa-4120-a5d6-1456b6683183', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        location: 'page.tsx',
        message: 'Home Page Styles Check',
        data: { 
          backgroundColor: bodyStyles.backgroundColor,
          fontFamily: bodyStyles.fontFamily,
          display: bodyStyles.display
        },
        timestamp: Date.now(),
        sessionId: 'debug-session',
        hypothesisId: 'H3'
      })
    }).catch(() => {});
  }, []);
  // #endregion

  const [isRecording, setIsRecording] = useState(false)
  const [recordingStatus, setRecordingStatus] = useState<"idle" | "starting" | "recording" | "stopping">("idle")

  const checkRecordingStatus = async () => {
    try {
      const response = await fetch("/api/meetings/status")
      if (response.ok) {
        const data = await response.json()
        setIsRecording(data.is_recording || false)
        setRecordingStatus(data.is_recording ? "recording" : "idle")
      }
    } catch (error) {
      console.error("Ошибка проверки статуса записи:", error)
    }
  }

  useEffect(() => {
    checkRecordingStatus()
    const interval = setInterval(checkRecordingStatus, 3000) // Проверяем каждые 3 секунды
    return () => clearInterval(interval)
  }, [])

  const handleStartRecording = async () => {
    setRecordingStatus("starting")
    try {
      const response = await fetch("/api/meetings/start", {
        method: "POST",
      })
      if (response.ok) {
        setIsRecording(true)
        setRecordingStatus("recording")
      } else {
        setRecordingStatus("idle")
        alert("Ошибка запуска записи")
      }
    } catch (error) {
      console.error("Ошибка запуска записи:", error)
      setRecordingStatus("idle")
      alert("Ошибка запуска записи")
    }
  }

  const handleStopRecording = async () => {
    setRecordingStatus("stopping")
    try {
      const response = await fetch("/api/meetings/stop", {
        method: "POST",
      })
      if (response.ok) {
        setIsRecording(false)
        setRecordingStatus("idle")
      } else {
        alert("Ошибка остановки записи")
      }
    } catch (error) {
      console.error("Ошибка остановки записи:", error)
      alert("Ошибка остановки записи")
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto py-8 px-6 max-w-7xl">
        {/* Заголовок и кнопка записи */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold tracking-tight mb-2 bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
              Нейрослав
            </h1>
            <p className="text-muted-foreground text-base font-light">Персональный движок обработки</p>
          </div>
          <Button
            onClick={isRecording ? handleStopRecording : handleStartRecording}
            disabled={recordingStatus === "starting" || recordingStatus === "stopping"}
            variant={isRecording ? "destructive" : "default"}
            size="lg"
            className="gap-2"
          >
            {recordingStatus === "starting" || recordingStatus === "stopping" ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {recordingStatus === "starting" ? "Запуск..." : "Остановка..."}
              </>
            ) : isRecording ? (
              <>
                <MicOff className="h-4 w-4" />
                Остановить запись
              </>
            ) : (
              <>
                <Mic className="h-4 w-4" />
                Слушать встречу
              </>
            )}
          </Button>
        </div>

        {/* Индикатор записи */}
        {isRecording && (
          <div className="mb-6 p-4 glass-strong border-destructive/30 flex items-center gap-3 rounded-2xl">
            <div className="h-2.5 w-2.5 bg-destructive rounded-full animate-pulse shadow-lg shadow-destructive/50" />
            <span className="text-sm text-destructive font-medium">Идет запись встречи...</span>
          </div>
        )}

        {/* Чат */}
        <Card className="mb-8">
          <CardHeader className="pb-4">
            <CardTitle className="text-xl font-semibold">Чат с Нейрославом</CardTitle>
            <CardDescription className="text-sm font-light">
              Просто напишите — система сама определит, что нужно сделать
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ChatInterface />
          </CardContent>
        </Card>

        {/* Секции: Встречи, Пинги, Задачи */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Встречи */}
          <Card>
            <CardHeader>
              <CardTitle>Встречи</CardTitle>
              <CardDescription>Последние записанные встречи</CardDescription>
            </CardHeader>
            <CardContent>
              <MeetingHistory />
            </CardContent>
          </Card>

          {/* Пинги */}
          <Card>
            <CardHeader>
              <CardTitle>Пинги</CardTitle>
              <CardDescription>Уведомления и сообщения</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground">
                Функция в разработке
              </div>
            </CardContent>
          </Card>

          {/* Задачи */}
          <Card>
            <CardHeader>
              <CardTitle>Задачи</CardTitle>
              <CardDescription>Активные задачи</CardDescription>
            </CardHeader>
            <CardContent>
              <TaskList />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
