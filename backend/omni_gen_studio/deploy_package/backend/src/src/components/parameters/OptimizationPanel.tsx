import React, { useState, useEffect } from 'react'
import { Zap, Shield, Sparkles, RefreshCw, AlertCircle, Save, Upload, Settings, Cpu, Monitor } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'
import { Slider } from '../ui/slider'
import { useGenerationContext } from '../../contexts/GenerationContext'
import { ModuleType } from '../../contexts/ModuleContext'
import { GenerationService } from '../../services/api'

interface OptimizationPanelProps {
  currentModule: ModuleType
}

interface UpscalingMethod {
  id: string
  name: string
  description: string
  type: 'real_esrgan' | 'seedvr' | 'latent_upscale' | 'swinir' | 'esrgan'
  supported_formats: string[]
  max_scale: number
  quality_rating: number
  speed_rating: number
  memory_usage: 'low' | 'medium' | 'high' | 'extreme'
  recommended_for: string[]
}

interface StyleFilter {
  id: string
  name: string
  description: string
  type: 'color' | 'artistic' | 'cinematic' | 'vintage' | 'modern'
  intensity: number
  parameters: Record<string, any>
  preview_available: boolean
  processing_time: number
}

interface OptimizationPreset {
  id: string
  name: string
  description: string
  module_type: ModuleType
  settings: any
  created_at: string
  usage_count: number
  is_favorite: boolean
  performance_score: number
}

interface PerformanceMetrics {
  gpu_usage: number
  memory_usage: number
  processing_speed: number
  quality_score: number
  efficiency_rating: 'poor' | 'fair' | 'good' | 'excellent'
}

interface AdvancedOptimization {
  hires_fix: {
    enabled: boolean
    scale: number
    denoise_strength: number
    steps: number
  }
  noise_injection: {
    enabled: boolean
    strength: number
    type: 'gaussian' | 'uniform' | 'perlin'
  }
  seed_enhancement: {
    enabled: boolean
    strength: number
    method: 'interpolation' | 'extrapolation' | 'hybrid'
  }
  ai_upscaling: {
    method: string
    scale: number
    parameters: Record<string, any>
  }
  style_filtering: {
    filter: string
    intensity: number
    parameters: Record<string, any>
  }
  refiner: {
    enabled: boolean
    model: string
    strength: number
  }
}

export const OptimizationPanel: React.FC<OptimizationPanelProps> = ({ currentModule }) => {
  const { config, updateConfig } = useGenerationContext()
  const [hiresFixEnabled, setHiresFixEnabled] = useState(false)
  const [refinerEnabled, setRefinerEnabled] = useState(false)
  const [noiseInjection, setNoiseInjection] = useState(false)
  const [seedEnhance, setSeedEnhance] = useState(false)

  const [noiseStrength, setNoiseStrength] = useState(0.1)
  const [seedEnhanceStrength, setSeedEnhanceStrength] = useState(0.2)

  const [upscalingMethods, setUpscalingMethods] = useState<UpscalingMethod[]>([])
  const [selectedUpscale, setSelectedUpscale] = useState('none')
  const [upscaleFactor, setUpscaleFactor] = useState(2)
  const [denoiseStrength, setDenoiseStrength] = useState(0.7)

  const [styleFilters, setStyleFilters] = useState<StyleFilter[]>([])
  const [selectedFilter, setSelectedFilter] = useState('none')

  const [optimizationPresets, setOptimizationPresets] = useState<OptimizationPreset[]>([])
  const [performanceMetrics, setPerformanceMetrics] = useState<PerformanceMetrics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [performanceMonitoring, setPerformanceMonitoring] = useState(false)

  // 获取优化相关数据
  const loadOptimizationData = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const [upscalingData, filtersData, presetsData, metricsData] = await Promise.all([
        GenerationService.getUpscalingMethods(),
        GenerationService.getStyleFilters(),
        GenerationService.getOptimizationPresets(currentModule),
        GenerationService.getPerformanceMetrics()
      ])
      
      setUpscalingMethods(upscalingData)
      setStyleFilters(filtersData)
      setOptimizationPresets(presetsData)
      setPerformanceMetrics(metricsData)
    } catch (err) {
      console.error('Failed to load optimization data:', err)
      setError('加载优化数据失败，请稍后重试')
      // 使用备用数据
      setUpscalingMethods([
        { 
          id: 'real_esrgan', 
          name: 'Real-ESRGAN', 
          description: '高质量图像放大', 
          type: 'real_esrgan', 
          supported_formats: ['jpg', 'png', 'webp'], 
          max_scale: 4, 
          quality_rating: 9, 
          speed_rating: 7, 
          memory_usage: 'medium',
          recommended_for: ['photography', 'portraits']
        },
        { 
          id: 'seedvr', 
          name: 'SeedVR 2.5', 
          description: 'AI 智能放大', 
          type: 'seedvr', 
          supported_formats: ['jpg', 'png'], 
          max_scale: 8, 
          quality_rating: 10, 
          speed_rating: 5, 
          memory_usage: 'high',
          recommended_for: ['artwork', 'illustrations']
        }
      ])
      setStyleFilters([
        { id: 'cinematic', name: '电影感', description: '电影级调色', type: 'cinematic', intensity: 0.8, parameters: {}, preview_available: true, processing_time: 2 },
        { id: 'vintage', name: '复古', description: '复古滤镜', type: 'vintage', intensity: 0.7, parameters: {}, preview_available: true, processing_time: 1 },
        { id: 'cyberpunk', name: '赛博朋克', description: '赛博朋克风格', type: 'modern', intensity: 0.9, parameters: {}, preview_available: true, processing_time: 3 }
      ])
      setOptimizationPresets([])
      setPerformanceMetrics(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOptimizationData()
  }, [currentModule])

  // 保存优化预设
  const handleSavePreset = async (name: string, description: string) => {
    try {
      const settings = {
        hires_fix: { enabled: hiresFixEnabled, scale: upscaleFactor, denoise_strength: denoiseStrength },
        noise_injection: { enabled: noiseInjection, strength: noiseStrength },
        seed_enhancement: { enabled: seedEnhance, strength: seedEnhanceStrength },
        ai_upscaling: { method: selectedUpscale, scale: upscaleFactor },
        style_filtering: { filter: selectedFilter, intensity: 0.8 },
        refiner: { enabled: refinerEnabled }
      }
      
      const result = await GenerationService.saveOptimizationPreset({
        name,
        description,
        module_type: currentModule,
        settings
      })
      
      if (result.success) {
        await loadOptimizationData() // 重新加载预设列表
      } else {
        setError(result.error || '保存预设失败')
      }
    } catch (err) {
      console.error('Failed to save preset:', err)
      setError('保存预设失败')
    }
  }

  // 加载优化预设
  const handleLoadPreset = async (preset: OptimizationPreset) => {
    try {
      const settings = preset.settings
      
      setHiresFixEnabled(settings.hires_fix?.enabled || false)
      setNoiseInjection(settings.noise_injection?.enabled || false)
      setSeedEnhance(settings.seed_enhancement?.enabled || false)
      setRefinerEnabled(settings.refiner?.enabled || false)
      
      if (settings.hires_fix) {
        setUpscaleFactor(settings.hires_fix.scale || 2)
        setDenoiseStrength(settings.hires_fix.denoise_strength || 0.7)
      }
      
      if (settings.noise_injection) {
        setNoiseStrength(settings.noise_injection.strength || 0.1)
      }
      
      if (settings.seed_enhancement) {
        setSeedEnhanceStrength(settings.seed_enhancement.strength || 0.2)
      }
      
      if (settings.ai_upscaling) {
        setSelectedUpscale(settings.ai_upscaling.method || 'none')
        setUpscaleFactor(settings.ai_upscaling.scale || 2)
      }
      
      if (settings.style_filtering) {
        setSelectedFilter(settings.style_filtering.filter || 'none')
      }
      
      await GenerationService.incrementPresetUsage(preset.id) // 增加使用次数
      await loadOptimizationData() // 重新加载预设列表（更新使用次数）
    } catch (err) {
      console.error('Failed to load preset:', err)
      setError('加载预设失败')
    }
  }

  // 性能监控切换
  const togglePerformanceMonitoring = () => {
    setPerformanceMonitoring(!performanceMonitoring)
    if (!performanceMonitoring) {
      // 启动性能监控
      GenerationService.startPerformanceMonitoring().then(() => {
        loadOptimizationData() // 重新加载性能指标
      })
    } else {
      // 停止性能监控
      GenerationService.stopPerformanceMonitoring()
    }
  }

  return (
    <Accordion type="single" defaultValue="optimization" className="w-full">
      <AccordionItem value="optimization" className="border border-primary-600 rounded-sm">
        <AccordionTrigger className="px-3 py-2 hover:bg-primary-700">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4" />
              <span className="text-sm font-medium">优化模组</span>
            </div>
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
                <Settings className="w-3 h-3" />
              </Button>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={(e) => {
                  e.stopPropagation()
                  togglePerformanceMonitoring()
                }}
                title={performanceMonitoring ? "停止性能监控" : "启动性能监控"}
              >
                <Monitor className={`w-3 h-3 ${performanceMonitoring ? 'text-green-400' : ''}`} />
              </Button>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={(e) => {
                  e.stopPropagation()
                  loadOptimizationData()
                }}
                disabled={loading}
                title="刷新优化数据"
              >
                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent className="px-0 pb-2">
          <div className="px-3 space-y-4">
            {/* 错误状态 */}
            {error && (
              <div className="flex items-center space-x-2 p-2 bg-red-500/20 border border-red-500/30 rounded-sm">
                <AlertCircle className="w-4 h-4 text-red-400" />
                <span className="text-xs text-red-300">{error}</span>
              </div>
            )}

            {/* 性能指标 */}
            {performanceMonitoring && performanceMetrics && (
              <div className="p-2 bg-primary-700 rounded-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs text-neutral-400">性能监控</span>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                    <span className="text-xs text-green-400">监控中</span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-neutral-400">GPU使用率</span>
                    <span className="text-neutral-300">{performanceMetrics.gpu_usage}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-400">内存使用</span>
                    <span className="text-neutral-300">{performanceMetrics.memory_usage}MB</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-400">处理速度</span>
                    <span className="text-neutral-300">{performanceMetrics.processing_speed}x</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-400">质量评分</span>
                    <span className={`text-${performanceMetrics.efficiency_rating === 'excellent' ? 'green' : performanceMetrics.efficiency_rating === 'good' ? 'yellow' : 'red'}-400`}>
                      {performanceMetrics.quality_score}/10
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* 优化预设 */}
            {optimizationPresets.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs text-neutral-400">优化预设</label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const name = prompt('请输入预设名称:')
                      if (name) {
                        handleSavePreset(name, '')
                      }
                    }}
                    className="h-6 px-2 text-xs"
                  >
                    <Save className="w-3 h-3 mr-1" />
                    保存
                  </Button>
                </div>
                <div className="space-y-1 max-h-24 overflow-y-auto">
                  {optimizationPresets.map((preset) => (
                    <div
                      key={preset.id}
                      className="p-2 bg-primary-700 rounded-sm cursor-pointer hover:bg-primary-600 flex items-center justify-between"
                      onClick={() => handleLoadPreset(preset)}
                    >
                      <div>
                        <div className="text-xs font-medium">{preset.name}</div>
                        <div className="text-xs text-neutral-400">
                          {preset.usage_count}次使用 • 评分: {preset.performance_score}/10
                        </div>
                      </div>
                      {preset.is_favorite && (
                        <Sparkles className="w-3 h-3 text-yellow-400" />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* High-res Fix */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Zap className="w-4 h-4 text-accent-400" />
                  <label className="text-xs text-neutral-400">高分辨率修复</label>
                </div>
                <Button
                  variant={hiresFixEnabled ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setHiresFixEnabled(!hiresFixEnabled)}
                  className="h-6 px-2 text-xs"
                >
                  {hiresFixEnabled ? 'ON' : 'OFF'}
                </Button>
              </div>
              
              {hiresFixEnabled && (
                <div className="space-y-2 pl-6">
                  <div className="space-y-1">
                    <label className="text-xs text-neutral-400">放大倍数</label>
                    <select
                      value={upscaleFactor}
                      onChange={(e) => setUpscaleFactor(parseInt(e.target.value))}
                      className="w-full h-7 px-2 bg-primary-700 border border-primary-600 rounded-sm text-xs"
                    >
                      <option value={1.5}>1.5x</option>
                      <option value={2}>2x</option>
                      <option value={4}>4x</option>
                    </select>
                  </div>
                  
                  <div className="space-y-1">
                    <label className="text-xs text-neutral-400">去噪强度</label>
                    <Slider
                      value={[denoiseStrength]}
                      onValueChange={([value]) => setDenoiseStrength(value)}
                      max={1.0}
                      min={0.1}
                      step={0.1}
                      className="w-full"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Noise Injection */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Shield className="w-4 h-4 text-accent-400" />
                  <label className="text-xs text-neutral-400">噪声注入</label>
                </div>
                <Button
                  variant={noiseInjection ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setNoiseInjection(!noiseInjection)}
                  className="h-6 px-2 text-xs"
                >
                  {noiseInjection ? 'ON' : 'OFF'}
                </Button>
              </div>
              
              {noiseInjection && (
                <div className="space-y-1 pl-6">
                  <label className="text-xs text-neutral-400">噪声强度</label>
                  <Slider
                    value={[noiseStrength]}
                    onValueChange={([value]) => setNoiseStrength(value)}
                    max={0.5}
                    min={0.0}
                    step={0.05}
                    className="w-full"
                  />
                </div>
              )}
            </div>

            {/* Seed Enhancement */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-4 h-4 text-accent-400" />
                  <label className="text-xs text-neutral-400">种子增强</label>
                </div>
                <Button
                  variant={seedEnhance ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setSeedEnhance(!seedEnhance)}
                  className="h-6 px-2 text-xs"
                >
                  {seedEnhance ? 'ON' : 'OFF'}
                </Button>
              </div>
              
              {seedEnhance && (
                <div className="space-y-1 pl-6">
                  <label className="text-xs text-neutral-400">增强强度</label>
                  <Slider
                    value={[seedEnhanceStrength]}
                    onValueChange={([value]) => setSeedEnhanceStrength(value)}
                    max={0.5}
                    min={0.0}
                    step={0.05}
                    className="w-full"
                  />
                </div>
              )}
            </div>

            {/* AI Upscaling */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">AI 放大</label>
                {loading && (
                  <RefreshCw className="w-4 h-4 animate-spin text-neutral-400" />
                )}
              </div>
              {upscalingMethods.length === 0 ? (
                <div className="text-center py-2 text-xs text-neutral-400">
                  加载中...
                </div>
              ) : (
                <select
                  value={selectedUpscale}
                  onChange={(e) => setSelectedUpscale(e.target.value)}
                  className="w-full h-8 px-2 bg-primary-700 border border-primary-600 rounded-sm text-sm"
                >
                  <option value="none">无</option>
                  {upscalingMethods.map((method) => (
                    <option key={method.id} value={method.id}>
                      {method.name} (质量:{method.quality_rating}/10 速度:{method.speed_rating}/10)
                    </option>
                  ))}
                </select>
              )}
              
              {selectedUpscale !== 'none' && (
                <div className="space-y-1">
                  <label className="text-xs text-neutral-400">放大倍数</label>
                  <select
                    value={upscaleFactor}
                    onChange={(e) => setUpscaleFactor(parseInt(e.target.value))}
                    className="w-full h-7 px-2 bg-primary-700 border border-primary-600 rounded-sm text-xs"
                  >
                    <option value={2}>2x</option>
                    <option value={4}>4x</option>
                    <option value={8}>8x</option>
                  </select>
                  
                  {/* 显示选中的放大方法详细信息 */}
                  {upscalingMethods.length > 0 && (
                    <div className="p-2 bg-primary-700 rounded-sm">
                      <div className="text-xs space-y-1">
                        {(() => {
                          const method = upscalingMethods.find(m => m.id === selectedUpscale)
                          if (!method) return null
                          return (
                            <>
                              <div className="text-neutral-400">{method.description}</div>
                              <div className="flex justify-between">
                                <span className="text-neutral-400">内存使用:</span>
                                <span className={`text-xs px-1 rounded ${
                                  method.memory_usage === 'low' ? 'bg-green-500/20 text-green-400' :
                                  method.memory_usage === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                                  'bg-red-500/20 text-red-400'
                                }`}>
                                  {method.memory_usage}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-neutral-400">推荐用途:</span>
                                <span className="text-neutral-300">{method.recommended_for.join(', ')}</span>
                              </div>
                            </>
                          )
                        })()}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Style Filters */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">风格滤镜</label>
                {loading && (
                  <RefreshCw className="w-4 h-4 animate-spin text-neutral-400" />
                )}
              </div>
              {styleFilters.length === 0 ? (
                <div className="text-center py-2 text-xs text-neutral-400">
                  加载中...
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-1">
                  {styleFilters.map((filter) => (
                    <Button
                      key={filter.id}
                      variant={selectedFilter === filter.id ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => setSelectedFilter(filter.id)}
                      className="text-xs h-6 justify-start"
                    >
                      <div className="text-left">
                        <div>{filter.name}</div>
                        <div className="text-xs opacity-60">
                          {filter.processing_time}s • {filter.type}
                        </div>
                      </div>
                    </Button>
                  ))}
                </div>
              )}
              
              {/* 显示选中的滤镜详细信息 */}
              {selectedFilter !== 'none' && styleFilters.length > 0 && (
                <div className="p-2 bg-primary-700 rounded-sm">
                  <div className="text-xs space-y-1">
                    {(() => {
                      const filter = styleFilters.find(f => f.id === selectedFilter)
                      if (!filter) return null
                      return (
                        <>
                          <div className="text-neutral-400">{filter.description}</div>
                          <div className="flex justify-between">
                            <span className="text-neutral-400">强度:</span>
                            <span className="text-neutral-300">{(filter.intensity * 100).toFixed(0)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-neutral-400">预览:</span>
                            <span className={filter.preview_available ? 'text-green-400' : 'text-red-400'}>
                              {filter.preview_available ? '可用' : '不可用'}
                            </span>
                          </div>
                        </>
                      )
                    })()}
                  </div>
                </div>
              )}
            </div>

            {/* Refiner */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">细化器</label>
                <Button
                  variant={refinerEnabled ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setRefinerEnabled(!refinerEnabled)}
                  className="h-6 px-2 text-xs"
                >
                  {refinerEnabled ? 'ON' : 'OFF'}
                </Button>
              </div>
            </div>

            {/* Performance Settings */}
            <div className="pt-2 border-t border-primary-600">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-neutral-400 font-medium">性能设置</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={togglePerformanceMonitoring}
                  className="h-6 px-2 text-xs"
                >
                  <Cpu className="w-3 h-3 mr-1" />
                  {performanceMonitoring ? '停止监控' : '性能监控'}
                </Button>
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-neutral-400">FlashAttention2</span>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                    <span className="text-xs text-green-400">已启用</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-neutral-400">xFormers</span>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                    <span className="text-xs text-green-400">已启用</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-neutral-400">CUDA 加速</span>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                    <span className="text-xs text-green-400">已启用</span>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-neutral-400">批处理优化</span>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-yellow-400 rounded-full"></div>
                    <span className="text-xs text-yellow-400">部分启用</span>
                  </div>
                </div>
              </div>
            </div>

            {/* 高级选项 */}
            {showAdvanced && (
              <div className="pt-2 border-t border-primary-600">
                <div className="space-y-2">
                  <label className="text-xs text-neutral-400 font-medium">高级优化</label>
                  
                  {/* 批量处理设置 */}
                  <div className="space-y-1">
                    <label className="text-xs text-neutral-400">批处理大小</label>
                    <Slider
                      value={[config.batchSize || 1]}
                      onValueChange={([value]) => updateConfig({ batchSize: value })}
                      max={8}
                      min={1}
                      step={1}
                      className="w-full"
                    />
                    <span className="text-xs text-neutral-500">
                      当前: {config.batchSize || 1} (内存使用: {((config.batchSize || 1) * 2.5).toFixed(1)}GB)
                    </span>
                  </div>

                  {/* 并行处理 */}
                  <div className="space-y-1">
                    <label className="text-xs text-neutral-400">并行任务数</label>
                    <Slider
                      value={[config.parallelTasks || 2]}
                      onValueChange={([value]) => updateConfig({ parallelTasks: value })}
                      max={8}
                      min={1}
                      step={1}
                      className="w-full"
                    />
                    <span className="text-xs text-neutral-500">
                      当前: {config.parallelTasks || 2} 线程
                    </span>
                  </div>

                  {/* 缓存优化 */}
                  <div className="space-y-1">
                    <label className="text-xs text-neutral-400">模型缓存大小</label>
                    <select
                      value={config.cacheSize || '4GB'}
                      onChange={(e) => updateConfig({ cacheSize: e.target.value })}
                      className="w-full h-7 px-2 bg-primary-700 border border-primary-600 rounded-sm text-xs"
                    >
                      <option value="2GB">2GB</option>
                      <option value="4GB">4GB</option>
                      <option value="8GB">8GB</option>
                      <option value="16GB">16GB</option>
                    </select>
                  </div>
                </div>
              </div>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}