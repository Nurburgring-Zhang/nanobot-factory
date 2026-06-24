import React from 'react'
import { Edit3, Brush, Eraser, Undo, Redo } from 'lucide-react'
import { Button } from '../ui/button'

export const ImageEditingWorkspace: React.FC = () => {
  return (
    <div className="h-full flex flex-col bg-neutral-900">
      {/* Toolbar */}
      <div className="h-12 bg-primary-800 border-b border-primary-600 flex items-center justify-between px-4">
        <div className="flex items-center space-x-2">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Edit3 className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Brush className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Eraser className="w-4 h-4" />
          </Button>
          <div className="w-px h-6 bg-primary-600 mx-2"></div>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Undo className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Redo className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Canvas Area */}
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-32 h-32 bg-primary-800 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <Edit3 className="w-16 h-16 text-neutral-400" />
          </div>
          <h3 className="text-lg font-semibold text-neutral-100 mb-2">
            图像编辑工作区
          </h3>
          <p className="text-neutral-400">
            上传图像进行编辑，支持局部修复、画布扩展等功能
          </p>
        </div>
      </div>
    </div>
  )
}