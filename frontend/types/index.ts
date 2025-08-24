export interface ClipRequest {
  url: string
  timestamp: number
  keywords?: string
  custom_text?: string
}

export interface VideoRequest {
  clips: ClipRequest[]
  font: string
  font_size: number
  font_color: string
  placement: TextPlacement
  music?: string
  format: VideoFormat
}

export interface VideoResponse {
  task_id: string
  status: string
  message: string
  download_url?: string
}

export interface ProcessingStatus {
  task_id: string
  status: string
  progress: number
  message: string
  download_url?: string
  error?: string
}

export type VideoFormat = 'youtube' | 'shorts' | 'instagram'
export type TextPlacement = 'top' | 'center' | 'bottom'

export interface Settings {
  font: string
  font_size: number
  font_color: string
  placement: TextPlacement
  music: string
  format: VideoFormat
}
