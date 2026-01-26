export interface Meeting {
  id: string
  transcript?: string
  summary?: string
  participants?: Participant[]
  projects?: Project[]
  actionItems?: ActionItem[]
  draftMessage?: string
  status: 'processing' | 'pending_approval' | 'completed' | 'sent' | 'error'
  createdAt: Date | string
}

export interface Participant {
  name: string
  contactId?: string
  telegramUsername?: string
  matched: boolean
  matchScore?: number
  originalName?: string
  matchedName?: string
}

export interface Project {
  key: string
  name: string
  id?: string
  matched: boolean
}

export interface ActionItem {
  text: string
  assignee?: string
  priority: 'High' | 'Medium' | 'Low'
}

export interface KeyDecision {
  title: string
  description: string
  impact?: string
}

export interface MeetingProcessingInput {
  transcript?: string
  audioFile?: File
}

export interface MeetingProcessingResponse {
  meeting_id: string
  summary: string
  transcript?: string
  participants: Participant[]
  projects?: Project[]
  action_items: ActionItem[]
  key_decisions?: KeyDecision[]
  insights?: string[]
  next_steps?: string[]
  draft_message?: string
  verification_warnings?: string[]
  requires_approval?: boolean
  status?: string
  message: string
}
