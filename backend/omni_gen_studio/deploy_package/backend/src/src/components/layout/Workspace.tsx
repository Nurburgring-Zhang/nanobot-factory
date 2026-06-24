import React, { useState, useEffect } from 'react'
import { 
  Play, 
  Pause, 
  RotateCcw, 
  Save, 
  Grid, 
  Maximize2,
  RefreshCw,
  Download,
  XCircle,
  CheckCircle,
  Clock,
  History,
  Trash2
} from 'lucide-react'
import { Button } from '../ui/button'
import { ImageGenerationWorkspace } from '../workspaces/ImageGenerationWorkspace'
import { ImageEditingWorkspace } from '../workspaces/ImageEditingWorkspace'
import { VideoGenerationWorkspace } from '../workspaces/VideoGenerationWorkspace'
import { ThreeDGenerationWorkspace } from '../workspaces/ThreeDGenerationWorkspace'
import { useGenerationContext } from '../../contexts/GenerationContext'
import { ModuleType } from '../../contexts/ModuleContext'
import { GenerationService, GenerationTask } from '../../services/api'

interface WorkspaceProps {
  currentModule: ModuleType
}

export const Workspace: React.FC<WorkspaceProps> = ({ currentModule }) => {
  const { status, progress, setStatus } = useGenerationContext()
  const [viewMode, setViewMode] = useState<'canvas' | 'grid' | 'history'>('canvas')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [generations, setGenerations] = useState<GenerationTask[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null)

  // 加载生成历史
  const loadGenerations = async () => {
    setLoading(true)
    setError(null)

    try {
      const result = await GenerationService.listGenerationHistory({
        moduleType: currentModule,
        limit: 20,
        offset: 0
      })

      if (result.success && result.data) {
        setGenerations(result.data.generations)
      } else {
        setError(result.error || '加载失败')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // 轮询生成状态
  useEffect(() => {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      setPollingInterval(null)
    }

    // 只有正在处理的任务才需要轮询
    const processingTasks = generations.filter(g => g.status === 'pending' || g.status === 'processing')
    
    if (processingTasks.length > 0) {
      const interval = setInterval(async () => {
        for (const task of processingTasks) {
          try {
            const result = await GenerationService.getGenerationStatus(task.id)
            if (result.success && result.data) {
              setGenerations(prev => 
                prev.map(g => g.id === task.id ? result.data! : g)
              )
            }
          } catch (err) {
            console.error('轮询状态失败:', err)
          }
        }
      }, 2000) // 每2秒轮询一次

      setPollingInterval(interval)
    }

    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [generations])

  // 组件挂载时加载数据
  useEffect(() => {
    if (viewMode === 'history') {
      loadGenerations()
    }
  }, [currentModule, viewMode])

  // 组件卸载时清理轮询
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [pollingInterval])

  const handleGenerate = () => {
    if (status === 'generating') {
      setStatus('idle')
    } else {
      setStatus('generating')
    }
  }

  // 取消生成任务
  const handleCancel = async (generationId: string) => {
    try {
      const result = await GenerationService.cancelGeneration(generationId)
      if (result.success) {
        setGenerations(prev => 
          prev.map(g => g.id === generationId 
            ? { ...g, status: 'failed', canCancel: false } 
            : g
          )
        )
      } else {
        setError(result.error || '取消失败')
      }
    } catch (err: any) {
      setError(err.message)
    }
  }

  // 重试生成任务
  const handleRetry = async (generationId: string) => {
    try {
      const result = await GenerationService.retryGeneration(generationId)
      if (result.success) {
        // 重新加载列表
        loadGenerations()
      } else {
        setError(result.error || '重试失败')
      }
    } catch (err: any) {
      setError(err.message)
    }
  }

  // 下载生成结果
  const handleDownload = async (generation: GenerationTask) => {
    if (!generation.output_files || generation.output_files.length === 0) {
      setError('没有可下载的文件')
      return
    }

    try {
      for (const fileUrl of generation.output_files) {
        const link = document.createElement('a')
        link.href = fileUrl
        link.download = fileUrl.split('/').pop() || 'download'
        link.target = '_blank'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      }
    } catch (err: any) {
      setError(err.message)
    }
  }

  // 获取状态图标和颜色
  const getStatusInfo = (status: string, progress?: number) => {
    switch (status) {
      case 'pending':
        return {
          icon: Clock,
          color: 'text-yellow-400',
          bgColor: 'bg-yellow-400/20',
          label: '等待中'
        }
      case 'processing':
        return {
          icon: RefreshCw,
          color: 'text-blue-400',
          bgColor: 'bg-blue-400/20',
          label: '处理中'
        }
      case 'completed':
        return {
          icon: CheckCircle,
          color: 'text-green-400',
          bgColor: 'bg-green-400/20',
          label: '已完成'
        }
      case 'failed':
        return {
          icon: XCircle,
          color: 'text-red-400',
          bgColor: 'bg-red-400/20',
          label: '失败'
        }
      default:
        return {
          icon: Clock,
          color: 'text-gray-400',
          bgColor: 'bg-gray-400/20',
          label: '未知'
        }
    }
  }

  // 格式化时间
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const renderCurrentWorkspace = () => {
    switch (currentModule) {
      case 'image-gen':
        return <ImageGenerationWorkspace />
      case 'image-edit':
        return <ImageEditingWorkspace />
      case 'video-gen':
        return <VideoGenerationWorkspace />
      case '3d-gen':
        return <ThreeDGenerationWorkspace />
      default:
        return <ImageGenerationWorkspace />
    }
  }

  return (
    <div className="flex-1 bg-neutral-900 flex flex-col">
      {/* Workspace Toolbar */}
      <div className="h-12 bg-primary-800 border-b border-primary-600 flex items-center justify-between px-4">
        <div className="flex items-center space-x-2">
          <Button
            onClick={handleGenerate}
            disabled={status === 'completed'}
            className="h-8 px-3"
          >
            {status === 'generating' ? (
              <>
                <Pause className="w-4 h-4 mr-1" />
                Pause
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-1" />
                Generate
              </>
            )}
          </Button>
          
          <Button variant="outline" size="icon" className="h-8 w-8">
            <RotateCcw className="w-4 h-4" />
          </Button>
          
          <Button variant="outline" size="icon" className="h-8 w-8">
            <Save className="w-4 h-4" />
          </Button>
        </div>

        <div className="flex items-center space-x-2">
          <Button
            variant={viewMode === 'canvas' ? 'default' : 'ghost'}
            size="icon"
            className="h-8 w-8"
            onClick={() => setViewMode('canvas')}
            title="画布视图"
          >
            <Maximize2 className="w-4 h-4" />
          </Button>
          
          <Button
            variant={viewMode === 'grid' ? 'default' : 'ghost'}
            size="icon"
            className="h-8 w-8"
            onClick={() => setViewMode('grid')}
            title="网格视图"
          >
            <Grid className="w-4 h-4" />
          </Button>
          
          <Button
            variant={viewMode === 'history' ? 'default' : 'ghost'}
            size="icon"
            className="h-8 w-8"
            onClick={() => setViewMode('history')}
            title="历史记录"
          >
            <History className="w-4 h-4" />
          </Button>
          
          <Button
            onClick={loadGenerations}
            disabled={loading}
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            title="刷新"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Progress Bar */}
      {status === 'generating' && (
        <div className="h-1 bg-primary-700">
          <div 
            className="h-full bg-accent-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mx-4 mt-4 p-3 bg-red-500/20 border border-red-500/30 rounded-sm">
          <div className="flex items-center gap-2">
            <XCircle className="w-4 h-4 text-red-400" />
            <p className="text-red-400 text-sm">{error}</p>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-red-400 hover:text-red-300"
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Main Canvas Area */}
      <div className="flex-1 relative overflow-hidden">
        {viewMode === 'history' ? (
          <HistoryView 
            generations={generations}
            loading={loading}
            onCancel={handleCancel}
            onRetry={handleRetry}
            onDownload={handleDownload}
            getStatusInfo={getStatusInfo}
            formatTime={formatTime}
          />
        ) : (
          renderCurrentWorkspace()
        )}
      </div>
    </div>
  )
}

// 历史视图组件
interface HistoryViewProps {
  generations: GenerationTask[]
  loading: boolean
  onCancel: (id: string) => void
  onRetry: (id: string) => void
  onDownload: (generation: GenerationTask) => void
  getStatusInfo: (status: string, progress?: number) => any
  formatTime: (timestamp: string) => string
}

const HistoryView: React.FC<HistoryViewProps> = ({
  generations,
  loading,
  onCancel,
  onRetry,
  onDownload,
  getStatusInfo,
  formatTime
}) => {
  if (loading && generations.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-primary-900">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 text-accent-400 animate-spin mx-auto mb-4" />
          <p className="text-neutral-400">加载中...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 bg-primary-900 overflow-hidden">
      {/* Header */}
      <div className="border-b border-primary-600 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-neutral-100">生成历史</h2>
            <p className="text-sm text-neutral-400 mt-1">
              共 {generations.length} 个任务
            </p>
          </div>
        </div>
      </div>

      {/* Generations List */}
      <div className="flex-1 overflow-y-auto p-4">
        {generations.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 bg-primary-700 rounded-full flex items-center justify-center">
              <History className="w-8 h-8 text-neutral-400" />
            </div>
            <h3 className="text-lg font-medium text-neutral-100 mb-2">暂无生成历史</h3>
            <p className="text-neutral-400">开始创建你的第一个作品吧！</p>
          </div>
        ) : (
          <div className="space-y-3">
            {generations.map((generation) => {
              const statusInfo = getStatusInfo(generation.status, generation.progress)
              const StatusIcon = statusInfo.icon

              return (
                <div
                  key={generation.id}
                  className="bg-primary-800 border border-primary-600 rounded-sm p-4 hover:border-primary-500 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      {/* Status and Time */}
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${statusInfo.bgColor} ${statusInfo.color}`}>
                          <StatusIcon className="w-3 h-3" />
                          {statusInfo.label}
                        </div>
                        <span className="text-xs text-neutral-400">
                          {formatTime(generation.created_at)}
                        </span>
                        {generation.elapsedTime && (
                          <span className="text-xs text-neutral-400">
                            用时 {Math.floor(generation.elapsedTime / 60)}:{(generation.elapsedTime % 60).toString().padStart(2, '0')}
                          </span>
                        )}
                      </div>

                      {/* Prompt */}
                      <p className="text-sm text-neutral-200 mb-2 line-clamp-2">
                        {generation.prompt}
                      </p>

                      {/* Progress Bar */}
                      {generation.status === 'processing' && generation.progress !== undefined && (
                        <div className="mb-2">
                          <div className="flex items-center justify-between text-xs text-neutral-400 mb-1">
                            <span>进度</span>
                            <span>{Math.round(generation.progress)}%</span>
                          </div>
                          <div className="w-full bg-primary-700 rounded-full h-1.5">
                            <div
                              className="bg-accent-500 h-1.5 rounded-full transition-all duration-300"
                              style={{ width: `${generation.progress}%` }}
                            />
                          </div>
                        </div>
                      )}

                      {/* Output Files */}
                      {generation.output_files && generation.output_files.length > 0 && (
                        <div className="mt-2">
                          <p className="text-xs text-neutral-400 mb-1">
                            输出文件 ({generation.output_files.length}):
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {generation.output_files.map((file, index) => (
                              <span
                                key={index}
                                className="text-xs px-2 py-1 bg-primary-700 text-neutral-300 rounded"
                              >
                                {file.split('/').pop()}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 ml-4">
                      {generation.output_files && generation.output_files.length > 0 && (
                        <button
                          onClick={() => onDownload(generation)}
                          className="p-2 text-neutral-400 hover:text-accent-400 hover:bg-primary-700 rounded transition-colors"
                          title="下载"
                        >
                          <Download className="w-4 h-4" />
                        </button>
                      )}

                      {generation.canCancel && (
                        <button
                          onClick={() => onCancel(generation.id)}
                          className="p-2 text-neutral-400 hover:text-red-400 hover:bg-primary-700 rounded transition-colors"
                          title="取消"
                        >
                          <Pause className="w-4 h-4" />
                        </button>
                      )}

                      {generation.canRetry && (
                        <button
                          onClick={() => onRetry(generation.id)}
                          className="p-2 text-neutral-400 hover:text-green-400 hover:bg-primary-700 rounded transition-colors"
                          title="重试"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Loading Overlay */}
      {loading && generations.length > 0 && (
        <div className="absolute inset-0 bg-primary-900/50 flex items-center justify-center">
          <div className="bg-primary-800 p-4 rounded-sm flex items-center gap-3">
            <RefreshCw className="w-4 h-4 text-accent-400 animate-spin" />
            <span className="text-neutral-200">加载中...</span>
          </div>
        </div>
      )}
    </div>
  )
}