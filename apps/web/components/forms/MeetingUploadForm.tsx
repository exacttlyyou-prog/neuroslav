"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { FileDropzone } from "@/components/ui/file-dropzone"
import { apiGet, apiPostFormData } from "@/lib/api"
import { MeetingProcessingResponse } from "@/types/meetings"
import { MeetingResults } from "@/components/meetings/MeetingResults"

export function MeetingUploadForm() {
  const lastMeetingUrl = "https://www.notion.so/2026-2edfa7fd637180b98715fa9f348f90f9#2eefa7fd63718048a829e4891f509363"
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)
  const [transcript, setTranscript] = useState("")
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [result, setResult] = useState<MeetingProcessingResponse | null>(null)
  const [isFetchingLastMeeting, setIsFetchingLastMeeting] = useState(false)
  const [lastMeetingMessage, setLastMeetingMessage] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setIsSubmitting(true)
    setSubmitMessage(null)

    try {
      const formData = new FormData()
      if (transcript) {
        formData.append("transcript", transcript)
      }
      if (audioFile) {
        formData.append("audio_file", audioFile)
      }

      if (!transcript && !audioFile) {
        setSubmitMessage("Пожалуйста, введите транскрипт или загрузите аудио файл")
        setIsSubmitting(false)
        return
      }

      const data: MeetingProcessingResponse = await apiPostFormData<MeetingProcessingResponse>(
        "/api/meetings",
        formData
      )
      
      setResult(data)
      setSubmitMessage(data.message)
      setTranscript("")
      setAudioFile(null)
    } catch (error) {
      setSubmitMessage(error instanceof Error ? error.message : "Ошибка при обработке встречи")
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleLastMeeting() {
    setIsFetchingLastMeeting(true)
    setLastMeetingMessage(null)
    try {
      const data = await apiGet<{ content: string }>(
        `/api/notion/last-meeting?page_url=${encodeURIComponent(lastMeetingUrl)}`
      )
      if (!data.content) {
        setLastMeetingMessage("Последняя встреча не найдена")
        return
      }
      if (!navigator.clipboard) {
        setLastMeetingMessage("Буфер обмена недоступен в этом браузере")
        return
      }
      await navigator.clipboard.writeText(data.content)
      setLastMeetingMessage("Последняя встреча скопирована")
    } catch (error) {
      setLastMeetingMessage(error instanceof Error ? error.message : "Ошибка при получении последней встречи")
    } finally {
      setIsFetchingLastMeeting(false)
    }
  }

  return (
    <>
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="transcript">Транскрипт</Label>
        <Textarea
          id="transcript"
          placeholder="Вставь текст встречи..."
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={6}
          className="rounded-lg"
        />
      </div>
      
      <div className="space-y-2">
        <Label>Или загрузи аудио</Label>
        <FileDropzone
          onFileSelect={setAudioFile}
          accept="audio/*"
        >
          <div className="text-center space-y-2">
            {audioFile ? (
              <div className="space-y-1">
                <p className="text-sm font-medium">{audioFile.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(audioFile.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Перетащи аудио сюда или кликни для выбора
              </p>
            )}
          </div>
        </FileDropzone>
      </div>

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Разбираю..." : "Разобрать"}
      </Button>

      <Button type="button" variant="secondary" onClick={handleLastMeeting} disabled={isFetchingLastMeeting}>
        {isFetchingLastMeeting ? "Копирую..." : "Последняя встреча"}
      </Button>

      {submitMessage && !result && (
        <p className={`text-sm ${submitMessage.includes("Ошибка") ? "text-destructive" : "text-muted-foreground"}`}>
          {submitMessage}
        </p>
      )}

      {lastMeetingMessage && (
        <p className={`text-sm ${lastMeetingMessage.includes("Ошибка") ? "text-destructive" : "text-muted-foreground"}`}>
          {lastMeetingMessage}
        </p>
      )}
    </form>
    
    {result && (
      <div className="mt-6">
        <MeetingResults 
          result={result}
          onSend={async () => {
            // TODO: реализовать отправку через API
            console.log("Отправка draft:", result.meeting.draftMessage)
          }}
        />
      </div>
    )}
  </>
  )
}
