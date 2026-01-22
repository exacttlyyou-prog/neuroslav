import { NextRequest, NextResponse } from "next/server"
import { extractLastMeetingFromMCP } from "@/lib/notion-mcp-parser"

/**
 * API route для получения данных из Notion через стандартный API.
 * 
 * Примечание: MCP Notion Server управляется через FastAPI backend.
 * Для получения meeting-notes блоков используйте FastAPI endpoint /api/notion/last-meeting/auto.
 * 
 * Этот route использует только стандартный Notion API (fallback).
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { page_id, page_url } = body

    if (!page_id && !page_url) {
      return NextResponse.json(
        { error: "Необходим page_id или page_url" },
        { status: 400 }
      )
    }

    // Извлекаем page_id из URL, если передан URL
    let resolvedPageId = page_id
    if (!resolvedPageId && page_url) {
      const urlMatch = page_url.match(/[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/i)
      if (urlMatch) {
        resolvedPageId = urlMatch[0]
      }
    }

    if (!resolvedPageId) {
      return NextResponse.json(
        { error: "Не удалось извлечь page_id из URL" },
        { status: 400 }
      )
    }

    // Примечание: MCP Notion Server управляется через FastAPI backend.
    // Все запросы к MCP должны идти через FastAPI endpoint /api/notion/last-meeting/auto.
    // Здесь используется только fallback на стандартный Notion API.
    
    // Fallback на стандартный Notion API
    const notionToken = process.env.NOTION_TOKEN
    if (!notionToken) {
      return NextResponse.json(
        { 
          error: "NOTION_TOKEN не установлен",
          suggestion: "Установите NOTION_TOKEN в переменных окружения. Для получения meeting-notes блоков используйте Python backend, который запускает локальный MCP сервер."
        },
        { status: 500 }
      )
    }

    // Пробуем получить через стандартный Notion API
    try {
      const notionApiUrl = `https://api.notion.com/v1/pages/${resolvedPageId.replace(/-/g, '')}`
      const response = await fetch(notionApiUrl, {
        headers: {
          'Authorization': `Bearer ${notionToken}`,
          'Notion-Version': '2025-09-03',
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.message || `Notion API error: ${response.status}`)
      }

      const pageData = await response.json()
      
      // Получаем блоки страницы
      const blocksUrl = `https://api.notion.com/v1/blocks/${resolvedPageId.replace(/-/g, '')}/children`
      const blocksResponse = await fetch(blocksUrl, {
        headers: {
          'Authorization': `Bearer ${notionToken}`,
          'Notion-Version': '2025-09-03',
          'Content-Type': 'application/json'
        }
      })

      if (!blocksResponse.ok) {
        throw new Error(`Не удалось получить блоки страницы: ${blocksResponse.status}`)
      }

      const blocksData = await blocksResponse.json()
      
      // Извлекаем текст из блоков
      let content = ''
      for (const block of blocksData.results || []) {
        const blockType = block.type
        if (block[blockType]?.rich_text) {
          for (const text of block[blockType].rich_text) {
            content += text.plain_text + '\n'
          }
        }
      }

      if (content.length < 100) {
        // Пробуем получить больше блоков рекурсивно
        try {
          const allBlocks: any[] = []
          let hasMore = true
          let cursor = null
          
          while (hasMore && allBlocks.length < 500) {
            const blocksResponse = await fetch(
              `${blocksUrl}${cursor ? `?start_cursor=${cursor}` : ''}`,
              {
                headers: {
                  'Authorization': `Bearer ${notionToken}`,
                  'Notion-Version': '2025-09-03',
                  'Content-Type': 'application/json'
                }
              }
            )
            
            if (!blocksResponse.ok) break
            
            const blocksData = await blocksResponse.json()
            allBlocks.push(...(blocksData.results || []))
            hasMore = blocksData.has_more || false
            cursor = blocksData.next_cursor
          }
          
          // Извлекаем текст из всех блоков
          content = ''
          for (const block of allBlocks) {
            const blockType = block.type
            if (block[blockType]?.rich_text) {
              for (const text of block[blockType].rich_text) {
                content += text.plain_text + '\n'
              }
            }
          }
        } catch (e) {
          // Игнорируем ошибки рекурсивного получения
        }
        
        if (content.length < 100) {
          return NextResponse.json(
            { 
              error: "Получен слишком короткий контент через стандартный Notion API",
              details: "Meeting-notes блоки недоступны через стандартный Notion API. Они требуют MCP Notion.",
              suggestion: "Используйте Python backend endpoint /api/notion/last-meeting/auto, который может использовать MCP через доступные механизмы Cursor, или вручную скопируйте контент из Notion"
            },
            { status: 400 }
          )
        }
      }

      // Парсим контент для извлечения последней встречи
      const meetingBlock = extractLastMeetingFromMCP(content, resolvedPageId)

      return NextResponse.json({
        page_id: resolvedPageId,
        block_id: meetingBlock.block_id,
        block_type: meetingBlock.block_type,
        content: meetingBlock.content,
        title: meetingBlock.title,
        has_transcription: meetingBlock.has_transcription,
        has_summary: meetingBlock.has_summary,
        method: 'notion_api_fallback'
      })

    } catch (apiError) {
      // Если стандартный API не работает, возвращаем понятную ошибку
      const errorMessage = apiError instanceof Error ? apiError.message : String(apiError)
      
      // Проверяем тип ошибки
      if (errorMessage.includes('unauthorized') || errorMessage.includes('401')) {
        return NextResponse.json(
          { 
            error: "Ошибка авторизации Notion API",
            details: "Проверьте правильность NOTION_TOKEN",
            suggestion: "Убедитесь, что NOTION_TOKEN установлен и имеет доступ к странице"
          },
          { status: 401 }
        )
      }
      
      if (errorMessage.includes('not found') || errorMessage.includes('404')) {
        return NextResponse.json(
          { 
            error: "Страница не найдена",
            details: `Страница с ID ${resolvedPageId} не найдена или недоступна`,
            suggestion: "Проверьте правильность page_id и доступ к странице"
          },
          { status: 404 }
        )
      }
      
      return NextResponse.json(
        { 
          error: "Не удалось получить данные через стандартный Notion API",
          details: errorMessage,
          suggestion: "Для получения meeting-notes блоков используйте Python backend endpoint /api/notion/last-meeting/auto, который может использовать MCP Notion через доступные механизмы Cursor"
        },
        { status: 500 }
      )
    }

  } catch (error) {
    console.error("Ошибка при получении данных из Notion через MCP:", error)
    return NextResponse.json(
      { 
        error: "Ошибка при получении данных из Notion",
        details: error instanceof Error ? error.message : String(error)
      },
      { status: 500 }
    )
  }
}
