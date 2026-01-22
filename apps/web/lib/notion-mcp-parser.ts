/**
 * Парсер для извлечения последней встречи из данных MCP Notion.
 */

export interface MeetingBlock {
  block_id: string
  block_type: 'transcription' | 'summary' | 'meeting-notes' | 'copied_text'
  content: string
  title: string
  has_transcription: boolean
  has_summary: boolean
}

/**
 * Извлекает последнюю встречу из ответа MCP Notion.
 * 
 * MCP Notion возвращает данные в формате Markdown с тегами <meeting-notes>,
 * <transcript>, <summary> и т.д.
 */
export function extractLastMeetingFromMCP(mcpContent: string, pageId?: string): MeetingBlock {
  if (!mcpContent || mcpContent.length < 100) {
    throw new Error('Получен слишком короткий контент от MCP Notion')
  }

  // Ищем meeting-notes блоки
  const meetingNotesRegex = /<meeting-notes[^>]*>([\s\S]*?)<\/meeting-notes>/gi
  const meetingNotesMatches = Array.from(mcpContent.matchAll(meetingNotesRegex))

  if (meetingNotesMatches.length > 0) {
    // Берем последний meeting-notes блок
    const lastMeeting = meetingNotesMatches[meetingNotesMatches.length - 1]
    const meetingContent = lastMeeting[1]

    // Ищем transcript внутри meeting-notes
    const transcriptMatch = meetingContent.match(/<transcript[^>]*>([\s\S]*?)<\/transcript>/i)
    const summaryMatch = meetingContent.match(/<summary[^>]*>([\s\S]*?)<\/summary>/i)

    if (transcriptMatch) {
      return {
        block_id: '',
        block_type: 'transcription',
        content: transcriptMatch[1].trim(),
        title: 'Последняя транскрипция',
        has_transcription: true,
        has_summary: false
      }
    }

    if (summaryMatch) {
      return {
        block_id: '',
        block_type: 'summary',
        content: summaryMatch[1].trim(),
        title: 'Последнее саммари',
        has_transcription: false,
        has_summary: true
      }
    }

    // Если нет transcript/summary, берем весь контент meeting-notes
    return {
      block_id: '',
      block_type: 'meeting-notes',
      content: meetingContent.trim(),
      title: 'Последняя встреча',
      has_transcription: !!transcriptMatch,
      has_summary: !!summaryMatch
    }
  }

  // Fallback: ищем transcript или summary напрямую в контенте
  const transcriptRegex = /<transcript[^>]*>([\s\S]*?)<\/transcript>/gi
  const summaryRegex = /<summary[^>]*>([\s\S]*?)<\/summary>/gi

  const transcriptMatches = Array.from(mcpContent.matchAll(transcriptRegex))
  const summaryMatches = Array.from(mcpContent.matchAll(summaryRegex))

  // Приоритет: transcript > summary
  if (transcriptMatches.length > 0) {
    const lastTranscript = transcriptMatches[transcriptMatches.length - 1]
    return {
      block_id: '',
      block_type: 'transcription',
      content: lastTranscript[1].trim(),
      title: 'Последняя транскрипция',
      has_transcription: true,
      has_summary: false
    }
  }

  if (summaryMatches.length > 0) {
    const lastSummary = summaryMatches[summaryMatches.length - 1]
    return {
      block_id: '',
      block_type: 'summary',
      content: lastSummary[1].trim(),
      title: 'Последнее саммари',
      has_transcription: false,
      has_summary: true
    }
  }

  // Если ничего не найдено, ищем по ключевым словам
  const lines = mcpContent.split('\n')
  let transcriptionStart = -1
  let summaryStart = -1

  for (let i = 0; i < lines.length; i++) {
    const lineLower = lines[i].toLowerCase()
    if ((lineLower.includes('transcript') || lineLower.includes('транскрипт')) && transcriptionStart === -1) {
      transcriptionStart = i
    }
    if ((lineLower.includes('summary') || lineLower.includes('саммари') || lineLower.includes('резюме')) && summaryStart === -1) {
      summaryStart = i
    }
  }

  if (transcriptionStart >= 0) {
    const content = lines.slice(transcriptionStart).join('\n').trim()
    return {
      block_id: '',
      block_type: 'transcription',
      content: content,
      title: 'Последняя транскрипция',
      has_transcription: true,
      has_summary: false
    }
  }

  if (summaryStart >= 0) {
    const content = lines.slice(summaryStart).join('\n').trim()
    return {
      block_id: '',
      block_type: 'summary',
      content: content,
      title: 'Последнее саммари',
      has_transcription: false,
      has_summary: true
    }
  }

  // Последний fallback: берем последние 20000 символов
  const lastContent = mcpContent.length > 20000 
    ? mcpContent.slice(-20000).trim()
    : mcpContent.trim()

  return {
    block_id: '',
    block_type: 'copied_text',
    content: lastContent,
    title: lastContent.split('\n')[0]?.substring(0, 100) || 'Скопированный текст',
    has_transcription: false,
    has_summary: false
  }
}
