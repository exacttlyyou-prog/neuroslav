import { NextRequest, NextResponse } from "next/server"
import { MeetingProcessingInput, MeetingProcessingResponse } from "@/types/meetings"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Проксирует запросы к FastAPI Backend
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const transcript = formData.get("transcript") as string | null
    const audioFile = formData.get("audio_file") as File | null
    
    if (!transcript && !audioFile) {
      return NextResponse.json(
        { error: "Пожалуйста, введите транскрипт или загрузите аудио файл" },
        { status: 400 }
      )
    }
    
    // Формируем FormData для FastAPI
    const apiFormData = new FormData()
    if (transcript) {
      apiFormData.append("transcript", transcript)
    }
    if (audioFile) {
      apiFormData.append("audio_file", audioFile)
    }
    
    // Проксируем запрос к FastAPI
    const response = await fetch(`${API_BASE_URL}/api/meetings/process`, {
      method: 'POST',
      body: apiFormData
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }))
      const errorMessage = error.error || error.detail || `HTTP ${response.status}: Ошибка при обработке встречи`
      console.error('Ошибка при обработке встречи:', {
        status: response.status,
        statusText: response.statusText,
        error: error
      })
      throw new Error(errorMessage)
    }
    
    const data = await response.json()
    
    // Преобразуем ответ FastAPI в формат Frontend
    const meetingResponse: MeetingProcessingResponse = {
      meeting_id: data.meeting_id,
      summary: data.summary,
      transcript: data.transcript ?? undefined,
      participants: data.participants || [],
      projects: data.projects || [],
      action_items: data.action_items || [],
      key_decisions: data.key_decisions ?? undefined,
      insights: data.insights ?? undefined,
      next_steps: data.next_steps ?? undefined,
      draft_message: data.draft_message,
      verification_warnings: data.verification_warnings || [],
      requires_approval: data.requires_approval || false,
      status: data.status || "pending_approval",
      message: data.message || "Встреча обработана и ожидает согласования",
    }
    
    return NextResponse.json(meetingResponse, { status: 201 })
  } catch (error) {
    console.error('Ошибка в POST /api/meetings:', error)
    
    // Проверяем, это ошибка подключения?
    if (error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('ECONNREFUSED'))) {
      return NextResponse.json(
        { 
          error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000"
        },
        { status: 503 }
      )
    }
    
    const errorMessage = error instanceof Error ? error.message : "Ошибка при обработке встречи"
    console.error('Детали ошибки:', errorMessage)
    
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const status = searchParams.get('status')
    
    const url = status 
      ? `${API_BASE_URL}/api/meetings?status=${status}`
      : `${API_BASE_URL}/api/meetings`
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    })
    
    if (!response.ok) {
      throw new Error('Ошибка при получении встреч')
    }
    
    const meetings = await response.json()
    return NextResponse.json({ meetings }, { status: 200 })
  } catch (error) {
    // Проверяем, это ошибка подключения?
    if (error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('ECONNREFUSED'))) {
      return NextResponse.json(
        { 
          error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000",
          meetings: []
        },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { 
        error: error instanceof Error ? error.message : "Ошибка при получении встреч",
        meetings: []
      },
      { status: 500 }
    )
  }
}
