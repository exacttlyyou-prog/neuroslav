"use client"

import { usePathname, useRouter } from "next/navigation"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card } from "@/components/ui/card"

export default function TabsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()

  const currentTab = pathname?.split('/').pop() || 'tasks'

  const handleTabChange = (value: string) => {
    router.push(`/${value}`)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto py-8 px-4 max-w-6xl">
        <div className="mb-10">
          <h1 className="text-display font-bold tracking-tight mb-2">Нейрослав</h1>
          <p className="text-muted-foreground text-lg">Персональный движок обработки</p>
        </div>
        <Tabs value={currentTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full grid-cols-5 mb-8 rounded-lg">
          <TabsTrigger value="chat">Чат</TabsTrigger>
          <TabsTrigger value="tasks">Задачи</TabsTrigger>
          <TabsTrigger value="meetings">Встречи</TabsTrigger>
          <TabsTrigger value="context">Знания</TabsTrigger>
          <TabsTrigger value="daily-checkin">Опросы</TabsTrigger>
        </TabsList>
          <div>
            {children}
          </div>
        </Tabs>
      </div>
    </div>
  )
}
