"use client"

import { useState, useRef, DragEvent } from "react"
import { cn } from "@/lib/utils"

interface FileDropzoneProps {
  onFileSelect: (file: File) => void
  accept?: string
  maxSize?: number
  className?: string
  children?: React.ReactNode
}

export function FileDropzone({
  onFileSelect,
  accept,
  maxSize,
  className,
  children,
}: FileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function validateFile(file: File): boolean {
    if (maxSize && file.size > maxSize) {
      setError(`Файл слишком большой. Максимум: ${maxSize / 1024 / 1024}MB`)
      return false
    }
    if (accept) {
      const acceptedTypes = accept.split(",").map((t) => t.trim())
      const fileExtension = "." + file.name.split(".").pop()?.toLowerCase()
      const fileType = file.type
      const isAccepted =
        acceptedTypes.some(
          (type) =>
            type === fileType ||
            type === fileExtension ||
            (type.endsWith("/*") && fileType.startsWith(type.slice(0, -1)))
        ) || acceptedTypes.includes(fileType)
      if (!isAccepted) {
        setError(`Неподдерживаемый формат. Разрешены: ${accept}`)
        return false
      }
    }
    setError(null)
    return true
  }

  function handleFile(file: File) {
    if (validateFile(file)) {
      onFileSelect(file)
    }
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    const file = e.dataTransfer.files[0]
    if (file) {
      handleFile(file)
    }
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) {
      handleFile(file)
    }
  }

  return (
    <div
      className={cn(
        "relative border-2 border-dashed rounded-lg p-8 transition-all",
        isDragging
          ? "border-primary bg-primary/5 scale-[1.02]"
          : "border-border hover:border-primary/50",
        className
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => fileInputRef.current?.click()}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleFileInput}
        className="hidden"
      />
      {children || (
        <div className="text-center space-y-2">
          <p className="text-sm text-muted-foreground">
            Перетащи файл сюда или кликни для выбора
          </p>
        </div>
      )}
      {error && (
        <p className="text-sm text-destructive mt-2 text-center">{error}</p>
      )}
    </div>
  )
}
