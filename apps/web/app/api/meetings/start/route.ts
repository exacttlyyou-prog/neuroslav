import { NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/meetings/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      }
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      return NextResponse.json(
        { error: error.detail || error.message || 'Ошибка при запуске записи' },
        { status: response.status }
      )
    }
    
    const data = await response.json()
    return NextResponse.json(data, { status: 200 })
  } catch (error) {
    if (error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('ECONNREFUSED'))) {
      return NextResponse.json(
        { 
          error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000"
        },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Ошибка при запуске записи" },
      { status: 500 }
    )
  }
}
