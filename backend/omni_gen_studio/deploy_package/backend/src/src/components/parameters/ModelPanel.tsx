import React, { useState, useEffect } from 'react'
import { ChevronDown, Upload, Download, RefreshCw, AlertCircle } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'
import { useModelContext } from '../../contexts/ModelContext'
import { ModuleType } from '../../contexts/ModuleContext'
import { ModelService, ModelConfig } from '../../services/api'

interface ModelPanelProps {
  currentModule: ModuleType
}

export const ModelPanel: React.FC<ModelPanelProps> = ({ currentModule }) => {
  const { currentCheckpoint, setCurrentCheckpoint } = useModelContext()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedModelType, setSelectedModelType] = useState('checkpoint')
  const [models, setModels] = useState<ModelConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  // Model types configuration
  const modelTypes = [
    { id: 'checkpoint', name: 'Checkpoints', count: 0 },
    { id: 'lora', name: 'LoRA Networks', count: 0 },
    { id: 'controlnet', name: 'ControlNet', count: 0 },
    { id: 'vae', name: 'VAE Models', count: 0 },
    { id: 'clip', name: 'CLIP Models', count: 0 }
  ]

  // Load models from API
  const loadModels = async () => {
    setLoading(true)
    setError(null)

    try {
      const result = await ModelService.listModels()
      if (result.success && result.data) {
        setModels(result.data.models)
        
        // Update model type counts
        modelTypes.forEach(type => {
          type.count = result.data.models.filter(m => m.type === type.id).length
        })
      } else {
        setError(result.error || '加载模型失败')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Load models on component mount
  useEffect(() => {
    loadModels()
  }, [])

  // Handle file upload
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setUploading(true)
    setError(null)

    try {
      const modelType = selectedModelType
      const result = await ModelService.uploadModel({
        file,
        type: modelType,
        name: file.name,
        description: `用户上传的${modelType}模型`
      })

      if (result.success) {
        await loadModels() // Reload models
        setSearchQuery('')
      } else {
        setError(result.error || '上传失败')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setUploading(false)
      // Reset file input
      event.target.value = ''
    }
  }

  // Handle model deletion
  const handleDeleteModel = async (modelId: string) => {
    try {
      const result = await ModelService.deleteModel(modelId)
      if (result.success) {
        await loadModels() // Reload models
      } else {
        setError(result.error || '删除失败')
      }
    } catch (err: any) {
      setError(err.message)
    }
  }

  // Filter models based on search and type
  const filteredModels = models
    .filter(model => {
      const matchesType = model.type === selectedModelType
      const matchesSearch = model.name.toLowerCase().includes(searchQuery.toLowerCase())
      return matchesType && matchesSearch
    })
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  return (
    <Accordion type="single" defaultValue="model" className="w-full">
      <AccordionItem value="model" className="border border-primary-600 rounded-sm">
        <AccordionTrigger className="px-3 py-2 hover:bg-primary-700">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium">模型模组</span>
              <span className="text-xs text-neutral-400">
                {modelTypes.find(t => t.id === selectedModelType)?.count || 0}
              </span>
              {loading && <RefreshCw className="w-3 h-3 animate-spin" />}
            </div>
            <div className="flex items-center space-x-1">
              <input
                type="file"
                accept=".safetensors,.ckpt,.bin,.gguf,.pth,.json"
                onChange={handleFileUpload}
                className="hidden"
                id="model-upload"
                disabled={uploading}
              />
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={() => document.getElementById('model-upload')?.click()}
                disabled={uploading}
                title="上传模型"
              >
                <Upload className="w-3 h-3" />
              </Button>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={loadModels}
                disabled={loading}
                title="刷新模型"
              >
                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent className="px-0 pb-2">
          <div className="px-3 space-y-3">
            {/* Error Display */}
            {error && (
              <div className="p-2 bg-red-500/20 border border-red-500/30 rounded-sm">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-3 h-3 text-red-400" />
                  <p className="text-xs text-red-400">{error}</p>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-4 w-4 ml-auto"
                    onClick={() => setError(null)}
                  >
                    <ChevronDown className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            )}

            {/* Upload Progress */}
            {uploading && (
              <div className="p-2 bg-blue-500/20 border border-blue-500/30 rounded-sm">
                <div className="flex items-center gap-2">
                  <RefreshCw className="w-3 h-3 text-blue-400 animate-spin" />
                  <p className="text-xs text-blue-400">正在上传模型...</p>
                </div>
              </div>
            )}

            {/* Model Type Selector */}
            <div className="grid grid-cols-2 gap-1">
              {modelTypes.map((type) => (
                <Button
                  key={type.id}
                  variant={selectedModelType === type.id ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setSelectedModelType(type.id)}
                  className="text-xs h-7"
                >
                  {type.name}
                  <span className="ml-1 text-xs opacity-70">({type.count})</span>
                </Button>
              ))}
            </div>

            {/* Search */}
            <div className="relative">
              <Input
                placeholder="搜索模型..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-7 text-xs"
              />
            </div>

            {/* Model List */}
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {loading ? (
                <div className="text-center py-4">
                  <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-2 text-neutral-400" />
                  <p className="text-xs text-neutral-400">加载中...</p>
                </div>
              ) : filteredModels.length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-xs text-neutral-400">
                    {searchQuery ? '未找到匹配的模型' : '暂无模型'}
                  </p>
                  {!searchQuery && (
                    <p className="text-xs text-neutral-500 mt-1">
                      点击上传按钮添加模型
                    </p>
                  )}
                </div>
              ) : (
                filteredModels.map((model) => (
                  <div
                    key={model.id}
                    className={`p-2 rounded-sm cursor-pointer transition-colors ${
                      (selectedModelType === 'checkpoint' && model.id === currentCheckpoint)
                        ? 'bg-accent-500/20 border border-accent-500/30'
                        : 'bg-primary-700 hover:bg-primary-600'
                    }`}
                    onClick={() => {
                      if (selectedModelType === 'checkpoint') {
                        setCurrentCheckpoint(model.id)
                      }
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-neutral-100 truncate">
                          {model.name}
                        </div>
                        <div className="text-xs text-neutral-400">
                          {model.size || `类型: ${model.type}`}
                        </div>
                        <div className="text-xs text-neutral-500">
                          {new Date(model.created_at).toLocaleDateString('zh-CN')}
                        </div>
                      </div>
                      <div className="flex items-center space-x-1 ml-2">
                        {model.is_active && (
                          <div className="w-2 h-2 bg-semantic-success rounded-full" title="已激活"></div>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-4 w-4 hover:bg-red-500/20"
                          onClick={(e) => {
                            e.stopPropagation()
                            if (confirm('确定要删除这个模型吗？')) {
                              handleDeleteModel(model.id)
                            }
                          }}
                          title="删除模型"
                        >
                          <ChevronDown className="w-3 h-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Model Info */}
            <div className="text-xs text-neutral-400 space-y-1">
              <div>支持格式: safetensors, checkpoint, diffusers, gguf</div>
              <div>支持模型: {modelTypes.find(t => t.id === selectedModelType)?.count || 0} 个</div>
              {searchQuery && <div>搜索结果: {filteredModels.length} 个</div>}
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}