import React from 'react'
import { Box, RotateCw, ZoomIn, ZoomOut } from 'lucide-react'
import { Button } from '../ui/button'

export const ThreeDGenerationWorkspace: React.FC = () => {
  return (
    <div className="h-full flex flex-col bg-neutral-900">
      {/* 3D Controls */}
      <div className="h-12 bg-primary-800 border-b border-primary-600 flex items-center justify-between px-4">
        <div className="flex items-center space-x-2">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <RotateCw className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ZoomIn className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ZoomOut className="w-4 h-4" />
          </Button>
        </div>
        <div className="text-sm text-neutral-400">
          支持 Hunyuan3D、Trellis-2 模型
        </div>
      </div>

      {/* 3D Viewer */}
      <div className="flex-1 flex items-center justify-center relative">
        <div className="text-center">
          <div className="w-32 h-32 bg-primary-800 rounded-lg mx-auto mb-4 flex items-center justify-center">
            <Box className="w-16 h-16 text-neutral-400" />
          </div>
          <h3 className="text-lg font-semibold text-neutral-100 mb-2">
            3D 生成工作区
          </h3>
          <p className="text-neutral-400">
            从图像或文本生成 3D 模型，支持 OBJ、GLB 格式导出
          </p>
        </div>
        
        {/* 3D Viewer Placeholder */}
        <div className="absolute inset-4 border-2 border-dashed border-primary-600 rounded-lg flex items-center justify-center">
          <div className="text-neutral-500 text-sm">
            3D 预览器将在此显示
          </div>
        </div>
      </div>
    </div>
  )
}