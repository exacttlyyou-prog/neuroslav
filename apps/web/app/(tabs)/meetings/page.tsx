import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { MeetingUploadForm } from "@/components/forms/MeetingUploadForm"
import { MeetingHistory } from "@/components/meetings/MeetingHistory"
import { MeetingAutoProcess } from "@/components/meetings/MeetingAutoProcess"

export default function MeetingsPage() {
  return (
    <div className="container mx-auto max-w-5xl py-8 px-4 space-y-8">
      <div className="space-y-2 mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Встречи</h1>
        <p className="text-muted-foreground text-lg">
          Автоматическая обработка встреч из Notion с AI-анализом и согласованием
        </p>
      </div>

      <MeetingAutoProcess />
      
      <Card className="shadow-md border-2">
        <CardHeader className="bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-950/20 dark:to-purple-950/20">
          <CardTitle className="text-xl font-bold">Ручная загрузка</CardTitle>
          <CardDescription className="text-base">
            Загрузи аудио или вставь транскрипт — Нейрослав разберет и подготовит саммари
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6">
          <MeetingUploadForm />
        </CardContent>
      </Card>
      
      <Card className="shadow-md border-2">
        <CardHeader className="bg-gradient-to-r from-slate-50 to-gray-50 dark:from-slate-950/20 dark:to-gray-950/20">
          <CardTitle className="text-xl font-bold">История встреч</CardTitle>
        </CardHeader>
        <CardContent className="pt-6">
          <MeetingHistory />
        </CardContent>
      </Card>
    </div>
  )
}
