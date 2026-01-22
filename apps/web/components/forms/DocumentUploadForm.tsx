"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { FileDropzone } from "@/components/ui/file-dropzone"
import { MAX_FILE_SIZE, FILE_TYPES } from "@/lib/constants"

export function DocumentUploadForm() {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setIsSubmitting(true)
    setSubmitMessage(null)

    if (!file) {
      setSubmitMessage("Пожалуйста, выберите файл")
      setIsSubmitting(false)
      return
    }

    if (file.size > MAX_FILE_SIZE) {
      setSubmitMessage(`Файл слишком большой. Максимальный размер: ${MAX_FILE_SIZE / 1024 / 1024}MB`)
      setIsSubmitting(false)
      return
    }

    try {
      const formData = new FormData()
      formData.append("file", file)

      const response = await fetch("/api/knowledge", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        throw new Error("Ошибка при индексации документа")
      }

      const data = await response.json()
      setSubmitMessage(data.message)
      setFile(null)
    } catch (error) {
      setSubmitMessage(error instanceof Error ? error.message : "Ошибка при индексации документа")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label>Документ</Label>
        <FileDropzone
          onFileSelect={setFile}
          accept=".pdf,.docx,.pptx"
          maxSize={MAX_FILE_SIZE}
        >
          <div className="text-center space-y-2">
            {file ? (
              <div className="space-y-1">
                <p className="text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  Перетащи файл сюда или кликни для выбора
                </p>
                <p className="text-xs text-muted-foreground">
                  PDF, DOCX, PPTX (до {MAX_FILE_SIZE / 1024 / 1024}MB)
                </p>
              </>
            )}
          </div>
        </FileDropzone>
      </div>

      <Button type="submit" disabled={isSubmitting || !file}>
        {isSubmitting ? "Сохраняю..." : "Сохранить"}
      </Button>

      {submitMessage && (
        <p className={`text-sm ${submitMessage.includes("Ошибка") ? "text-destructive" : "text-muted-foreground"}`}>
          {submitMessage}
        </p>
      )}
    </form>
  )
}
