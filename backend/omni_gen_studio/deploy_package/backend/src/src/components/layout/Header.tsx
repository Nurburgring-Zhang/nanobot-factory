import React from 'react'
import { Settings, Download, Upload, History, Zap } from 'lucide-react'
import { Button } from '../ui/button'

interface HeaderProps {
  parameterPanelOpen: boolean
  setParameterPanelOpen: (open: boolean) => void
}

export const Header: React.FC<HeaderProps> = ({ parameterPanelOpen, setParameterPanelOpen }) => {
  return (
    <header className="h-12 bg-primary-800 border-b border-primary-600 flex items-center justify-between px-4">
      {/* Logo and Title */}
      <div className="flex items-center space-x-3">
        <div className="w-8 h-8 bg-accent-500 rounded-md flex items-center justify-center">
          <Zap className="w-5 h-5 text-neutral-900" />
        </div>
        <h1 className="text-lg font-semibold text-neutral-100">General AIGC Enhanced</h1>
        <span className="text-xs text-neutral-400 bg-primary-700 px-2 py-1 rounded-sm">v7.0</span>
      </div>

      {/* Status Indicators */}
      <div className="flex items-center space-x-4">
        {/* GPU Status */}
        <div className="flex items-center space-x-2 text-xs">
          <div className="w-2 h-2 bg-semantic-success rounded-full animate-pulse"></div>
          <span className="text-neutral-400">GPU Ready</span>
        </div>

        {/* Queue Status */}
        <div className="flex items-center space-x-2 text-xs">
          <History className="w-4 h-4 text-neutral-400" />
          <span className="text-neutral-400">0 in queue</span>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center space-x-2">
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Upload className="w-4 h-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Download className="w-4 h-4" />
        </Button>
        <Button 
          variant="ghost" 
          size="icon" 
          className="h-8 w-8"
          onClick={() => setParameterPanelOpen(!parameterPanelOpen)}
        >
          <Settings className="w-4 h-4" />
        </Button>
      </div>
    </header>
  )
}