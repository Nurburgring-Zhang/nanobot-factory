import React, { useState, useEffect } from 'react'
import { Plus, Minus, Upload, X, RefreshCw, AlertCircle } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'
import { Slider } from '../ui/slider'
import { useModelContext } from '../../contexts/ModelContext'
import { ModuleType } from '../../contexts/ModuleContext'
import { GenerationService } from '../../services/api'

interface LoRAPanelProps {
  currentModule: ModuleType
}

interface LoRAModel {
  id: string
  name: string
  category: string
  weight: number
  description?: string
  tags?: string[]
  download_count?: number
  size?: string
}

export const LoRAPanel: React.FC<LoRAPanelProps> = ({ currentModule }) => {
  const { selectedModels, addModel, removeModel, updateModelWeight } = useModelContext()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('All')
  const [availableLoRAs, setAvailableLoRAs] = useState<LoRAModel[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)

  // 获取可用LoRA列表
  const loadLoRAList = async () => {
    try {
      setLoading(true)
      setError(null)
      const loraList = await GenerationService.getLoRAList()
      setAvailableLoRAs(loraList)
    } catch (err) {
      console.error('Failed to load LoRA list:', err)
      setError('加载LoRA列表失败，请稍后重试')
      // 使用备用数据
      setAvailableLoRAs([
        { id: 'l1', name: 'Anime Style v2', category: 'Style', weight: 0.8 },
        { id: 'l2', name: 'Photorealistic Detail', category: 'Quality', weight: 0.6 },
        { id: 'l3', name: 'Cinematic Lighting', category: 'Style', weight: 1.0 },
        { id: 'l4', name: 'Character Consistency', category: 'Character', weight: 0.7 },
        { id: 'l5', name: 'Art Nouveau Style', category: 'Style', weight: 0.9 },
        { id: 'l6', name: 'Vaporwave Aesthetic', category: 'Style', weight: 0.5 },
        { id: 'l7', name: 'Watercolor Effect', category: 'Style', weight: 0.8 },
        { id: 'l8', name: 'Portrait Enhancement', category: 'Quality', weight: 0.7 }
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLoRAList()
  }, [currentModule])

  // 文件上传处理
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      setUploadProgress(0)
      const result = await GenerationService.uploadLoRA(file, (progress) => {
        setUploadProgress(progress)
      })
      
      if (result.success) {
        await loadLoRAList() // 重新加载列表
        setUploadProgress(0)
      }
    } catch (err) {
      console.error('Failed to upload LoRA:', err)
      setError('上传LoRA失败，请检查文件格式')
      setUploadProgress(0)
    }
  }

  const selectedLoRAs = selectedModels.filter(model => model.type === 'lora')

  // 获取所有分类
  const categories = ['All', ...Array.from(new Set(availableLoRAs.map(lora => lora.category)))]

  // 筛选LoRA列表
  const filteredLoRAs = availableLoRAs.filter(lora => {
    const matchesSearch = lora.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         lora.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         lora.tags?.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()))
    const matchesCategory = selectedCategory === 'All' || lora.category === selectedCategory
    return matchesSearch && matchesCategory
  })

  const handleAddLoRA = (lora: any) => {
    addModel({
      id: lora.id,
      name: lora.name,
      type: 'lora',
      path: `/models/lora/${lora.id}.safetensors`,
      weight: lora.weight
    })
  }

  const handleRemoveLoRA = (id: string) => {
    removeModel(id)
  }

  const handleWeightChange = (id: string, weight: number) => {
    updateModelWeight(id, weight)
  }

  return (
    <Accordion type="single" defaultValue="lora" className="w-full">
      <AccordionItem value="lora" className="border border-primary-600 rounded-sm">
        <AccordionTrigger className="px-3 py-2 hover:bg-primary-700">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium">LoRA 模组</span>
              <span className="text-xs text-neutral-400">
                {selectedLoRAs.length}/3
              </span>
            </div>
            <div className="flex items-center space-x-1">
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={loadLoRAList}
                disabled={loading}
                title="刷新LoRA列表"
              >
                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
              </Button>
              <label className="cursor-pointer">
                <input
                  type="file"
                  accept=".safetensors,.ckpt,.pt,.bin"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <Button variant="ghost" size="icon" className="h-6 w-6">
                  <Upload className="w-3 h-3" />
                </Button>
              </label>
              <span className="text-xs text-neutral-400">
                最多支持3个
              </span>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent className="px-0 pb-2">
          <div className="px-3 space-y-3">
            {/* 错误状态 */}
            {error && (
              <div className="flex items-center space-x-2 p-2 bg-red-500/20 border border-red-500/30 rounded-sm">
                <AlertCircle className="w-4 h-4 text-red-400" />
                <span className="text-xs text-red-300">{error}</span>
              </div>
            )}

            {/* 上传进度 */}
            {uploadProgress > 0 && uploadProgress < 100 && (
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-neutral-400">上传中...</span>
                  <span className="text-neutral-300">{uploadProgress}%</span>
                </div>
                <div className="w-full bg-primary-800 rounded-full h-1">
                  <div 
                    className="bg-accent-500 h-1 rounded-full transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}
            {/* Selected LoRAs */}
            {selectedLoRAs.length > 0 && (
              <div className="space-y-2">
                <label className="text-xs text-neutral-400">已选 LoRA</label>
                {selectedLoRAs.map((lora) => (
                  <div key={lora.id} className="p-2 bg-primary-700 rounded-sm">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-neutral-100">
                        {lora.name}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5"
                        onClick={() => handleRemoveLoRA(lora.id)}
                      >
                        <X className="w-3 h-3" />
                      </Button>
                    </div>
                    
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-neutral-400">权重</span>
                        <span className="text-xs text-neutral-300">
                          {lora.weight?.toFixed(1) || 0.8}
                        </span>
                      </div>
                      <Slider
                        value={[lora.weight || 0.8]}
                        onValueChange={([value]) => handleWeightChange(lora.id, value)}
                        max={2.0}
                        min={0.1}
                        step={0.1}
                        className="w-full"
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Add LoRA */}
            {selectedLoRAs.length < 3 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs text-neutral-400">添加 LoRA</label>
                  <Button variant="ghost" size="icon" className="h-6 w-6">
                    <Plus className="w-3 h-3" />
                  </Button>
                </div>

                {/* Search */}
                <div className="relative">
                  <Input
                    placeholder="搜索 LoRA..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="h-7 text-xs"
                  />
                </div>

                {/* Available LoRAs */}
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {loading ? (
                    <div className="flex items-center justify-center py-4">
                      <RefreshCw className="w-4 h-4 animate-spin text-neutral-400" />
                      <span className="ml-2 text-xs text-neutral-400">加载中...</span>
                    </div>
                  ) : filteredLoRAs.length === 0 ? (
                    <div className="text-center py-4 text-xs text-neutral-400">
                      {searchQuery || selectedCategory !== 'All' ? '没有找到匹配的LoRA' : '暂无可用LoRA'}
                    </div>
                  ) : (
                    filteredLoRAs.map((lora) => (
                    <div
                      key={lora.id}
                      className={`p-2 rounded-sm cursor-pointer transition-colors ${
                        selectedLoRAs.find(selected => selected.id === lora.id)
                          ? 'bg-accent-500/20 border border-accent-500/30'
                          : 'bg-primary-700 hover:bg-primary-600'
                      }`}
                      onClick={() => handleAddLoRA(lora)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-neutral-100 truncate">
                            {lora.name}
                          </div>
                          <div className="text-xs text-neutral-400">
                            {lora.category} • {lora.weight}
                          </div>
                        </div>
                        <div className="flex items-center space-x-1 ml-2">
                          {selectedLoRAs.find(selected => selected.id === lora.id) ? (
                            <Minus className="w-3 h-3 text-accent-400" />
                          ) : (
                            <Plus className="w-3 h-3 text-neutral-400" />
                          )}
                        </div>
                      </div>
                    </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* LoRA Categories */}
            <div className="space-y-1">
              <label className="text-xs text-neutral-400">分类</label>
              <div className="flex flex-wrap gap-1">
                {categories.map((category) => (
                  <Button
                    key={category}
                    variant={selectedCategory === category ? "default" : "ghost"}
                    size="sm"
                    className={`text-xs h-6 px-2 ${
                      selectedCategory === category 
                        ? 'bg-accent-500 text-white' 
                        : 'hover:bg-primary-600'
                    }`}
                    onClick={() => setSelectedCategory(category)}
                  >
                    {category}
                    {category !== 'All' && (
                      <span className="ml-1 text-xs opacity-60">
                        ({availableLoRAs.filter(lora => lora.category === category).length})
                      </span>
                    )}
                  </Button>
                ))}
              </div>
            </div>

            {/* Info */}
            <div className="text-xs text-neutral-400 space-y-1">
              <div>• LoRA 权重范围: 0.1 - 2.0</div>
              <div>• 推荐权重: 0.6 - 1.2</div>
              <div>• 格式: .safetensors, .ckpt</div>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}