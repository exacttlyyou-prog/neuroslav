"use client"

import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { apiGet } from "@/lib/api"

interface KnowledgeItem {
  content: string
  metadata: {
    doc_id?: string
    source_file?: string
    [key: string]: any
  }
  score?: number
}

export function KnowledgeSearch() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<KnowledgeItem[]>([])
  const [loading, setLoading] = useState(false)

  async function handleSearch() {
    if (!query.trim()) return

    try {
      setLoading(true)
      const response = await apiGet<{ results: KnowledgeItem[] }>(
        `/api/knowledge/search?q=${encodeURIComponent(query)}&limit=5`
      )
      // API возвращает { results: [...] }
      setResults(response.results || [])
    } catch (error) {
      console.error("Ошибка при поиске:", error)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  function highlightText(text: string, query: string) {
    if (!query) return text
    const parts = text.split(new RegExp(`(${query})`, "gi"))
    return parts.map((part, i) =>
      part.toLowerCase() === query.toLowerCase() ? (
        <mark key={i} className="bg-accent/20 rounded px-1">
          {part}
        </mark>
      ) : (
        part
      )
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input
          placeholder="Найди по смыслу..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          className="rounded-lg flex-1"
        />
        <Button onClick={handleSearch} disabled={loading || !query.trim()}>
          {loading ? "Ищу..." : "Найти"}
        </Button>
      </div>

      {results.length > 0 && (
        <div className="space-y-3">
          {results.map((item, idx) => (
            <Card key={idx} className="hover-lift">
              <CardContent className="p-4">
                <div className="space-y-2">
                  {item.metadata.source_file && (
                    <p className="text-xs text-muted-foreground font-medium">
                      {item.metadata.source_file}
                    </p>
                  )}
                  <p className="text-sm leading-relaxed">
                    {highlightText(item.content, query)}
                  </p>
                  {item.score && (
                    <p className="text-xs text-muted-foreground">
                      Релевантность: {Math.round(item.score * 100)}%
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {results.length === 0 && query && !loading && (
        <div className="text-center py-8 text-muted-foreground">
          <p>Ничего не найдено</p>
        </div>
      )}
    </div>
  )
}
