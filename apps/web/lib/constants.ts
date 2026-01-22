// Константы приложения

export const API_ENDPOINTS = {
  TASKS: '/api/tasks',
  MEETINGS: '/api/meetings',
  KNOWLEDGE: '/api/knowledge',
} as const

export const TASK_STATUSES = {
  PENDING: 'pending',
  SCHEDULED: 'scheduled',
  COMPLETED: 'completed',
} as const

export const MEETING_STATUSES = {
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  SENT: 'sent',
  ERROR: 'error',
} as const

export const FILE_TYPES = {
  PDF: 'application/pdf',
  DOCX: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  PPTX: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  AUDIO: ['audio/mpeg', 'audio/wav', 'audio/mp3'],
} as const

export const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
