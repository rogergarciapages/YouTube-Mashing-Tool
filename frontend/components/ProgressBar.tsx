'use client'

import { CheckCircle, AlertCircle, Clock } from 'lucide-react'

interface ProgressBarProps {
  progress: number
  status: string
}

export default function ProgressBar({ progress, status }: ProgressBarProps) {
  const getStatusIcon = () => {
    if (progress === 100) {
      return <CheckCircle className="w-5 h-5 text-green-600" />
    } else if (progress === 0) {
      return <Clock className="w-5 h-5 text-blue-600" />
    } else {
      return <Clock className="w-5 h-5 text-blue-600 animate-spin" />
    }
  }

  const getStatusColor = () => {
    if (progress === 100) {
      return 'text-green-600'
    } else if (progress === 0) {
      return 'text-blue-600'
    } else {
      return 'text-blue-600'
    }
  }

  const getProgressColor = () => {
    if (progress === 100) {
      return 'bg-green-600'
    } else {
      return 'bg-blue-600'
    }
  }

  return (
    <div className="space-y-3">
      {/* Status Icon and Text */}
      <div className="flex items-center gap-2">
        {getStatusIcon()}
        <span className={`text-sm font-medium ${getStatusColor()}`}>
          {status}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all duration-500 ease-out ${getProgressColor()}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Progress Percentage */}
      <div className="flex justify-between text-xs text-gray-500">
        <span>Processing...</span>
        <span>{progress}%</span>
      </div>

      {/* Status Messages */}
      {progress < 100 && (
        <div className="text-xs text-gray-600 bg-blue-50 p-3 rounded-lg">
          <div className="font-medium mb-1">Current Step:</div>
          <div>{status}</div>
          {progress > 0 && (
            <div className="mt-2">
              <div className="text-blue-600">
                This may take a few minutes depending on the number of clips and video length.
              </div>
            </div>
          )}
        </div>
      )}

      {progress === 100 && (
        <div className="text-xs text-green-600 bg-green-50 p-3 rounded-lg">
          <div className="font-medium">Video compilation completed successfully!</div>
          <div className="mt-1">Your video is ready for download.</div>
        </div>
      )}
    </div>
  )
}
