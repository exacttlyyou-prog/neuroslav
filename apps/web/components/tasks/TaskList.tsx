"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { apiGet } from "@/lib/api"
import { Task } from "@/types/tasks"
import { Clock } from "lucide-react"

type TaskStatus = "pending" | "overdue" | "completed" | "all"

// Расширяем тип Task для совместимости с API
interface TaskWithStatus extends Omit<Task, "status"> {
  status: string
  intent?: string
  priority?: string
}

export function TaskList() {
  const [tasks, setTasks] = useState<TaskWithStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<TaskStatus>("all")

  useEffect(() => {
    loadTasks()
  }, [filter])

  async function loadTasks() {
    try {
      setLoading(true)
      const status = filter === "all" ? undefined : filter
      const response = await apiGet<{ tasks: TaskWithStatus[]; error?: string }>(
        status ? `/api/tasks?status=${status}` : "/api/tasks"
      )
      if (response.error) {
        console.error("Ошибка API:", response.error)
        // Показываем пустой список, если бэкенд не запущен
        setTasks([])
      } else {
        setTasks(response.tasks || [])
      }
    } catch (error) {
      console.error("Ошибка при загрузке задач:", error)
      setTasks([]) // Показываем пустой список при ошибке
    } finally {
      setLoading(false)
    }
  }

  function getStatusBadge(status: string) {
    const variants: Record<string, "default" | "secondary" | "destructive"> = {
      pending: "default",
      completed: "secondary",
      overdue: "destructive",
    }
    const labels: Record<string, string> = {
      pending: "В работе",
      completed: "Готово",
      overdue: "Просрочено",
    }
    return (
      <Badge variant={variants[status] || "default"}>
        {labels[status] || status}
      </Badge>
    )
  }

  function getPriorityBadge(priority: string | undefined) {
    if (!priority) return null
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      High: "destructive",
      Medium: "default",
      Low: "outline",
    }
    return (
      <Badge variant={variants[priority] || "outline"} className="ml-2">
        {priority}
      </Badge>
    )
  }

  function formatDate(dateInput: string | Date | null | undefined) {
    if (!dateInput) return "—"
    const date = dateInput instanceof Date ? dateInput : new Date(dateInput)
    if (isNaN(date.getTime())) return "—"
    return date.toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "short",
      year: date.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
    })
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-20 bg-muted rounded-lg animate-pulse" />
        ))}
      </div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <p>Нет задач</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(["all", "pending", "overdue", "completed"] as TaskStatus[]).map((f) => (
          <Button
            key={f}
            variant={filter === f ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(f)}
            className="rounded-lg"
          >
            {f === "all" ? "Все" : f === "pending" ? "В работе" : f === "overdue" ? "Просрочено" : "Готово"}
          </Button>
        ))}
      </div>

      <div className="space-y-3">
        {tasks.map((task) => (
          <Card key={task.id} className="hover-lift border-l-4 border-l-primary/50">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 space-y-1">
                  <p className="font-semibold text-base">{task.intent || task.text}</p>
                  {task.intent && task.text !== task.intent && (
                    <p className="text-sm text-muted-foreground line-clamp-2 italic">
                      "{task.text}"
                    </p>
                  )}
                  <div className="flex items-center gap-3 pt-1">
                    {task.deadline && (
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDate(task.deadline)}
                      </p>
                    )}
                    {getPriorityBadge(task.priority)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {getStatusBadge(task.status)}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
