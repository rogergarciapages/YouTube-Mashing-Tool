'use client'

import { useState } from 'react'
import { Upload, X } from 'lucide-react'

interface CookiesUploadProps {
  onCookiesUploaded: (cookiesPath: string) => void
  onCookiesCleared: () => void
  uploadedCookiesFile?: string
}

export default function CookiesUpload({
  onCookiesUploaded,
  onCookiesCleared,
  uploadedCookiesFile
}: CookiesUploadProps) {
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState('')

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file
    if (!file.name.includes('cookies')) {
      setError('Please upload a cookies.txt file')
      return
    }

    if (file.size > 1024 * 1024) { // 1MB limit
      setError('Cookies file must be smaller than 1MB')
      return
    }

    setIsUploading(true)
    setError('')

    try {
      const formData = new FormData()
      formData.append('file', file)

      const baseUrl = process.env.NEXT_PUBLIC_API_URL || ''
      const response = await fetch(`${baseUrl}/upload-cookies`, {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        throw new Error('Failed to upload cookies file')
      }

      const data = await response.json()
      onCookiesUploaded(data.cookies_file)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error uploading cookies file')
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="card bg-amber-50 border-amber-200">
      <div className="flex items-start gap-3">
        <Upload className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-amber-900 mb-2">
            Browser Cookies (Optional)
          </h3>
          <p className="text-xs text-amber-800 mb-3">
            If you're downloading age-restricted or region-locked videos, upload your browser cookies.txt file to authenticate with YouTube.
          </p>

          {uploadedCookiesFile ? (
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-mono bg-white px-2 py-1 rounded border border-amber-200 text-amber-900 flex-1 truncate">
                {uploadedCookiesFile.split('/').pop()}
              </span>
              <button
                onClick={() => onCookiesCleared()}
                className="p-1 hover:bg-amber-100 rounded transition"
                title="Remove cookies"
              >
                <X className="w-4 h-4 text-amber-600" />
              </button>
            </div>
          ) : (
            <label className="block">
              <input
                type="file"
                accept=".txt"
                onChange={handleFileUpload}
                disabled={isUploading}
                className="hidden"
              />
              <span className="inline-block px-3 py-2 bg-amber-600 text-white text-xs font-medium rounded hover:bg-amber-700 cursor-pointer transition disabled:opacity-50">
                {isUploading ? 'Uploading...' : 'Choose cookies.txt file'}
              </span>
            </label>
          )}

          {error && (
            <p className="text-xs text-red-600 mt-2">{error}</p>
          )}

          <p className="text-xs text-amber-700 mt-2">
            <strong>How to export cookies:</strong> Use browser extension like "EditThisCookie" or
            "Open source cookies.txt" to export from youtube.com as cookies.txt
          </p>
        </div>
      </div>
    </div>
  )
}
