'use client'

import { useState, useEffect } from 'react'
import Settings from '../components/Settings'
import ProgressBar from '../components/ProgressBar'
import CookiesUpload from '../components/CookiesUpload'
import ItemCard from '../components/ItemCard'
import { ClipRequest, VideoRequest, VideoFormat, TextPlacement } from '../types'

// Define this locally for now to match backend Schema
interface VideoItem {
  title: string;
  order: number;
  clips: ClipRequest[];
}

export default function Home() {
  // State for hierarchical list
  const [items, setItems] = useState<VideoItem[]>([])

  const [settings, setSettings] = useState({
    title: 'Amazing Video Compilation',
    font: 'KOMIKAX_.ttf',
    font_size: 36,
    font_color: 'white',
    placement: 'bottom' as TextPlacement,
    music: '',
    format: 'youtube' as VideoFormat
  })
  const [cookiesFile, setCookiesFile] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [backendStatus, setBackendStatus] = useState<'unknown' | 'healthy' | 'unhealthy'>('unknown')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('')
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)

  // -- Item Management --

  const addItem = () => {
    setItems([...items, {
      title: '',
      order: items.length,
      clips: []
    }])
  }

  const removeItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index))
  }

  const updateItemTitle = (index: number, newTitle: string) => {
    const newItems = [...items]
    newItems[index].title = newTitle
    setItems(newItems)
  }

  // -- Clip Management within Items --

  const addClipToItem = (itemIndex: number) => {
    const newItems = [...items]
    newItems[itemIndex].clips.push({
      url: '',
      timestamp: 0,
      keywords: '',
      customText: ''
    } as ClipRequest)
    setItems(newItems)
  }

  const removeClipFromItem = (itemIndex: number, clipIndex: number) => {
    const newItems = [...items]
    newItems[itemIndex].clips = newItems[itemIndex].clips.filter((_, i) => i !== clipIndex)
    setItems(newItems)
  }

  const updateClipInItem = (itemIndex: number, clipIndex: number, field: string, value: any) => {
    const newItems = [...items]
    // @ts-ignore - Dynamic key access
    newItems[itemIndex].clips[clipIndex][field] = value
    setItems(newItems)
  }

  const handleGenerate = async () => {
    // Validate: At least one item, and at least one clip total
    if (items.length === 0) {
      alert('Please add at least one item (Top-X category)')
      return
    }

    const totalClips = items.reduce((acc, item) => acc + item.clips.length, 0)
    if (totalClips === 0) {
      alert('Please add at least one clip to your items')
      return
    }

    // Check validation of individual clips
    for (const item of items) {
      for (const clip of item.clips) {
        if (!clip.url) {
          alert(`Please provide a URL for all clips (Item: ${item.title || 'Untitled'})`)
          return
        }
      }
    }

    setIsProcessing(true)
    setProgress(0)
    setStatus('Starting video generation...')

    try {
      const request = {
        items: items, // Send hierarchical items
        ...settings,
        download_config: cookiesFile ? { cookies_file: cookiesFile } : undefined
      }

      const baseUrl = process.env.NEXT_PUBLIC_API_URL || ''
      const response = await fetch(`${baseUrl}/generate-video`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to start video generation')
      }

      const data = await response.json()
      setTaskId(data.task_id)

      // Start polling for status
      pollStatus(data.task_id)

    } catch (error: any) {
      console.error('Error:', error)
      setStatus(`Error starting video generation: ${error.message}`)
      setIsProcessing(false)
    }
  }

  // Health check for backend service
  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || ''

    const checkHealth = async () => {
      try {
        const res = await fetch(`${baseUrl}/health`)
        if (res.ok) {
          const data = await res.json()
          if (data.status === 'healthy') setBackendStatus('healthy')
          else setBackendStatus('unhealthy')
        } else {
          setBackendStatus('unhealthy')
        }
      } catch (e) {
        setBackendStatus('unhealthy')
      }
    }

    // Initial check
    checkHealth()
    const id = setInterval(checkHealth, 5000)
    return () => clearInterval(id)
  }, [])

  const pollStatus = async (id: string) => {
    const interval = setInterval(async () => {
      try {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || ''
        const response = await fetch(`${baseUrl}/status/${id}`)
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
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold text-gray-900">Top-X Video Generator</h1>
                {/* Backend health indicator */}
                <div className="flex items-center text-sm text-gray-600">
                  <span
                    aria-hidden
                    className={`inline-block w-3 h-3 rounded-full mr-2 ${backendStatus === 'healthy' ? 'bg-green-500' : backendStatus === 'unhealthy' ? 'bg-red-500' : 'bg-gray-300'}`}
                  />
                  <span>{backendStatus === 'healthy' ? 'Backend healthy' : backendStatus === 'unhealthy' ? 'Backend unreachable' : 'Checking backend...'}</span>
                </div>
              </div>
              <p className="text-gray-600 mt-1">
                Create "Top 10" style videos with hierarchical items and clips
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - List of Items */}
          <div className="lg:col-span-2 space-y-6">

            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold text-gray-800">Your List</h2>
              <button
                onClick={addItem}
                className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-semibold shadow-md transition-colors flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add New Item
              </button>
            </div>

            {items.length === 0 ? (
              <div className="text-center py-12 bg-white rounded-xl border-2 border-dashed border-gray-300">
                <p className="text-gray-500 text-lg">Your list is empty.</p>
                <p className="text-gray-400">Click "Add New Item" to start building your Top-X list.</p>
              </div>
            ) : (
              <div className="space-y-6">
                {items.map((item, index) => (
                  <ItemCard
                    key={index}
                    title={item.title}
                    index={index}
                    clips={item.clips as any} // Local interface match
                    onUpdateTitle={(val: string) => updateItemTitle(index, val)}
                    onAddClip={() => addClipToItem(index)}
                    onRemoveClip={(clipIdx: number) => removeClipFromItem(index, clipIdx)}
                    onUpdateClip={(clipIdx: number, field: string, val: any) => updateClipInItem(index, clipIdx, field, val)}
                    onRemoveItem={() => removeItem(index)}
                  />
                ))}
              </div>
            )}

          </div>

          {/* Right Column - Settings and Generate */}
          <div className="space-y-6">
            <div className="sticky top-8 space-y-6">
              <Settings
                settings={settings}
                onSettingsChange={setSettings}
              />

              <CookiesUpload
                onCookiesUploaded={setCookiesFile}
                onCookiesCleared={() => setCookiesFile(null)}
                uploadedCookiesFile={cookiesFile || undefined}
              />

              <div className="card">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">
                  Generate Video
                </h3>

                <button
                  onClick={handleGenerate}
                  disabled={isProcessing || items.length === 0}
                  className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isProcessing ? 'Generating...' : 'Generate Video'}
                </button>

                {items.length === 0 && (
                  <p className="text-sm text-gray-500 mt-2 text-center">
                    List is empty
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
        </div>
      </main>
    </div>
  )
}
