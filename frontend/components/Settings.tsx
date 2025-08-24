'use client'

import { Settings as SettingsIcon, Type, Palette, Music, Monitor } from 'lucide-react'
import { Settings as SettingsType, VideoFormat, TextPlacement } from '../types'

interface SettingsProps {
  settings: SettingsType
  onSettingsChange: (settings: SettingsType) => void
}

export default function Settings({ settings, onSettingsChange }: SettingsProps) {
  const handleChange = (field: keyof SettingsType, value: any) => {
    onSettingsChange({
      ...settings,
      [field]: value
    })
  }

  const fontOptions = [
    'Arial', 'Helvetica', 'Times New Roman', 'Georgia', 'Verdana',
    'Courier New', 'Impact', 'Comic Sans MS', 'Tahoma', 'Trebuchet MS'
  ]

  const colorOptions = [
    { name: 'White', value: 'white' },
    { name: 'Black', value: 'black' },
    { name: 'Red', value: 'red' },
    { name: 'Blue', value: 'blue' },
    { name: 'Green', value: 'green' },
    { name: 'Yellow', value: 'yellow' },
    { name: 'Orange', value: 'orange' },
    { name: 'Purple', value: 'purple' }
  ]

  const formatOptions: { value: VideoFormat; label: string; description: string }[] = [
    {
      value: 'youtube',
      label: 'YouTube (16:9)',
      description: '1920x1080 - Standard landscape format'
    },
    {
      value: 'shorts',
      label: 'YouTube Shorts (9:16)',
      description: '1080x1920 - Vertical mobile format'
    },
    {
      value: 'instagram',
      label: 'Instagram (1:1)',
      description: '1080x1080 - Square format'
    }
  ]

  const placementOptions: { value: TextPlacement; label: string }[] = [
    { value: 'top', label: 'Top' },
    { value: 'center', label: 'Center' },
    { value: 'bottom', label: 'Bottom' }
  ]

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-4">
        <SettingsIcon className="w-5 h-5 text-primary-600" />
        <h3 className="text-lg font-semibold text-gray-900">
          Video Settings
        </h3>
      </div>

      <div className="space-y-4">
        {/* Font Settings */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <Type className="w-4 h-4 inline mr-2" />
            Font Settings
          </label>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Font Family</label>
              <select
                value={settings.font}
                onChange={(e) => handleChange('font', e.target.value)}
                className="input-field text-sm"
              >
                {fontOptions.map(font => (
                  <option key={font} value={font}>{font}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-gray-600 mb-1">Font Size</label>
              <input
                type="range"
                min="12"
                max="120"
                value={settings.font_size}
                onChange={(e) => handleChange('font_size', parseInt(e.target.value))}
                className="w-full"
              />
              <div className="text-xs text-gray-500 text-center">
                {settings.font_size}px
              </div>
            </div>
          </div>
        </div>

        {/* Color and Placement */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <Palette className="w-4 h-4 inline mr-2" />
            Text Appearance
          </label>
          
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">Text Color</label>
              <select
                value={settings.font_color}
                onChange={(e) => handleChange('font_color', e.target.value)}
                className="input-field text-sm"
              >
                {colorOptions.map(color => (
                  <option key={color.value} value={color.value}>{color.name}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-gray-600 mb-1">Placement</label>
              <select
                value={settings.placement}
                onChange={(e) => handleChange('placement', e.target.value as TextPlacement)}
                className="input-field text-sm"
              >
                {placementOptions.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Output Format */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <Monitor className="w-4 h-4 inline mr-2" />
            Output Format
          </label>
          
          <div className="space-y-2">
            {formatOptions.map(option => (
              <label key={option.value} className="flex items-start gap-3 cursor-pointer">
                <input
                  type="radio"
                  name="format"
                  value={option.value}
                  checked={settings.format === option.value}
                  onChange={(e) => handleChange('format', e.target.value as VideoFormat)}
                  className="mt-1"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900">
                    {option.label}
                  </div>
                  <div className="text-xs text-gray-500">
                    {option.description}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Background Music */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <Music className="w-4 h-4 inline mr-2" />
            Background Music
          </label>
          
          <div className="text-xs text-gray-500 mb-2">
            Upload an MP3 file to add background music (optional)
          </div>
          
          <input
            type="file"
            accept=".mp3,.wav,.m4a"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) {
                handleChange('music', file.name)
              }
            }}
            className="input-field text-sm"
          />
          
          {settings.music && (
            <div className="mt-2 text-sm text-primary-600">
              Selected: {settings.music}
            </div>
          )}
        </div>

        {/* Preview */}
        <div className="pt-4 border-t border-gray-200">
          <div className="text-sm font-medium text-gray-700 mb-2">Text Preview</div>
          <div 
            className="p-3 rounded border-2 border-dashed border-gray-300 text-center"
            style={{
              fontFamily: settings.font,
              fontSize: `${settings.font_size}px`,
              color: settings.font_color,
              backgroundColor: '#f3f4f6'
            }}
          >
            Sample Text
          </div>
          <div className="text-xs text-gray-500 mt-1 text-center">
            This shows how your text will appear on the video
          </div>
        </div>
      </div>
    </div>
  )
}
