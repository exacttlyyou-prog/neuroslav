"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { MeetingProcessingResponse, Participant, Project, ActionItem, KeyDecision } from "@/types/meetings"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { apiRequest } from "@/lib/api"
import { AlertCircle, CheckCircle2, XCircle, Loader2 } from "lucide-react"

interface MeetingResultsProps {
  result: MeetingProcessingResponse | null
  onApproved?: () => void
}

export function MeetingResults({ result, onApproved }: MeetingResultsProps) {
  const [summary, setSummary] = useState(result?.summary || "")
  const [participants, setParticipants] = useState<Participant[]>(result?.participants || [])
  const [projects, setProjects] = useState<Project[]>(result?.projects || [])
  const [actionItems, setActionItems] = useState<ActionItem[]>(result?.action_items || [])
  const [keyDecisions, setKeyDecisions] = useState<KeyDecision[]>(result?.key_decisions || [])
  const [insights, setInsights] = useState<string[]>(result?.insights || [])
  const [nextSteps, setNextSteps] = useState<string[]>(result?.next_steps || [])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (result) {
      setSummary(result.summary || "")
      setParticipants(result.participants || [])
      setProjects(result.projects || [])
      setActionItems(result.action_items || [])
      setKeyDecisions(result.key_decisions || [])
      setInsights(result.insights || [])
      setNextSteps(result.next_steps || [])
    }
  }, [result])

  if (!result) return null

  const handleApproveAndSend = async () => {
    if (!result.meeting_id) {
      setError("ID встречи не найден")
      return
    }

    setSending(true)
    setError(null)
    setSuccess(false)

    try {
      await apiRequest(`/api/meetings/${result.meeting_id}/approve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          summary,
          participants,
          action_items: actionItems,
          key_decisions: keyDecisions,
          insights: insights,
          next_steps: nextSteps,
        }),
      })

      setSuccess(true)
      onApproved?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка при отправке")
    } finally {
      setSending(false)
    }
  }

  const addParticipant = () => {
    setParticipants([...participants, { name: "", matched: false }])
  }

  const removeParticipant = (index: number) => {
    setParticipants(participants.filter((_, i) => i !== index))
  }

  const updateParticipant = (index: number, field: keyof Participant, value: string | boolean) => {
    const updated = [...participants]
    updated[index] = { ...updated[index], [field]: value }
    setParticipants(updated)
  }

  const addActionItem = () => {
    setActionItems([...actionItems, { text: "", priority: "Medium" }])
  }

  const removeActionItem = (index: number) => {
    setActionItems(actionItems.filter((_, i) => i !== index))
  }

  const updateActionItem = (index: number, field: keyof ActionItem, value: string) => {
    const updated = [...actionItems]
    updated[index] = { ...updated[index], [field]: value }
    setActionItems(updated)
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Разделение экрана: Транскрипция | Саммари + Задачи */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Аудио-плеер (если есть аудио) */}
        {result.transcript && (
          <div className="lg:col-span-2">
            {/* Плеер будет добавлен, когда будет доступен URL аудио */}
          </div>
        )}
        {/* Левая панель: Транскрипция */}
        <Card className="shadow-md border-2">
          <CardHeader className="bg-gradient-to-r from-slate-50 to-gray-50 dark:from-slate-950/20 dark:to-gray-950/20">
            <CardTitle className="text-xl font-bold flex items-center gap-2">
              <span>📝</span>
              Транскрипция
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="space-y-4">
              {result.transcript ? (
                <div className="prose prose-sm max-w-none text-sm">
                  <pre className="whitespace-pre-wrap font-mono text-xs bg-muted/50 p-4 rounded-lg overflow-auto max-h-[600px]">
                    {result.transcript}
                  </pre>
                </div>
              ) : (
                <div className="text-sm text-muted-foreground text-center py-8">
                  Транскрипция недоступна
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Правая панель: Саммари + Задачи */}
        <div className="space-y-6">
      {/* Саммари */}
      <Card className="shadow-md border-2 animate-in fade-in slide-in-from-left duration-300">
        <CardHeader className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/20 dark:to-indigo-950/20">
          <CardTitle className="text-xl font-bold flex items-center gap-2">
            <span>📝</span>
            Саммари встречи
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="space-y-4">
            <Textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={12}
              className="font-mono text-sm border-2 focus:border-primary transition-colors"
              placeholder="Саммари встречи..."
            />
            <div className="text-sm text-muted-foreground">
              <p className="mb-2 font-semibold">Предпросмотр (Markdown):</p>
              <div className="prose prose-sm max-w-none border-2 rounded-lg p-4 bg-muted/50 dark:prose-invert">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {summary || "*Саммари не заполнено*"}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Участники */}
      <Card className="shadow-md border-2 animate-in fade-in slide-in-from-right duration-300 delay-75">
        <CardHeader className="bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-950/20 dark:to-pink-950/20">
          <CardTitle className="text-xl font-bold flex items-center gap-2">
            <span>👥</span>
            Участники
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-6 space-y-3">
          {participants.map((p, idx) => (
            <div 
              key={idx} 
              className="flex items-center gap-3 p-4 border-2 rounded-lg hover:border-primary/50 transition-colors bg-card"
            >
              <div className="flex-1">
                <Input
                  value={p.name}
                  onChange={(e) => updateParticipant(idx, "name", e.target.value)}
                  placeholder="Имя участника"
                  className={!p.matched ? "border-orange-300 focus:border-orange-500" : "border-green-300 focus:border-green-500"}
                />
              </div>
              <div className="flex items-center gap-2">
                {p.matched ? (
                  <Badge variant="default" className="gap-1.5 px-3 py-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Найден
                  </Badge>
                ) : (
                  <Badge variant="outline" className="gap-1.5 px-3 py-1.5 text-orange-600 border-orange-300 bg-orange-50 dark:bg-orange-950/20">
                    <AlertCircle className="w-3.5 h-3.5" />
                    Не найден
                  </Badge>
                )}
                {p.matchScore && p.matchScore < 1.0 && (
                  <span className="text-xs text-muted-foreground font-medium">
                    {Math.round(p.matchScore * 100)}%
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeParticipant(idx)}
                  className="text-destructive hover:bg-destructive/10"
                >
                  <XCircle className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}
          <Button 
            variant="outline" 
            onClick={addParticipant} 
            className="w-full border-2 border-dashed hover:border-solid transition-all"
          >
            + Добавить участника
          </Button>
        </CardContent>
      </Card>

      {/* Проекты */}
      {projects && projects.length > 0 && (
        <Card className="shadow-md border-2">
          <CardHeader className="bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/20 dark:to-emerald-950/20">
            <CardTitle className="text-xl font-bold flex items-center gap-2">
              <span>📁</span>
              Проекты
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="flex flex-wrap gap-2">
              {projects.map((project, idx) => (
                <Badge
                  key={idx}
                  variant={project.matched ? "default" : "outline"}
                  className={`px-3 py-1.5 text-sm ${
                    !project.matched 
                      ? "border-orange-300 text-orange-600 bg-orange-50 dark:bg-orange-950/20" 
                      : ""
                  }`}
                >
                  {project.name || project.key}
                  {!project.matched && (
                    <AlertCircle className="w-3 h-3 ml-1.5" />
                  )}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ключевые решения */}
      {keyDecisions && keyDecisions.length > 0 && (
        <Card className="shadow-md border-2 animate-in fade-in slide-in-from-bottom duration-300 delay-100">
          <CardHeader className="bg-gradient-to-r from-blue-50 to-cyan-50 dark:from-blue-950/20 dark:to-cyan-950/20">
            <CardTitle className="text-xl font-bold flex items-center gap-2">
              <span>🎯</span>
              Ключевые решения
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-4">
            {keyDecisions.map((decision, idx) => (
              <div 
                key={idx} 
                className="p-4 border-2 rounded-lg space-y-3 hover:border-primary/50 transition-colors bg-card"
              >
                <div>
                  <Label className="text-sm font-semibold mb-2 block">Название решения</Label>
                  <Input
                    value={decision.title}
                    onChange={(e) => {
                      const updated = [...keyDecisions]
                      updated[idx] = { ...updated[idx], title: e.target.value }
                      setKeyDecisions(updated)
                    }}
                    placeholder="Название решения..."
                    className="border-2 focus:border-primary transition-colors"
                  />
                </div>
                <div>
                  <Label className="text-sm font-semibold mb-2 block">Описание</Label>
                  <Textarea
                    value={decision.description}
                    onChange={(e) => {
                      const updated = [...keyDecisions]
                      updated[idx] = { ...updated[idx], description: e.target.value }
                      setKeyDecisions(updated)
                    }}
                    placeholder="Описание решения..."
                    rows={3}
                    className="border-2 focus:border-primary transition-colors"
                  />
                </div>
                {decision.impact && (
                  <div>
                    <Label className="text-sm font-semibold mb-2 block">Влияние</Label>
                    <Input
                      value={decision.impact}
                      onChange={(e) => {
                        const updated = [...keyDecisions]
                        updated[idx] = { ...updated[idx], impact: e.target.value }
                        setKeyDecisions(updated)
                      }}
                      placeholder="Влияние на проект/команду..."
                      className="border-2 focus:border-primary transition-colors"
                    />
                  </div>
                )}
                <div className="flex justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setKeyDecisions(keyDecisions.filter((_, i) => i !== idx))}
                    className="text-destructive hover:bg-destructive/10"
                  >
                    <XCircle className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
            <Button 
              variant="outline" 
              onClick={() => setKeyDecisions([...keyDecisions, { title: "", description: "", impact: "" }])} 
              className="w-full border-2 border-dashed hover:border-solid transition-all"
            >
              + Добавить решение
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Инсайты */}
      {insights && insights.length > 0 && (
        <Card className="shadow-md border-2 animate-in fade-in slide-in-from-bottom duration-300 delay-150">
          <CardHeader className="bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-950/20 dark:to-purple-950/20">
            <CardTitle className="text-xl font-bold flex items-center gap-2">
              <span>💡</span>
              Инсайты
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-3">
            {insights.map((insight, idx) => (
              <div 
                key={idx} 
                className="flex items-center gap-3 p-4 border-2 rounded-lg hover:border-primary/50 transition-colors bg-card"
              >
                <Textarea
                  value={insight}
                  onChange={(e) => {
                    const updated = [...insights]
                    updated[idx] = e.target.value
                    setInsights(updated)
                  }}
                  placeholder="Инсайт..."
                  rows={2}
                  className="flex-1 border-2 focus:border-primary transition-colors"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setInsights(insights.filter((_, i) => i !== idx))}
                  className="text-destructive hover:bg-destructive/10"
                >
                  <XCircle className="w-4 h-4" />
                </Button>
              </div>
            ))}
            <Button 
              variant="outline" 
              onClick={() => setInsights([...insights, ""])} 
              className="w-full border-2 border-dashed hover:border-solid transition-all"
            >
              + Добавить инсайт
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Следующие шаги */}
      {nextSteps && nextSteps.length > 0 && (
        <Card className="shadow-md border-2 animate-in fade-in slide-in-from-bottom duration-300 delay-200">
          <CardHeader className="bg-gradient-to-r from-teal-50 to-cyan-50 dark:from-teal-950/20 dark:to-cyan-950/20">
            <CardTitle className="text-xl font-bold flex items-center gap-2">
              <span>🚀</span>
              Следующие шаги
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6 space-y-3">
            {nextSteps.map((step, idx) => (
              <div 
                key={idx} 
                className="flex items-center gap-3 p-4 border-2 rounded-lg hover:border-primary/50 transition-colors bg-card"
              >
                <Textarea
                  value={step}
                  onChange={(e) => {
                    const updated = [...nextSteps]
                    updated[idx] = e.target.value
                    setNextSteps(updated)
                  }}
                  placeholder="Следующий шаг..."
                  rows={2}
                  className="flex-1 border-2 focus:border-primary transition-colors"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setNextSteps(nextSteps.filter((_, i) => i !== idx))}
                  className="text-destructive hover:bg-destructive/10"
                >
                  <XCircle className="w-4 h-4" />
                </Button>
              </div>
            ))}
            <Button 
              variant="outline" 
              onClick={() => setNextSteps([...nextSteps, ""])} 
              className="w-full border-2 border-dashed hover:border-solid transition-all"
            >
              + Добавить шаг
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Задачи */}
      <Card className="shadow-md border-2 animate-in fade-in slide-in-from-bottom duration-300 delay-250">
        <CardHeader className="bg-gradient-to-r from-yellow-50 to-amber-50 dark:from-yellow-950/20 dark:to-amber-950/20">
          <CardTitle className="text-xl font-bold flex items-center gap-2">
            <span>✅</span>
            Задачи (Action Items)
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-6 space-y-4">
          {actionItems.map((item, idx) => (
            <div 
              key={idx} 
              className="p-4 border-2 rounded-lg space-y-3 hover:border-primary/50 transition-colors bg-card"
            >
              <div>
                <Label className="text-sm font-semibold mb-2 block">Текст задачи</Label>
                <Textarea
                  value={item.text}
                  onChange={(e) => updateActionItem(idx, "text", e.target.value)}
                  placeholder="Описание задачи..."
                  rows={2}
                  className="border-2 focus:border-primary transition-colors"
                />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <Label className="text-sm font-semibold mb-2 block">Ответственный</Label>
                  <Input
                    value={item.assignee || ""}
                    onChange={(e) => updateActionItem(idx, "assignee", e.target.value)}
                    placeholder="Имя ответственного"
                    className="border-2 focus:border-primary transition-colors"
                  />
                </div>
                <div className="w-36">
                  <Label className="text-sm font-semibold mb-2 block">Приоритет</Label>
                  <select
                    value={item.priority}
                    onChange={(e) => updateActionItem(idx, "priority", e.target.value as ActionItem["priority"])}
                    className={`w-full h-10 px-3 rounded-md border-2 bg-background transition-colors ${
                      item.priority === 'High' ? 'border-red-300 focus:border-red-500' :
                      item.priority === 'Medium' ? 'border-yellow-300 focus:border-yellow-500' :
                      'border-green-300 focus:border-green-500'
                    }`}
                  >
                    <option value="High">High</option>
                    <option value="Medium">Medium</option>
                    <option value="Low">Low</option>
                  </select>
                </div>
                <div className="flex items-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeActionItem(idx)}
                    className="text-destructive hover:bg-destructive/10"
                  >
                    <XCircle className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
          <Button 
            variant="outline" 
            onClick={addActionItem} 
            className="w-full border-2 border-dashed hover:border-solid transition-all"
          >
            + Добавить задачу
          </Button>
        </CardContent>
      </Card>

      {/* Предупреждения */}
      {result.verification_warnings && result.verification_warnings.length > 0 && (
        <Card className="border-2 border-orange-300 bg-orange-50 dark:bg-orange-950/20 shadow-md">
          <CardHeader>
            <CardTitle className="text-orange-800 dark:text-orange-300 flex items-center gap-2">
              <AlertCircle className="w-5 h-5" />
              Предупреждения
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc list-inside space-y-2 text-sm text-orange-700 dark:text-orange-300">
              {result.verification_warnings.map((warning, idx) => (
                <li key={idx} className="font-medium">{warning}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Кнопка отправки */}
      <Card className="shadow-lg border-2 border-primary/20">
        <CardContent className="pt-6">
          <div className="space-y-4">
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
            {success && (
              <div className="p-4 bg-green-50 dark:bg-green-950/20 border-2 border-green-200 dark:border-green-800 rounded-lg">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0" />
                  <p className="font-semibold text-green-800 dark:text-green-300">
                    Встреча успешно отправлена в Telegram
                  </p>
                </div>
              </div>
            )}
            <Button
              onClick={handleApproveAndSend}
              disabled={sending || success}
              className="w-full h-12 text-lg font-semibold shadow-lg hover:shadow-xl transition-all"
              size="lg"
            >
              {sending ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Отправка...
                </>
              ) : success ? (
                <>
                  <CheckCircle2 className="w-5 h-5 mr-2" />
                  Отправлено
                </>
              ) : (
                <>
                  <span className="mr-2">📤</span>
                  Отправить в Telegram
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
        </div>
      </div>
    </div>
  )
}
