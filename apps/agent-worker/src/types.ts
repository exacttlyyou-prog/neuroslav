/**
 * Общие типы для мульти-агентной системы обработки встреч Notion
 */

export interface MeetingPage {
  id: string;
  url: string;
  title: string;
  status: MeetingStatus;
}

export type MeetingStatus = 'Ready to Process' | 'Processing' | 'Done' | 'Error';

export interface ScraperResult {
  success: boolean;
  content?: string;
  error?: string;
}

export interface AnalystResult {
  success: boolean;
  data?: StructuredMeetingData;
  error?: string;
}

export interface StructuredMeetingData {
  actionItems: ActionItem[];
  keyDecisions: KeyDecision[];
  summary?: string;
}

export interface ActionItem {
  title: string;
  description?: string;
  assignee?: string;
  dueDate?: string;
  priority?: 'High' | 'Medium' | 'Low';
}

export interface KeyDecision {
  title: string;
  description?: string;
  context?: string;
}

export interface WriterResult {
  success: boolean;
  taskIds?: string[];
  error?: string;
}

export interface AgentResult<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface Config {
  notionToken: string;
  openaiApiKey: string;
  notionDbId: string;
  notionTasksDbId: string;
  statusProperty: string;
  pollInterval: number;
  authFilePath: string;
}
