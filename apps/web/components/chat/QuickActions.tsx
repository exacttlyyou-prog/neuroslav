"use client"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface QuickActionsProps {
  onProcessLastMeeting?: () => void
  onShowTasks?: () => void
  onSearchKnowledge?: () => void
}

export function QuickActions({
  onProcessLastMeeting,
  onShowTasks,
  onSearchKnowledge
}: QuickActionsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Быстрые действия</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start"
          onClick={onProcessLastMeeting}
        >
          📋 Обработать последнюю встречу
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start"
          onClick={onShowTasks}
        >
          ✅ Мои задачи
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start"
          onClick={onSearchKnowledge}
        >
          🔍 Поиск по знаниям
        </Button>
      </CardContent>
    </Card>
  )
}
