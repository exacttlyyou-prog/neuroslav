import { Status } from './index'

export interface Task {
  id: string
  text: string
  deadline?: Date | string
  status: Status
  createdAt: Date | string
  notifiedAt?: Date | string
}

export interface CreateTaskInput {
  text: string
  deadline?: string
  create_in_notion?: boolean
}

export interface TaskResponse {
  task: Task
  message: string
}
