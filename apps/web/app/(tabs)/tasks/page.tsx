import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { TaskInputForm } from "@/components/forms/TaskInputForm"
import { TaskList } from "@/components/tasks/TaskList"

export default function TasksPage() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Задачи</CardTitle>
          <CardDescription>
            Добавь задачу — Нейрослав определит дедлайн и напомнит
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TaskInputForm />
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader>
          <CardTitle>Активные задачи</CardTitle>
        </CardHeader>
        <CardContent>
          <TaskList />
        </CardContent>
      </Card>
    </div>
  )
}
