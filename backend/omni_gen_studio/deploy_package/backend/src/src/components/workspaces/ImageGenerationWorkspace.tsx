import React, { useState } from 'react'
import { Upload, Download, RefreshCw, Eye, Grid3X3 } from 'lucide-react'
import { Button } from '../ui/button'
import { useGenerationContext } from '../../contexts/GenerationContext'

export const ImageGenerationWorkspace: React.FC = () => {
  const { status, progress, config, lastResult } = useGenerationContext()
  const [viewMode, setViewMode] = useState<'single' | 'grid'>('single')
  const [showGrid, setShowGrid] = useState(false)

  // Mock results
  const mockResults = [
    { id: '1', url: '/api/placeholder/512/512', prompt: 'Beautiful landscape' },
    { id: '2', url: '/api/placeholder/512/512', prompt: 'Futuristic city' },
    { id: '3', url: '/api/placeholder/512/512', prompt: 'Fantasy castle' }
  ]

  return (
    <div className="h-full flex flex-col bg-neutral-900">
      {/* Toolbar */}
      <div className="h-12 bg-primary-800 border-b border-primary-600 flex items-center justify-between px-4">
        <div className="flex items-center space-x-2">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Upload className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Download className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>

        <div className="flex items-center space-x-2">
          <Button
            variant={viewMode === 'single' ? 'default' : 'ghost'}
            size="icon"
            className="h-8 w-8"
            onClick={() => setViewMode('single')}
          >
            <Eye className="w-4 h-4" />
          </Button>
          <Button
            variant={viewMode === 'grid' ? 'default' : 'ghost'}
            size="icon"
            className="h-8 w-8"
            onClick={() => setViewMode('grid')}
          >
            <Grid3X3 className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div className="flex-1 relative overflow-hidden">
        {status === 'idle' && !lastResult && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div className="w-32 h-32 bg-primary-800 rounded-lg mx-auto mb-4 flex items-center justify-center">
                <Eye className="w-16 h-16 text-neutral-400" />
              </div>
              <h3 className="text-lg font-semibold text-neutral-100 mb-2">
                图像生成工作区
              </h3>
              <p className="text-neutral-400 mb-4">
                在右侧参数面板中配置生成参数，然后点击生成
              </p>
              <div className="text-xs text-neutral-500 space-y-1">
                <div>支持文生图、图生图、图像修复</div>
                <div>实时预览生成进度</div>
                <div>批量生成和网格视图</div>
              </div>
            </div>
          </div>
        )}

        {status === 'generating' && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div className="w-16 h-16 border-4 border-accent-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
              <h3 className="text-lg font-semibold text-neutral-100 mb-2">
                正在生成图像...
              </h3>
              <p className="text-neutral-400 mb-2">
                推理步数: {config.steps} | CFG: {config.guidanceScale}
              </p>
              <div className="w-64 bg-primary-700 rounded-full h-2 mx-auto">
                <div 
                  className="bg-accent-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
              <p className="text-sm text-neutral-400 mt-2">
                {progress.toFixed(1)}% 完成
              </p>
            </div>
          </div>
        )}

        {status === 'completed' && lastResult && (
          <div className="h-full p-4">
            {viewMode === 'single' ? (
              <div className="h-full flex items-center justify-center">
                <div className="relative max-w-full max-h-full">
                  <img 
                    src={lastResult} 
                    alt="Generated" 
                    className="max-w-full max-h-full object-contain rounded-lg shadow-floating"
                  />
                  <div className="absolute bottom-4 left-4 bg-black/70 backdrop-blur-sm rounded-sm px-3 py-1">
                    <p className="text-sm text-neutral-100">{config.prompt}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-4 p-4">
                {mockResults.map((result) => (
                  <div key={result.id} className="relative group">
                    <img 
                      src={result.url} 
                      alt={result.prompt}
                      className="w-full aspect-square object-cover rounded-lg cursor-pointer hover:opacity-80 transition-opacity"
                    />
                    <div className="absolute inset-0 bg-black/70 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center">
                      <Button size="sm" variant="secondary">
                        查看详情
                      </Button>
                    </div>
                    <div className="absolute bottom-2 left-2 bg-black/70 backdrop-blur-sm rounded-sm px-2 py-1">
                      <p className="text-xs text-neutral-100 truncate max-w-[200px]">
                        {result.prompt}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Generation Info Overlay */}
        {status === 'completed' && (
          <div className="absolute top-4 right-4 bg-semantic-success/20 border border-semantic-success/30 rounded-sm px-3 py-2">
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 bg-semantic-success rounded-full"></div>
              <span className="text-sm text-semantic-success">生成完成</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}