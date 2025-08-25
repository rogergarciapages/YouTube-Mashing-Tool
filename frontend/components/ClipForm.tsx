'use client'

import { useState } from 'react'
import { Plus, Youtube } from 'lucide-react'
import { ClipRequest } from '../types'

interface ClipFormProps {
  onAddClip: (clip: ClipRequest) => void
}

export default function ClipForm({ onAddClip }: ClipFormProps) {
  const [formData, setFormData] = useState({
    url: '',
    keywords: '',
    custom_text: ''
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {}

    if (!formData.url.trim()) {
      newErrors.url = 'YouTube URL is required'
    } else if (!isValidYouTubeUrl(formData.url)) {
      newErrors.url = 'Please enter a valid YouTube URL'
    } else {
      // Check if URL contains a timestamp
      const timestamp = extractTimestampFromUrl(formData.url)
      if (timestamp === null) {
        newErrors.url = 'YouTube URL must contain a timestamp (e.g., ?t=120 or &t=120)'
      }
    }

    if (!formData.keywords.trim() && !formData.custom_text.trim()) {
      newErrors.keywords = 'Either keywords or custom text is required'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const isValidYouTubeUrl = (url: string): boolean => {
    const youtubeRegex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+/
    return youtubeRegex.test(url)
  }

  const extractTimestampFromUrl = (url: string): number | null => {
    try {
      const urlObj = new URL(url)
      const searchParams = urlObj.searchParams
      
      // Check for 't' parameter (timestamp in seconds)
      const timestamp = searchParams.get('t')
      if (timestamp) {
        const seconds = parseInt(timestamp)
        return isNaN(seconds) || seconds < 0 ? null : seconds
      }
      
      // Check for 'si' parameter which sometimes contains timestamp
      const si = searchParams.get('si')
      if (si) {
        // Extract timestamp from si parameter if it exists
        const match = si.match(/t=(\d+)/)
        if (match) {
          const seconds = parseInt(match[1])
          return isNaN(seconds) || seconds < 0 ? null : seconds
        }
      }
      
      return null
    } catch {
      return null
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm()) {
      return
    }

    const timestamp = extractTimestampFromUrl(formData.url)
    if (timestamp === null) {
      setErrors({ url: 'Failed to extract timestamp from URL' })
      return
    }

    const clip: ClipRequest = {
      url: formData.url.trim(),
      timestamp: timestamp,
      keywords: formData.keywords.trim() || undefined,
      custom_text: formData.custom_text.trim() || undefined
    }

    onAddClip(clip)
    
    // Reset form
    setFormData({
      url: '',
      keywords: '',
      custom_text: ''
    })
    setErrors({})
  }

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: '' }))
    }
  }

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-4">
        <Plus className="w-5 h-5 text-primary-600" />
        <h3 className="text-lg font-semibold text-gray-900">
          Add New Clip
        </h3>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* YouTube URL */}
        <div>
          <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
            YouTube URL *
          </label>
          <div className="relative">
            <Youtube className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="url"
              id="url"
              value={formData.url}
              onChange={(e) => handleInputChange('url', e.target.value)}
              placeholder="https://youtu.be/example or https://youtube.com/watch?v=example"
              className={`input-field pl-10 ${errors.url ? 'border-red-300 focus:ring-red-500' : ''}`}
            />
          </div>
          {errors.url && (
            <p className="text-sm text-red-600 mt-1">{errors.url}</p>
          )}
        </div>

        {/* Timestamp Info */}
        <div className="text-xs text-gray-500 bg-blue-50 p-2 rounded border border-blue-200">
          <strong>Timestamp:</strong> The start time will be automatically extracted from your YouTube URL (e.g., ?t=120 means start at 2 minutes)
        </div>

        {/* Keywords */}
        <div>
          <label htmlFor="keywords" className="block text-sm font-medium text-gray-700 mb-1">
            Keywords (for AI summary)
          </label>
          <input
            type="text"
            id="keywords"
            value={formData.keywords}
            onChange={(e) => handleInputChange('keywords', e.target.value)}
            placeholder="Rolex, Submariner, diving watch"
            className={`input-field ${errors.keywords ? 'border-red-300 focus:ring-red-500' : ''}`}
          />
          {errors.keywords && (
            <p className="text-sm text-red-600 mt-1">{errors.keywords}</p>
          )}
          <p className="text-xs text-gray-500 mt-1">
            AI will generate a summary based on these keywords
          </p>
        </div>

        {/* Custom Text */}
        <div>
          <label htmlFor="custom_text" className="block text-sm font-medium text-gray-700 mb-1">
            Custom Text (override AI summary)
          </label>
          <input
            type="text"
            id="custom_text"
            value={formData.custom_text}
            onChange={(e) => handleInputChange('custom_text', e.target.value)}
            placeholder="Your custom text here"
            maxLength={60}
            className="input-field"
          />
          <p className="text-xs text-gray-500 mt-1">
            Optional: Override AI summary with your own text (max 60 characters)
          </p>
        </div>

        <button
          type="submit"
          className="btn-primary w-full"
        >
          Add Clip
        </button>
      </form>
    </div>
  )
}
