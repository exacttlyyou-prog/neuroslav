import { NextRequest, NextResponse } from "next/server"
import { KnowledgeIndexResponse, KnowledgeSearchResponse } from "@/types/knowledge"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Проксирует запросы к FastAPI Backend
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const file = formData.get("file") as File | null
    
    if (!file) {
      return NextResponse.json(
        { error: "Файл не предоставлен" },
        { status: 400 }
      )
    }
    
    // Формируем FormData для FastAPI
    const apiFormData = new FormData()
    apiFormData.append("file", file)
    
    // Проксируем запрос к FastAPI
    const response = await fetch(`${API_BASE_URL}/api/knowledge/index`, {
      method: 'POST',
      body: apiFormData
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }))
      throw new Error(error.error || error.detail || 'Ошибка при индексации документа')
    }
    
    const data = await response.json()
    
    // Преобразуем ответ FastAPI в формат Frontend
    const indexResponse: KnowledgeIndexResponse = {
      item: {
        id: data.item_id,
        sourceFile: file.name,
        fileType: file.type,
        indexedAt: new Date().toISOString(),
      },
      chunksCount: data.chunks_count,
      message: data.message || "Документ успешно индексирован",
    }
    
    return NextResponse.json(indexResponse, { status: 201 })
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
      { error: error instanceof Error ? error.message : "Ошибка при индексации документа" },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const query = searchParams.get("q") || ""
  const limit = searchParams.get("limit") || "5"
  
  try {
    if (!query) {
      return NextResponse.json(
        { error: "Параметр запроса 'q' обязателен" },
        { status: 400 }
      )
    }
    
    // Проксируем запрос к FastAPI
    const response = await fetch(`${API_BASE_URL}/api/knowledge/search?q=${encodeURIComponent(query)}&limit=${limit}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    })
    
    if (!response.ok) {
      throw new Error('Ошибка при поиске')
    }
    
    const data = await response.json()
    
    // Преобразуем ответ FastAPI в формат Frontend
    const searchResponse: KnowledgeSearchResponse = {
      results: data.results.map((r: any) => ({
        id: r.metadata?.doc_id || r.metadata?.chunk_id || '',
        content: r.content,
        sourceFile: r.metadata?.source_file || '',
        score: r.score || 0,
        metadata: r.metadata
      })),
      query: data.query,
    }
    
    return NextResponse.json(searchResponse, { status: 200 })
  } catch (error) {
    // Проверяем, это ошибка подключения?
    if (error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('ECONNREFUSED'))) {
      return NextResponse.json(
        { 
          error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000",
          results: [],
          query: query
        },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { 
        error: error instanceof Error ? error.message : "Ошибка при поиске",
        results: [],
        query: query
      },
      { status: 500 }
    )
  }
}
