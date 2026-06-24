import React from 'react'
import { Video, Play, Pause } from 'lucide-react'
import { Button } from '../ui/button'

export const VideoGenerationWorkspace: React.FC = () => {
  return (
    <div className="h-full flex flex-col bg-neutral-900">
      {/* Video Controls */}
      <div className="h-12 bg-primary-800 border-b border-primary-600 flex items-center justify-between px-4">
        <div className="flex items-center space-x-2">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Play className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Pause className="w-4 h-4" />
          </Button>
        </div>
        <div className="text-sm text-neutral-400">
          支持文生视频、图生视频
        </div>
      </div>

      {/* Video Preview Area */}
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-32 h-32 bg-primary-800 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <Video className="w-16 h-16 text-neutral-400" />
          </div>
          <h3 className="text-lg font-semibold text-neutral-100 mb-2">
            视频生成工作区
          </h3>
          <p className="text-neutral-400">
            支持 Wan 2.2、LTX-2 等视频生成模型
          </p>
        </div>
      </div>
    </div>
  )
}