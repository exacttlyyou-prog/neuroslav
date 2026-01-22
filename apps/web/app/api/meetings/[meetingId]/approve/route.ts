import { NextRequest, NextResponse } from "next/server"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function POST(
  request: NextRequest,
  { params }: { params: { meetingId: string } }
) {
  try {
    const meetingId = params.meetingId
    const body = await request.json()
    
    const { summary, participants, action_items } = body
    
    // Формируем FormData для FastAPI
    const formData = new FormData()
    if (summary) {
      formData.append("summary", summary)
    }
    if (participants) {
      formData.append("participants", JSON.stringify(participants))
    }
    if (action_items) {
      formData.append("action_items", JSON.stringify(action_items))
    }
    
    // Проксируем запрос к FastAPI
    const response = await fetch(`${API_BASE_URL}/api/meetings/${meetingId}/approve-and-send`, {
      method: 'POST',
      body: formData
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }))
      throw new Error(error.error || error.detail || 'Ошибка при отправке встречи')
    }
    
    const data = await response.json()
    
    return NextResponse.json(data, { status: 200 })
  } catch (error) {
    console.error("Ошибка при отправке встречи после согласования:", error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Неизвестная ошибка" },
      { status: 500 }
    )
  }
}
