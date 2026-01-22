import { NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Проксирует GET запрос к FastAPI для проверки здоровья бэкенда
export async function GET(request: NextRequest) {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    })

    if (!response.ok) {
      // Если бэкенд недоступен, возвращаем 503
      if (response.status === 503 || response.status === 0) {
        return NextResponse.json(
          { 
            status: "unhealthy",
            error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000"
          },
          { status: 503 }
        )
      }
      
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || error.error || 'Ошибка при проверке здоровья бэкенда')
    }

    const data = await response.json()
    return NextResponse.json(data, { status: 200 })
  } catch (error) {
    // Проверяем, это ошибка подключения?
    if (error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('ECONNREFUSED'))) {
      return NextResponse.json(
        { 
          status: "unhealthy",
          error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000"
        },
        { status: 503 }
      )
    }

    return NextResponse.json(
      { 
        status: "error",
        error: error instanceof Error ? error.message : "Ошибка при проверке здоровья бэкенда" 
      },
      { status: 500 }
    )
  }
}
