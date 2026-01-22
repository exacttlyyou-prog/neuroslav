import { NextRequest, NextResponse } from "next/server"
import { CreateTaskInput, TaskResponse } from "@/types/tasks"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Проксирует запросы к FastAPI Backend
export async function POST(request: NextRequest) {
  try {
    const body: CreateTaskInput = await request.json()
    
    // Проксируем запрос к FastAPI
    const response = await fetch(`${API_BASE_URL}/api/tasks`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: body.text,
        create_in_notion: body.create_in_notion || false
      })
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }))
      throw new Error(error.error || error.detail || 'Ошибка при создании задачи')
    }
    
    const data = await response.json()
    
    // Преобразуем ответ FastAPI в формат Frontend
    const taskResponse: TaskResponse = {
      task: {
        id: data.task_id,
        text: data.intent || body.text,
        deadline: data.deadline,
        status: 'pending',
        createdAt: new Date().toISOString(),
      },
      message: data.message || "Задача создана",
    }
    
    return NextResponse.json(taskResponse, { status: 201 })
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
      { error: error instanceof Error ? error.message : "Ошибка при создании задачи" },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams
    const status = searchParams.get('status')
    
    const url = status 
      ? `${API_BASE_URL}/api/tasks?status=${status}`
      : `${API_BASE_URL}/api/tasks`
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || errorData.message || 'Ошибка при получении задач')
    }
    
    const tasks = await response.json()
    return NextResponse.json({ tasks }, { status: 200 })
  } catch (error) {
    // Проверяем, это ошибка подключения?
    if (error instanceof TypeError && (error.message.includes('fetch') || error.message.includes('ECONNREFUSED'))) {
      return NextResponse.json(
        { 
          error: "Бэкенд не запущен. Запустите: cd apps/api && uvicorn app.main:app --reload --port 8000",
          tasks: [] // Возвращаем пустой массив, чтобы фронтенд не падал
        },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { 
        error: error instanceof Error ? error.message : "Ошибка при получении задач",
        tasks: []
      },
      { status: 500 }
    )
  }
}
