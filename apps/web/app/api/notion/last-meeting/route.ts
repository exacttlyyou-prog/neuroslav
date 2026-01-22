import { NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Проксирует GET запрос к FastAPI для получения последней встречи
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const pageId = searchParams.get('page_id')
    const pageUrl = searchParams.get('page_url')

    if (!pageId && !pageUrl) {
      return NextResponse.json(
        { error: "Необходим page_id или page_url" },
        { status: 400 }
      )
    }

    // Формируем URL для FastAPI
    let url = `${API_BASE_URL}/api/notion/last-meeting?`
    if (pageId) {
      url += `page_id=${encodeURIComponent(pageId)}`
    }
    if (pageUrl) {
      if (pageId) url += '&'
      url += `page_url=${encodeURIComponent(pageUrl)}`
    }

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || error.error || 'Ошибка при получении последней встречи')
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
      { error: error instanceof Error ? error.message : "Ошибка при получении последней встречи" },
      { status: 500 }
    )
  }
}
