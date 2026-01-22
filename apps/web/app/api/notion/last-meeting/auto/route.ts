import { NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Проксирует запрос к FastAPI для автоматической обработки последней встречи
export async function POST(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const pageId = searchParams.get('page_id')
    const process = searchParams.get('process') === 'true'

    // Формируем URL для FastAPI
    let url = `${API_BASE_URL}/api/notion/last-meeting/auto?process=${process}`
    if (pageId) {
      url += `&page_id=${pageId}`
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      }
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || error.error || 'Ошибка при автоматической обработке встречи')
    }

    const data = await response.json()
    return NextResponse.json(data, { status: 200 })
  } catch (error) {
    // Проверяем, это ошибка подключения?
    if (error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('ECONNREFUSED'))) {
      return NextResponse.json(
        { 
          error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000"
        },
        { status: 503 }
      )
    }

    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Ошибка при автоматической обработке встречи" },
      { status: 500 }
    )
  }
}
