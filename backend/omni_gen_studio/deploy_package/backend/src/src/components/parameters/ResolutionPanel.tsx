import React, { useState, useEffect } from 'react'
import { Shuffle, RefreshCw, AlertCircle, Save, Upload, Monitor, Zap } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'
import { Slider } from '../ui/slider'
import { useGenerationContext } from '../../contexts/GenerationContext'
import { ModuleType } from '../../contexts/ModuleContext'
import { GenerationService } from '../../services/api'

interface ResolutionPanelProps {
  currentModule: ModuleType
}

interface AspectRatio {
  id: string
  name: string
  width: number
  height: number
  category: 'square' | 'portrait' | 'landscape' | 'wide' | 'ultrawide'
  megapixels: number
  description?: string
  usage_frequency: number
}

interface ResolutionPreset {
  id: string
  name: string
  width: number
  height: number
  module_type: ModuleType
  aspect_ratio_id: string
  performance_tier: 'fast' | 'standard' | 'high_quality' | 'ultra'
  memory_usage: 'low' | 'medium' | 'high' | 'extreme'
  recommended_steps: number
  created_at: string
  usage_count: number
  is_favorite: boolean
}

interface ResolutionValidation {
  isValid: boolean
  errors: string[]
  warnings: string[]
  suggestions: string[]
  optimal: boolean
}

interface ModelCompatibility {
  model_id: string
  model_name: string
  max_resolution: number
  recommended_resolutions: { width: number; height: number }[]
  memory_requirement: 'low' | 'medium' | 'high' | 'extreme'
  performance_impact: 'minimal' | 'moderate' | 'significant'
  memory_usage: 'low' | 'medium' | 'high' | 'extreme'
}

export const ResolutionPanel: React.FC<ResolutionPanelProps> = ({ currentModule }) => {
  const { config, updateConfig } = useGenerationContext()
  const [resolutionMode, setResolutionMode] = useState<'preset' | 'custom' | 'random'>('preset')
  const [aspectRatios, setAspectRatios] = useState<AspectRatio[]>([])
  const [resolutionPresets, setResolutionPresets] = useState<ResolutionPreset[]>([])
  const [modelCompatibility, setModelCompatibility] = useState<ModelCompatibility[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [validation, setValidation] = useState<ResolutionValidation>({ 
    isValid: true, 
    errors: [], 
    warnings: [], 
    suggestions: [],
    optimal: true 
  })
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [showAdvanced, setShowAdvanced] = useState(false)

  // 获取分辨率相关数据
  const loadResolutionData = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const [ratiosData, presetsData, compatibilityData] = await Promise.all([
        GenerationService.getAspectRatios(),
        GenerationService.getResolutionPresets(currentModule),
        GenerationService.getModelCompatibility()
      ])
      
      setAspectRatios(ratiosData)
      setResolutionPresets(presetsData)
      setModelCompatibility(compatibilityData)
      
      // 验证当前分辨率
      validateResolution(config.width, config.height)
    } catch (err) {
      console.error('Failed to load resolution data:', err)
      setError('加载分辨率数据失败，请稍后重试')
      // 使用备用数据
      setAspectRatios([
        { id: '1:1', name: '1:1 (512×512)', width: 512, height: 512, category: 'square', megapixels: 0.26, usage_frequency: 85 },
        { id: '4:3', name: '4:3 (640×480)', width: 640, height: 480, category: 'landscape', megapixels: 0.31, usage_frequency: 70 },
        { id: '3:2', name: '3:2 (768×512)', width: 768, height: 512, category: 'landscape', megapixels: 0.39, usage_frequency: 75 },
        { id: '16:9', name: '16:9 (768×432)', width: 768, height: 432, category: 'landscape', megapixels: 0.33, usage_frequency: 80 },
        { id: '21:9', name: '21:9 (896×384)', width: 896, height: 384, category: 'wide', megapixels: 0.34, usage_frequency: 60 },
        { id: '9:16', name: '9:16 (512×896)', width: 512, height: 896, category: 'portrait', megapixels: 0.46, usage_frequency: 90 },
        { id: '2:3', name: '2:3 (512×768)', width: 512, height: 768, category: 'portrait', megapixels: 0.39, usage_frequency: 70 },
        { id: '3:4', name: '3:4 (480×640)', width: 480, height: 640, category: 'portrait', megapixels: 0.31, usage_frequency: 65 },
        { id: '9:21', name: '9:21 (384×896)', width: 384, height: 896, category: 'ultrawide', megapixels: 0.34, usage_frequency: 45 }
      ])
      setResolutionPresets([])
      setModelCompatibility([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadResolutionData()
  }, [currentModule])

  // 分辨率验证
  const validateResolution = (width: number, height: number): ResolutionValidation => {
    const errors: string[] = []
    const warnings: string[] = []
    const suggestions: string[] = []
    const megapixels = (width * height) / 1000000

    // 基本验证
    if (width < 256 || height < 256) {
      errors.push('分辨率不能小于256×256')
    }
    
    if (width > 2048 || height > 2048) {
      errors.push('分辨率不能大于2048×2048')
    }

    // 内存使用警告
    if (megapixels > 4) {
      warnings.push('高分辨率将消耗大量内存和计算时间')
    }

    if (megapixels > 8) {
      warnings.push('超高分辨率可能超出模型处理能力')
    }

    // 优化建议
    if (width % 64 !== 0 || height % 64 !== 0) {
      suggestions.push('建议使用64的倍数以获得最佳效果')
    }

    // 模型兼容性
    const compatibleModels = modelCompatibility.filter(model => 
      (width * height) <= model.max_resolution
    )

    if (compatibleModels.length === 0) {
      errors.push('当前分辨率超出所有可用模型的处理能力')
    } else if (compatibleModels.length < 3) {
      warnings.push('仅少数模型支持此分辨率')
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
      suggestions,
      optimal: warnings.length === 0 && suggestions.length === 0
    }
  }

  // 获取分类选项
  const categories = [
    { id: 'all', name: '全部', icon: Monitor },
    { id: 'square', name: '正方形', icon: Monitor },
    { id: 'portrait', name: '竖向', icon: Monitor },
    { id: 'landscape', name: '横向', icon: Monitor },
    { id: 'wide', name: '宽屏', icon: Monitor },
    { id: 'ultrawide', name: '超宽', icon: Monitor }
  ]

  // 筛选宽高比
  const filteredRatios = selectedCategory === 'all' 
    ? aspectRatios 
    : aspectRatios.filter(ratio => ratio.category === selectedCategory)

  // 按使用频率排序
  const sortedRatios = [...filteredRatios].sort((a, b) => b.usage_frequency - a.usage_frequency)

  const handleAspectRatioSelect = (ratio: any) => {
    updateConfig({ 
      width: ratio.width, 
      height: ratio.height 
    })
  }

  const handleRandomResolution = () => {
    const randomRatio = aspectRatios[Math.floor(Math.random() * aspectRatios.length)]
    handleAspectRatioSelect(randomRatio)
  }

  const handleWidthChange = (width: number) => {
    updateConfig({ width })
  }

  const handleHeightChange = (height: number) => {
    updateConfig({ height })
  }

  return (
    <Accordion type="single" defaultValue="resolution" className="w-full">
      <AccordionItem value="resolution" className="border border-primary-600 rounded-sm">
        <AccordionTrigger className="px-3 py-2 hover:bg-primary-700">
          <div className="flex items-center justify-between w-full">
            <span className="text-sm font-medium">分辨率模组</span>
            <div className="flex items-center space-x-1">
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowAdvanced(!showAdvanced)
                }}
                title="切换高级选项"
              >
                <Zap className="w-3 h-3" />
              </Button>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={(e) => {
                  e.stopPropagation()
                  loadResolutionData()
                }}
                disabled={loading}
                title="刷新分辨率数据"
              >
                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
              </Button>
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

            {/* 分辨率验证结果 */}
            {!validation.isValid && validation.errors.length > 0 && (
              <div className="space-y-1">
                {validation.errors.map((error, index) => (
                  <div key={index} className="flex items-center space-x-2 p-2 bg-red-500/20 border border-red-500/30 rounded-sm">
                    <AlertCircle className="w-4 h-4 text-red-400" />
                    <span className="text-xs text-red-300">{error}</span>
                  </div>
                ))}
              </div>
            )}

            {/* 分辨率警告和建议 */}
            {(validation.warnings.length > 0 || validation.suggestions.length > 0) && (
              <div className="space-y-1">
                {validation.warnings.map((warning, index) => (
                  <div key={`warn-${index}`} className="flex items-center space-x-2 p-2 bg-yellow-500/20 border border-yellow-500/30 rounded-sm">
                    <AlertCircle className="w-4 h-4 text-yellow-400" />
                    <span className="text-xs text-yellow-300">{warning}</span>
                  </div>
                ))}
                {validation.suggestions.map((suggestion, index) => (
                  <div key={`suggest-${index}`} className="flex items-center space-x-2 p-2 bg-blue-500/20 border border-blue-500/30 rounded-sm">
                    <Zap className="w-4 h-4 text-blue-400" />
                    <span className="text-xs text-blue-300">{suggestion}</span>
                  </div>
                ))}
              </div>
            )}

            {/* 当前分辨率信息 */}
            <div className="p-2 bg-primary-700 rounded-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs text-neutral-400">当前分辨率</span>
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-medium">{config.width} × {config.height}</span>
                  <span className="text-xs text-neutral-500">
                    ({((config.width * config.height) / 1000000).toFixed(1)}MP)
                  </span>
                  {validation.optimal && (
                    <span className="text-xs px-1.5 py-0.5 bg-green-500/20 text-green-400 rounded">
                      优化
                    </span>
                  )}
                </div>
              </div>
            </div>
            {/* Resolution Mode */}
            <div className="flex space-x-1">
              <Button
                variant={resolutionMode === 'preset' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setResolutionMode('preset')}
                className="text-xs h-7 flex-1"
              >
                预设
              </Button>
              <Button
                variant={resolutionMode === 'custom' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setResolutionMode('custom')}
                className="text-xs h-7 flex-1"
              >
                自定义
              </Button>
              <Button
                variant={resolutionMode === 'random' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setResolutionMode('random')}
                className="text-xs h-7 flex-1"
              >
                随机
              </Button>
            </div>

            {resolutionMode === 'preset' && (
              <div className="space-y-3">
                {/* 分类筛选 */}
                <div className="space-y-1">
                  <label className="text-xs text-neutral-400">分类</label>
                  <div className="flex flex-wrap gap-1">
                    {categories.map((category) => {
                      const IconComponent = category.icon
                      return (
                        <Button
                          key={category.id}
                          variant={selectedCategory === category.id ? 'default' : 'ghost'}
                          size="sm"
                          onClick={() => setSelectedCategory(category.id)}
                          className={`text-xs h-6 px-2 ${
                            selectedCategory === category.id ? 'bg-accent-500' : ''
                          }`}
                        >
                          <IconComponent className="w-3 h-3 mr-1" />
                          {category.name}
                        </Button>
                      )
                    })}
                  </div>
                </div>

                {/* 宽高比选择 */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-neutral-400">宽高比</label>
                    {loading && (
                      <RefreshCw className="w-4 h-4 animate-spin text-neutral-400" />
                    )}
                  </div>
                  {sortedRatios.length === 0 ? (
                    <div className="text-center py-4 text-xs text-neutral-400">
                      加载中...
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-1">
                      {sortedRatios.map((ratio) => (
                        <Button
                          key={ratio.id}
                          variant={
                            config.width === ratio.width && config.height === ratio.height 
                              ? 'default' 
                              : 'ghost'
                          }
                          size="sm"
                          onClick={() => {
                            handleAspectRatioSelect(ratio)
                            validateResolution(ratio.width, ratio.height)
                          }}
                          className="text-xs h-7 justify-start"
                        >
                          <div className="text-left">
                            <div>{ratio.name}</div>
                            <div className="text-xs opacity-60">
                              {ratio.megapixels.toFixed(1)}MP • {ratio.usage_frequency}%使用
                            </div>
                          </div>
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {resolutionMode === 'custom' && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs text-neutral-400">宽度</label>
                    <Input
                      value={config.width}
                      onChange={(e) => {
                        const newWidth = parseInt(e.target.value) || 512
                        handleWidthChange(newWidth)
                        validateResolution(newWidth, config.height)
                      }}
                      className="h-7 text-xs"
                      min={256}
                      max={2048}
                      step={64}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-neutral-400">高度</label>
                    <Input
                      value={config.height}
                      onChange={(e) => {
                        const newHeight = parseInt(e.target.value) || 512
                        handleHeightChange(newHeight)
                        validateResolution(config.width, newHeight)
                      }}
                      className="h-7 text-xs"
                      min={256}
                      max={2048}
                      step={64}
                    />
                  </div>
                </div>
                
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-neutral-400">宽度调整</label>
                    <span className="text-xs text-neutral-300">{config.width}</span>
                  </div>
                  <Slider
                    value={[config.width]}
                    onValueChange={([value]) => {
                      handleWidthChange(value)
                      validateResolution(value, config.height)
                    }}
                    max={2048}
                    min={256}
                    step={64}
                    className="w-full"
                  />
                </div>
                
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-neutral-400">高度调整</label>
                    <span className="text-xs text-neutral-300">{config.height}</span>
                  </div>
                  <Slider
                    value={[config.height]}
                    onValueChange={([value]) => {
                      handleHeightChange(value)
                      validateResolution(config.width, value)
                    }}
                    max={2048}
                    min={256}
                    step={64}
                    className="w-full"
                  />
                </div>

                {/* 高级选项 */}
                {showAdvanced && (
                  <div className="space-y-2 border-t border-primary-600 pt-3">
                    <label className="text-xs text-neutral-400 font-medium">高级选项</label>
                    
                    {/* 优化建议 */}
                    <div className="space-y-1">
                      <label className="text-xs text-neutral-400">智能优化</label>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          // 自动调整为64的倍数
                          const optimizedWidth = Math.round(config.width / 64) * 64
                          const optimizedHeight = Math.round(config.height / 64) * 64
                          updateConfig({ width: optimizedWidth, height: optimizedHeight })
                          validateResolution(optimizedWidth, optimizedHeight)
                        }}
                        className="w-full h-7 text-xs justify-start"
                      >
                        <Zap className="w-3 h-3 mr-1" />
                        调整为64倍数 (优化性能)
                      </Button>
                    </div>

                    {/* 模型兼容性信息 */}
                    {modelCompatibility.length > 0 && (
                      <div className="space-y-1">
                        <label className="text-xs text-neutral-400">模型兼容性</label>
                        <div className="text-xs text-neutral-400 space-y-1">
                          {modelCompatibility.slice(0, 3).map((model, index) => (
                            <div key={index} className="flex items-center justify-between p-1 bg-primary-700 rounded">
                              <span>{model.model_name}</span>
                              <span className={`text-xs px-1 rounded ${
                                model.memory_usage === 'low' ? 'bg-green-500/20 text-green-400' :
                                model.memory_usage === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                                'bg-red-500/20 text-red-400'
                              }`}>
                                {model.memory_usage}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {resolutionMode === 'random' && (
              <div className="space-y-2">
                <Button
                  onClick={handleRandomResolution}
                  className="w-full h-8"
                >
                  <Shuffle className="w-4 h-4 mr-1" />
                  随机选择分辨率
                </Button>
                <div className="text-center text-xs text-neutral-400">
                  当前: {config.width} × {config.height}
                </div>
              </div>
            )}

            {/* Quick Resolutions */}
            <div className="space-y-1">
              <label className="text-xs text-neutral-400">快速选择</label>
              <div className="grid grid-cols-2 gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => updateConfig({ width: 512, height: 512 })}
                  className="text-xs h-6"
                >
                  512²
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => updateConfig({ width: 768, height: 768 })}
                  className="text-xs h-6"
                >
                  768²
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => updateConfig({ width: 512, height: 768 })}
                  className="text-xs h-6"
                >
                  512×768
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => updateConfig({ width: 768, height: 512 })}
                  className="text-xs h-6"
                >
                  768×512
                </Button>
              </div>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}