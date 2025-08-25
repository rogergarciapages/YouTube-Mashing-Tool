'use client'

import { useState } from 'react'
import ClipForm from '../components/ClipForm'
import ClipList from '../components/ClipList'
import Settings from '../components/Settings'
import ProgressBar from '../components/ProgressBar'
import { ClipRequest, VideoRequest, VideoFormat, TextPlacement } from '../types'

export default function Home() {
  const [clips, setClips] = useState<ClipRequest[]>([])
  const [settings, setSettings] = useState({
    font: 'KOMIKAX_.ttf',
    font_size: 36,
    font_color: 'white',
    placement: 'bottom' as TextPlacement,
    music: '',
    format: 'youtube' as VideoFormat
  })
  const [isProcessing, setIsProcessing] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('')
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)

  const addClip = (clip: ClipRequest) => {
    setClips([...clips, clip])
  }

  const removeClip = (index: number) => {
    setClips(clips.filter((_, i) => i !== index))
  }

  const updateClip = (index: number, clip: ClipRequest) => {
    const newClips = [...clips]
    newClips[index] = clip
    setClips(newClips)
  }

  const handleGenerate = async () => {
    if (clips.length === 0) {
      alert('Please add at least one clip')
      return
    }

    setIsProcessing(true)
    setProgress(0)
    setStatus('Starting video generation...')

    try {
      const request: VideoRequest = {
        clips,
        ...settings
      }

      const response = await fetch('/api/generate-video', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      })

      if (!response.ok) {
        throw new Error('Failed to start video generation')
      }

      const data = await response.json()
      setTaskId(data.task_id)
      
      // Start polling for status
      pollStatus(data.task_id)
      
    } catch (error) {
      console.error('Error:', error)
      setStatus('Error starting video generation')
      setIsProcessing(false)
    }
  }

  const pollStatus = async (id: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/status/${id}`)
        if (response.ok) {
          const statusData = await response.json()
          
          setProgress(statusData.progress)
          setStatus(statusData.message)
          
          if (statusData.status === 'completed') {
            setDownloadUrl(statusData.download_url)
            setIsProcessing(false)
            clearInterval(interval)
          } else if (statusData.status === 'error') {
            setStatus(`Error: ${statusData.error}`)
            setIsProcessing(false)
            clearInterval(interval)
          }
        }
      } catch (error) {
        console.error('Error polling status:', error)
        setStatus('Error checking status')
        setIsProcessing(false)
        clearInterval(interval)
      }
    }, 2000) // Poll every 2 seconds
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                YouTube Clip Compilation Tool
              </h1>
              <p className="text-gray-600 mt-1">
                Create amazing video compilations with AI summaries
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - Clip Form and List */}
          <div className="lg:col-span-2 space-y-6">
            <ClipForm onAddClip={addClip} />
            <ClipList 
              clips={clips} 
              onRemoveClip={removeClip}
              onUpdateClip={updateClip}
            />
          </div>

          {/* Right Column - Settings and Generate */}
          <div className="space-y-6">
            <Settings 
              settings={settings} 
              onSettingsChange={setSettings}
            />
            
            <div className="card">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                Generate Video
              </h3>
              
              <button
                onClick={handleGenerate}
                disabled={isProcessing || clips.length === 0}
                className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isProcessing ? 'Generating...' : 'Generate Video'}
              </button>
              
              {clips.length === 0 && (
                <p className="text-sm text-gray-500 mt-2 text-center">
                  Add at least one clip to generate a video
                </p>
              )}
            </div>

            {/* Progress and Status */}
            {isProcessing && (
              <div className="card">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Processing Status
                </h3>
                <ProgressBar progress={progress} status={status} />
              </div>
            )}

            {/* Download Link */}
            {downloadUrl && (
              <div className="card bg-green-50 border-green-200">
                <h3 className="text-lg font-semibold text-green-900 mb-4">
                  Video Ready!
                </h3>
                <a
                  href={downloadUrl}
                  className="btn-primary w-full text-center"
                  download
                >
                  Download Video
                </a>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
