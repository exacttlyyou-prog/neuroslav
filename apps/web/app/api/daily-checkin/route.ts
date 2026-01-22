import { NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Проксирует запросы к FastAPI Backend для ежедневных опросов
export async function POST(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const action = url.searchParams.get('action')
    
    if (action === 'send') {
      // Отправка еженедельных вопросов
      const response = await fetch(`${API_BASE_URL}/api/daily-checkin/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      })
      
      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Unknown error' }))
        throw new Error(error.error || error.detail || 'Ошибка при отправке вопросов')
      }
      
      const data = await response.json()
      return NextResponse.json(data, { status: 200 })
    }
    
    return NextResponse.json(
      { error: "Неизвестное действие" },
      { status: 400 }
    )
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
      { error: error instanceof Error ? error.message : "Ошибка при обработке запроса" },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url)
    const weekStart = url.searchParams.get('week_start')
    const status = url.searchParams.get('status')
    
    const params = new URLSearchParams()
    if (weekStart) params.append('week_start', weekStart)
    if (status) params.append('status', status)
    
    const queryString = params.toString()
    const endpoint = `${API_BASE_URL}/api/daily-checkin${queryString ? `?${queryString}` : ''}`
    
    const response = await fetch(endpoint, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }))
      throw new Error(error.error || error.detail || 'Ошибка при получении опросов')
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
      { error: error instanceof Error ? error.message : "Ошибка при получении опросов" },
      { status: 500 }
    )
  }
}
