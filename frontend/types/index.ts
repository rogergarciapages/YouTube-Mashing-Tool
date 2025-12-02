export interface ClipRequest {
  url: string
  timestamp: number
  keywords?: string
  custom_text?: string
}

export interface DownloadConfig {
  cookies_file?: string
  use_geo_bypass?: boolean
  retries?: number
}

export interface VideoRequest {
  clips: ClipRequest[]
  title: string
  font: string
  font_size: number
  font_color: string
  placement: TextPlacement
  music?: string
  format: VideoFormat
  download_config?: DownloadConfig
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
  title: string
  font: string
  font_size: number
  font_color: string
  placement: TextPlacement
  music: string
  format: VideoFormat
}
