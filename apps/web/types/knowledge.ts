export interface KnowledgeItem {
  id: string
  sourceFile: string
  fileType: string
  indexedAt: Date | string
  metadata?: Record<string, unknown>
}

export interface KnowledgeSearchResult {
  id: string
  content: string
  sourceFile: string
  score: number
  metadata?: Record<string, unknown>
}

export interface KnowledgeIndexInput {
  file: File
}

export interface KnowledgeIndexResponse {
  item: KnowledgeItem
  chunksCount: number
  message: string
}

export interface KnowledgeSearchInput {
  query: string
  limit?: number
}

export interface KnowledgeSearchResponse {
  results: KnowledgeSearchResult[]
  query: string
}
