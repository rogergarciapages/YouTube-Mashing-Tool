'use client'

import { useState } from 'react'
import { Trash2, Edit, Youtube, Clock, FileText } from 'lucide-react'
import { ClipRequest } from '../types'

interface ClipListProps {
  clips: ClipRequest[]
  onRemoveClip: (index: number) => void
  onUpdateClip: (index: number, clip: ClipRequest) => void
}

export default function ClipList({ clips, onRemoveClip, onUpdateClip }: ClipListProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<ClipRequest>({
    url: '',
    timestamp: 0,
    keywords: '',
    custom_text: ''
  })

  const startEditing = (index: number) => {
    setEditingIndex(index)
    setEditForm(clips[index])
  }

  const cancelEditing = () => {
    setEditingIndex(null)
    setEditForm({
      url: '',
      timestamp: 0,
      keywords: '',
      custom_text: ''
    })
  }

  const saveEdit = () => {
    if (editingIndex !== null) {
      onUpdateClip(editingIndex, editForm)
      setEditingIndex(null)
    }
  }

  const formatTimestamp = (seconds: number): string => {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  const getVideoId = (url: string): string => {
    const regex = /(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/
    const match = url.match(regex)
    return match ? match[1] : ''
  }

  if (clips.length === 0) {
    return (
      <div className="card text-center py-12">
        <Youtube className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">No clips added yet</h3>
        <p className="text-gray-500">
          Use the form above to add your first YouTube clip
        </p>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          Clips ({clips.length})
        </h3>
        <span className="text-sm text-gray-500">
          {clips.length}/20 clips
        </span>
      </div>

      <div className="space-y-3">
        {clips.map((clip, index) => (
          <div key={index} className="border border-gray-200 rounded-lg p-4">
            {editingIndex === index ? (
              // Edit Form
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    YouTube URL
                  </label>
                  <input
                    type="url"
                    value={editForm.url}
                    onChange={(e) => setEditForm(prev => ({ ...prev, url: e.target.value }))}
                    className="input-field"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Timestamp (seconds)
                  </label>
                  <input
                    type="number"
                    value={editForm.timestamp}
                    onChange={(e) => setEditForm(prev => ({ ...prev, timestamp: parseInt(e.target.value) || 0 }))}
                    className="input-field"
                    min="0"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Keywords
                  </label>
                  <input
                    type="text"
                    value={editForm.keywords || ''}
                    onChange={(e) => setEditForm(prev => ({ ...prev, keywords: e.target.value }))}
                    className="input-field"
                    placeholder="Keywords for AI summary"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Custom Text
                  </label>
                  <input
                    type="text"
                    value={editForm.custom_text || ''}
                    onChange={(e) => setEditForm(prev => ({ ...prev, custom_text: e.target.value }))}
                    className="input-field"
                    placeholder="Custom text (optional)"
                    maxLength={60}
                  />
                </div>
                
                <div className="flex gap-2">
                  <button
                    onClick={saveEdit}
                    className="btn-primary flex-1"
                  >
                    Save
                  </button>
                  <button
                    onClick={cancelEditing}
                    className="btn-secondary flex-1"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              // Display Mode
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Youtube className="w-4 h-4 text-red-600" />
                    <span className="text-sm font-medium text-gray-900">
                      Clip {index + 1}
                    </span>
                    <span className="text-xs text-gray-500">
                      {getVideoId(clip.url)}
                    </span>
                  </div>
                  
                  <div className="flex items-center gap-4 text-sm text-gray-600">
                    <div className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      {formatTimestamp(clip.timestamp)}
                    </div>
                    
                    {clip.keywords && (
                      <div className="flex items-center gap-1">
                        <FileText className="w-4 h-4" />
                        {clip.keywords}
                      </div>
                    )}
                    
                    {clip.custom_text && (
                      <div className="text-primary-600 font-medium">
                        "{clip.custom_text}"
                      </div>
                    )}
                  </div>
                </div>
                
                <div className="flex gap-2">
                  <button
                    onClick={() => startEditing(index)}
                    className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
                    title="Edit clip"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                  
                  <button
                    onClick={() => onRemoveClip(index)}
                    className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                    title="Remove clip"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
