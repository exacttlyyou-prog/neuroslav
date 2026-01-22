"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { apiRequest } from "@/lib/api"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { MeetingResults } from "./MeetingResults"
import { Loader2, CheckCircle2, AlertCircle, Clock, Zap } from "lucide-react"

interface AutoProcessResult {
  page_id: string
  block_id: string
  block_type: string
  content: string
  title: string
  method: string
  processing?: {
    status: string
    meeting_id?: string
    summary?: string
    participants?: Array<{ name: string; matched?: boolean }>
    projects?: Array<{ key: string; name: string; matched?: boolean }>
    action_items?: Array<{ text: string; assignee?: string; priority: string }>
    verification_warnings?: string[]
    requires_approval?: boolean
    error?: string
  }
}

type ProcessingStage = 'idle' | 'fetching' | 'processing' | 'completed' | 'error'

export function MeetingAutoProcess() {
  const [loading, setLoading] = useState(false)
  const [stage, setStage] = useState<ProcessingStage>('idle')
  const [result, setResult] = useState<AutoProcessResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleGetLastMeeting = async (shouldProcess: boolean = false) => {
    setLoading(true)
    setError(null)
    setResult(null)
    setStage('fetching')

    try {
      const endpoint = `/api/notion/last-meeting/auto?process=${shouldProcess}`
      
      if (shouldProcess) {
        setStage('processing')
      }
      
      const data = await apiRequest<AutoProcessResult>(endpoint, {
        method: "POST",
      })

      setResult(data)
      
      if (shouldProcess && data.processing) {
        if (data.processing.status === "pending_approval") {
          setStage('completed')
        } else if (data.processing.status === "error") {
          setStage('error')
        } else {
          setStage('completed')
        }
      } else {
        setStage('completed')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Неизвестная ошибка")
      setStage('error')
    } finally {
      setLoading(false)
    }
  }

  const getMethodBadge = (method: string) => {
    const methods: Record<string, { label: string; variant: "default" | "secondary" | "outline" }> = {
      "nextjs_mcp": { label: "MCP Notion", variant: "default" },
      "mcp_server": { label: "MCP Notion", variant: "default" },  // Локальный MCP сервер
      "notion_api": { label: "Notion API", variant: "secondary" },
      "playwright_browser": { label: "Браузер", variant: "outline" }
    }
    return methods[method] || { label: method, variant: "outline" as const }
  }

  return (
    <Card className="shadow-lg border-2">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-2xl font-bold">Автоматическая обработка встреч</CardTitle>
            <CardDescription className="mt-2 text-base">
              Получи последнюю встречу из Notion и обработай её автоматически
            </CardDescription>
          </div>
          {stage === 'fetching' && <Loader2 className="w-6 h-6 animate-spin text-primary" />}
          {stage === 'processing' && <Zap className="w-6 h-6 animate-pulse text-yellow-500" />}
          {stage === 'completed' && <CheckCircle2 className="w-6 h-6 text-green-500" />}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Кнопки действий */}
        <div className="flex gap-3">
          <Button
            onClick={() => handleGetLastMeeting(false)}
            disabled={loading}
            variant="outline"
            size="lg"
            className="flex-1"
          >
            {stage === 'fetching' ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Загрузка...
              </>
            ) : (
              <>
                <Clock className="w-4 h-4 mr-2" />
                Получить встречу
              </>
            )}
          </Button>
          <Button
            onClick={() => handleGetLastMeeting(true)}
            disabled={loading}
            size="lg"
            className="flex-1"
          >
            {stage === 'processing' ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Обработка...
              </>
            ) : (
              <>
                <Zap className="w-4 h-4 mr-2" />
                Обработать встречу
              </>
            )}
          </Button>
        </div>

        {/* Индикатор прогресса */}
        {loading && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {stage === 'fetching' && (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Получение данных из Notion...
                </>
              )}
              {stage === 'processing' && (
                <>
                  <Zap className="w-4 h-4 animate-pulse" />
                  Обработка встречи через AI...
                </>
              )}
            </div>
            <div className="w-full bg-muted rounded-full h-2">
              <div 
                className="bg-primary h-2 rounded-full transition-all duration-300"
                style={{ 
                  width: stage === 'fetching' ? '50%' : stage === 'processing' ? '100%' : '0%' 
                }}
              />
            </div>
          </div>
        )}

        {/* Ошибка */}
        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-950/20 border-2 border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="font-semibold text-red-800 dark:text-red-300 mb-1">Ошибка</p>
                <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Результат получения данных */}
        {result && !result.processing && (
          <Card className="bg-muted/50">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">{result.title || "Последняя встреча"}</CardTitle>
                <Badge {...getMethodBadge(result.method)}>
                  {getMethodBadge(result.method).label}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-muted-foreground mb-3">
                Получено {result.content.length} символов
              </div>
              <div className="p-4 bg-background border rounded-lg max-h-60 overflow-y-auto">
                <pre className="text-xs whitespace-pre-wrap font-mono">
                  {result.content.substring(0, 1000)}
                  {result.content.length > 1000 && "\n\n... (показаны первые 1000 символов)"}
                </pre>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Результат обработки */}
        {result?.processing && (
          <div className="space-y-4">
            {result.processing.status === "pending_approval" && (
              <Card className="border-2 border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/20">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Clock className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    <CardTitle className="text-lg text-blue-900 dark:text-blue-100">
                      Встреча обработана и ожидает согласования
                    </CardTitle>
                  </div>
                  <CardDescription className="text-blue-700 dark:text-blue-300">
                    Пожалуйста, просмотрите и отредактируйте результат перед отправкой
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <MeetingResults 
                    result={{
                      meeting_id: result.processing.meeting_id || "",
                      summary: result.processing.summary || "",
                      participants: result.processing.participants || [],
                      projects: result.processing.projects || [],
                      action_items: result.processing.action_items || [],
                      verification_warnings: result.processing.verification_warnings || [],
                      requires_approval: true,
                      status: "pending_approval",
                      message: "Встреча обработана и ожидает согласования"
                    }}
                    onApproved={() => {
                      setStage('completed')
                    }}
                  />
                </CardContent>
              </Card>
            )}

            {result.processing.status === "completed" && (
              <Card className="border-2 border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/20">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                    <CardTitle className="text-lg text-green-900 dark:text-green-100">
                      Встреча успешно обработана
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {result.processing.summary && (
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {result.processing.summary}
                      </ReactMarkdown>
                    </div>
                  )}
                  
                  {result.processing.participants && result.processing.participants.length > 0 && (
                    <div>
                      <p className="text-sm font-semibold mb-2">Участники:</p>
                      <div className="flex flex-wrap gap-2">
                        {result.processing.participants.map((p, idx) => (
                          <Badge 
                            key={idx} 
                            variant={typeof p === "object" && p.matched ? "default" : "outline"}
                            className={typeof p === "object" && !p.matched ? "border-orange-300" : ""}
                          >
                            {typeof p === "string" ? p : p.name || "Неизвестно"}
                            {typeof p === "object" && !p.matched && (
                              <AlertCircle className="w-3 h-3 ml-1" />
                            )}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {result.processing.projects && result.processing.projects.length > 0 && (
                    <div>
                      <p className="text-sm font-semibold mb-2">Проекты:</p>
                      <div className="flex flex-wrap gap-2">
                        {result.processing.projects.map((project, idx) => (
                          <Badge 
                            key={idx}
                            variant={project.matched ? "default" : "outline"}
                            className={!project.matched ? "border-orange-300" : ""}
                          >
                            {project.name || project.key}
                            {!project.matched && <AlertCircle className="w-3 h-3 ml-1" />}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {result.processing.action_items && result.processing.action_items.length > 0 && (
                    <div>
                      <p className="text-sm font-semibold mb-2">Задачи:</p>
                      <ul className="list-disc list-inside space-y-1 text-sm">
                        {result.processing.action_items.map((item, idx) => (
                          <li key={idx} className="flex items-start gap-2">
                            <span className="flex-1">
                              {typeof item === "string" ? item : item.text}
                            </span>
                            {typeof item === "object" && item.assignee && (
                              <Badge variant="secondary" className="text-xs">
                                {item.assignee}
                              </Badge>
                            )}
                            {typeof item === "object" && item.priority && (
                              <Badge 
                                variant="outline" 
                                className={`text-xs ${
                                  item.priority === 'High' ? 'border-red-300' :
                                  item.priority === 'Medium' ? 'border-yellow-300' :
                                  'border-green-300'
                                }`}
                              >
                                {item.priority}
                              </Badge>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {result.processing.status === "error" && (
              <Card className="border-2 border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/20">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
                    <CardTitle className="text-lg text-red-900 dark:text-red-100">
                      Ошибка обработки
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-red-700 dark:text-red-400">
                    {result.processing.error || "Неизвестная ошибка"}
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
