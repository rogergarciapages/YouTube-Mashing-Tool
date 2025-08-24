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
    timestamp: '',
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
    }

    if (!formData.timestamp.trim()) {
      newErrors.timestamp = 'Timestamp is required'
    } else {
      const timestamp = parseInt(formData.timestamp)
      if (isNaN(timestamp) || timestamp < 0) {
        newErrors.timestamp = 'Timestamp must be a positive number'
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm()) {
      return
    }

    const clip: ClipRequest = {
      url: formData.url.trim(),
      timestamp: parseInt(formData.timestamp),
      keywords: formData.keywords.trim() || undefined,
      custom_text: formData.custom_text.trim() || undefined
    }

    onAddClip(clip)
    
    // Reset form
    setFormData({
      url: '',
      timestamp: '',
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

        {/* Timestamp */}
        <div>
          <label htmlFor="timestamp" className="block text-sm font-medium text-gray-700 mb-1">
            Start Time (seconds) *
          </label>
          <input
            type="number"
            id="timestamp"
            value={formData.timestamp}
            onChange={(e) => handleInputChange('timestamp', e.target.value)}
            placeholder="45"
            min="0"
            className={`input-field ${errors.timestamp ? 'border-red-300 focus:ring-red-500' : ''}`}
          />
          {errors.timestamp && (
            <p className="text-sm text-red-600 mt-1">{errors.timestamp}</p>
          )}
          <p className="text-xs text-gray-500 mt-1">
            Enter the time in seconds when you want the clip to start
          </p>
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
