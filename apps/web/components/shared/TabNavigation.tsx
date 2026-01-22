"use client"

import { usePathname, useRouter } from "next/navigation"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

export function TabNavigation() {
  const pathname = usePathname()
  const router = useRouter()

  const currentTab = pathname?.split('/').pop() || 'tasks'

  const handleTabChange = (value: string) => {
    router.push(`/${value}`)
  }

  return (
    <Tabs value={currentTab} onValueChange={handleTabChange} className="w-full">
      <TabsList className="grid w-full grid-cols-3">
        <TabsTrigger value="tasks">Задачи</TabsTrigger>
        <TabsTrigger value="meetings">Встречи</TabsTrigger>
        <TabsTrigger value="context">Знания</TabsTrigger>
      </TabsList>
    </Tabs>
  )
}
