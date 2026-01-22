"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { apiPost } from "@/lib/api"
import { CreateTaskInput, TaskResponse } from "@/types/tasks"

const taskFormSchema = z.object({
  text: z.string().min(1, "Текст задачи обязателен"),
})

type TaskFormValues = z.infer<typeof taskFormSchema>

export function TaskInputForm() {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)

  const form = useForm<TaskFormValues>({
    resolver: zodResolver(taskFormSchema),
    defaultValues: {
      text: "",
    },
  })

  async function onSubmit(data: TaskFormValues) {
    setIsSubmitting(true)
    setSubmitMessage(null)

    try {
      const input: CreateTaskInput = {
        text: data.text,
      }

      const response = await apiPost<TaskResponse>("/api/tasks", input)
      setSubmitMessage(response.message)
      form.reset()
    } catch (error) {
      setSubmitMessage(error instanceof Error ? error.message : "Ошибка при создании задачи")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="text"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Что нужно сделать?</FormLabel>
              <FormControl>
                <Input
                  placeholder="Например: напомни про встречу во вторник"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Нейрослав сам определит дедлайн и приоритет
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={isSubmitting} className="hover-lift">
          {isSubmitting ? "Обрабатываю..." : "Добавить"}
        </Button>
        {submitMessage && (
          <p className={`text-sm ${submitMessage.includes("Ошибка") ? "text-destructive" : "text-muted-foreground"}`}>
            {submitMessage}
          </p>
        )}
      </form>
    </Form>
  )
}
