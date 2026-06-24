import React, { useState, useEffect } from 'react'
import { Shuffle, RefreshCw, AlertCircle, Save, Upload, Settings } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'
import { Slider } from '../ui/slider'
import { useGenerationContext } from '../../contexts/GenerationContext'
import { ModuleType } from '../../contexts/ModuleContext'
import { GenerationService } from '../../services/api'

interface ParametersPanelProps {
  currentModule: ModuleType
}

interface Sampler {
  id: string
  name: string
  description: string
  speed: 'fast' | 'medium' | 'slow'
  quality: 'draft' | 'standard' | 'high'
  memory_usage: 'low' | 'medium' | 'high'
}

interface Scheduler {
  id: string
  name: string
  description: string
  type: 'simple' | 'karras' | 'exponential' | 'polynomial' | 'sgm_uniform' | 'beta'
  stability: 'low' | 'medium' | 'high'
}

interface ParameterPreset {
  id: string
  name: string
  description: string
  module_type: ModuleType
  parameters: any
  created_at: string
  usage_count: number
  is_favorite: boolean
}

interface ParameterValidation {
  isValid: boolean
  errors: string[]
  warnings: string[]
}

export const ParametersPanel: React.FC<ParametersPanelProps> = ({ currentModule }) => {
  const { config, updateConfig } = useGenerationContext()
  const [samplers, setSamplers] = useState<Sampler[]>([])
  const [schedulers, setSchedulers] = useState<Scheduler[]>([])
  const [presets, setPresets] = useState<ParameterPreset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [validation, setValidation] = useState<ParameterValidation>({ isValid: true, errors: [], warnings: [] })

  // 获取可用的采样器和调度器列表
  const loadParametersData = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const [samplersData, schedulersData, presetsData] = await Promise.all([
        GenerationService.getSamplers(),
        GenerationService.getSchedulers(),
        GenerationService.getParameterPresets(currentModule)
      ])
      
      setSamplers(samplersData)
      setSchedulers(schedulersData)
      setPresets(presetsData)
      
      // 验证当前参数
      validateParameters(config)
    } catch (err) {
      console.error('Failed to load parameters data:', err)
      setError('加载参数数据失败，请稍后重试')
      // 使用备用数据
      setSamplers([
        { id: 'dpmpp_2m', name: 'DPM++ 2M', description: 'Fast and stable', speed: 'fast', quality: 'high', memory_usage: 'medium' },
        { id: 'dpmpp_2m_sde', name: 'DPM++ 2M SDE', description: 'High quality SDE', speed: 'medium', quality: 'high', memory_usage: 'high' },
        { id: 'euler', name: 'Euler', description: 'Simple and fast', speed: 'fast', quality: 'standard', memory_usage: 'low' },
        { id: 'euler_a', name: 'Euler Ancestral', description: 'More creative', speed: 'fast', quality: 'standard', memory_usage: 'low' },
        { id: 'lcm', name: 'LCM', description: 'Latent Consistency Model', speed: 'fast', quality: 'draft', memory_usage: 'low' }
      ])
      setSchedulers([
        { id: 'simple', name: 'Simple', description: 'Standard scheduler', type: 'simple', stability: 'medium' },
        { id: 'karras', name: 'Karras', description: 'Karras noise schedule', type: 'karras', stability: 'high' },
        { id: 'exponential', name: 'Exponential', description: 'Exponential decay', type: 'exponential', stability: 'medium' }
      ])
      setPresets([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadParametersData()
  }, [currentModule])

  // 参数验证
  const validateParameters = (params: any): ParameterValidation => {
    const errors: string[] = []
    const warnings: string[] = []

    if (params.steps < 1 || params.steps > 100) {
      errors.push('推理步数必须在1-100之间')
    }

    if (params.guidanceScale < 1 || params.guidanceScale > 20) {
      errors.push('CFG引导值必须在1-20之间')
    }

    if (params.steps > 50 && params.guidanceScale > 15) {
      warnings.push('高步数+高CFG可能导致过饱和')
    }

    if (params.steps < 10 && params.guidanceScale < 5) {
      warnings.push('低步数+低CFG可能导致质量下降')
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings
    }
  }

  // 随机种子生成
  const handleRandomSeed = () => {
    const randomSeed = Math.floor(Math.random() * 1000000000)
    updateConfig({ seed: randomSeed })
  }

  // 保存参数预设
  const handleSavePreset = async (name: string, description: string) => {
    try {
      setSaving(true)
      const result = await GenerationService.saveParameterPreset({
        name,
        description,
        module_type: currentModule,
        parameters: config
      })
      
      if (result.success) {
        await loadParametersData() // 重新加载预设列表
      } else {
        setError(result.error || '保存预设失败')
      }
    } catch (err) {
      console.error('Failed to save preset:', err)
      setError('保存预设失败')
    } finally {
      setSaving(false)
    }
  }

  // 加载参数预设
  const handleLoadPreset = async (preset: ParameterPreset) => {
    try {
      updateConfig(preset.parameters)
      await GenerationService.incrementPresetUsage(preset.id) // 增加使用次数
      await loadParametersData() // 重新加载预设列表（更新使用次数）
    } catch (err) {
      console.error('Failed to load preset:', err)
      setError('加载预设失败')
    }
  }

  return (
    <Accordion type="single" defaultValue="parameters" className="w-full">
      <AccordionItem value="parameters" className="border border-primary-600 rounded-sm">
        <AccordionTrigger className="px-3 py-2 hover:bg-primary-700">
          <div className="flex items-center justify-between w-full">
            <span className="text-sm font-medium">生图参数模组</span>
            <div className="flex items-center space-x-1">
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowAdvanced(!showAdvanced)
                }}
                title="切换高级参数"
              >
                <Settings className="w-3 h-3" />
              </Button>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={(e) => {
                  e.stopPropagation()
                  loadParametersData()
                }}
                disabled={loading}
                title="刷新参数数据"
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

            {/* 参数验证警告 */}
            {validation.warnings.length > 0 && (
              <div className="space-y-1">
                {validation.warnings.map((warning, index) => (
                  <div key={index} className="flex items-center space-x-2 p-2 bg-yellow-500/20 border border-yellow-500/30 rounded-sm">
                    <AlertCircle className="w-4 h-4 text-yellow-400" />
                    <span className="text-xs text-yellow-300">{warning}</span>
                  </div>
                ))}
              </div>
            )}

            {/* 参数预设 */}
            {presets.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs text-neutral-400">参数预设</label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const name = prompt('请输入预设名称:')
                      if (name) {
                        handleSavePreset(name, '')
                      }
                    }}
                    disabled={saving}
                    className="h-6 px-2 text-xs"
                  >
                    <Save className="w-3 h-3 mr-1" />
                    保存
                  </Button>
                </div>
                <div className="space-y-1 max-h-24 overflow-y-auto">
                  {presets.map((preset) => (
                    <div
                      key={preset.id}
                      className="p-2 bg-primary-700 rounded-sm cursor-pointer hover:bg-primary-600 flex items-center justify-between"
                      onClick={() => handleLoadPreset(preset)}
                    >
                      <div>
                        <div className="text-xs font-medium">{preset.name}</div>
                        <div className="text-xs text-neutral-400">
                          {preset.usage_count}次使用 • {preset.description}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* Steps */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">推理步数</label>
                <span className="text-xs text-neutral-300">{config.steps}</span>
              </div>
              <Slider
                value={[config.steps]}
                onValueChange={([value]) => updateConfig({ steps: value })}
                max={100}
                min={1}
                step={1}
                className="w-full"
              />
            </div>

            {/* CFG Scale */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">CFG 引导</label>
                <span className="text-xs text-neutral-300">{config.guidanceScale.toFixed(1)}</span>
              </div>
              <Slider
                value={[config.guidanceScale]}
                onValueChange={([value]) => updateConfig({ guidanceScale: value })}
                max={20}
                min={1}
                step={0.5}
                className="w-full"
              />
            </div>

            {/* Seed */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">随机种子</label>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={handleRandomSeed}
                >
                  <Shuffle className="w-3 h-3" />
                </Button>
              </div>
              <Input
                value={config.seed || ''}
                onChange={(e) => {
                  const value = e.target.value ? parseInt(e.target.value) : null
                  updateConfig({ seed: value })
                }}
                placeholder="自动生成"
                className="h-7 text-xs"
              />
            </div>

            {/* Sampler */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">采样器</label>
                {loading && (
                  <RefreshCw className="w-4 h-4 animate-spin text-neutral-400" />
                )}
              </div>
              {samplers.length === 0 ? (
                <div className="text-center py-2 text-xs text-neutral-400">
                  加载中...
                </div>
              ) : (
                <select
                  value={config.sampler}
                  onChange={(e) => {
                    updateConfig({ sampler: e.target.value })
                    validateParameters({ ...config, sampler: e.target.value })
                  }}
                  className="w-full h-8 px-2 bg-primary-700 border border-primary-600 rounded-sm text-sm text-neutral-100"
                >
                  {samplers.map((sampler) => (
                    <option key={sampler.id} value={sampler.id}>
                      {sampler.name} ({sampler.speed}/{sampler.quality})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Scheduler */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">调度器</label>
                {loading && (
                  <RefreshCw className="w-4 h-4 animate-spin text-neutral-400" />
                )}
              </div>
              {schedulers.length === 0 ? (
                <div className="text-center py-2 text-xs text-neutral-400">
                  加载中...
                </div>
              ) : (
                <select
                  value={config.scheduler}
                  onChange={(e) => {
                    updateConfig({ scheduler: e.target.value })
                    validateParameters({ ...config, scheduler: e.target.value })
                  }}
                  className="w-full h-8 px-2 bg-primary-700 border border-primary-600 rounded-sm text-sm text-neutral-100"
                >
                  {schedulers.map((scheduler) => (
                    <option key={scheduler.id} value={scheduler.id}>
                      {scheduler.name} ({scheduler.stability})
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* 高级参数 */}
            {showAdvanced && (
              <div className="space-y-3 border-t border-primary-600 pt-3">
                <label className="text-xs text-neutral-400 font-medium">高级参数</label>
                
                {/* 采样器特定参数 */}
                <div className="space-y-2">
                  <label className="text-xs text-neutral-400">采样器eta</label>
                  <Slider
                    value={[config.samplerEta || 0.0]}
                    onValueChange={([value]) => updateConfig({ samplerEta: value })}
                    max={1.0}
                    min={0.0}
                    step={0.1}
                    className="w-full"
                  />
                  <span className="text-xs text-neutral-500">
                    当前值: {config.samplerEta?.toFixed(1) || 0.0}
                  </span>
                </div>

                {/* 噪声控制 */}
                <div className="space-y-2">
                  <label className="text-xs text-neutral-400">噪声控制</label>
                  <Slider
                    value={[config.noiseScale || 0.1]}
                    onValueChange={([value]) => updateConfig({ noiseScale: value })}
                    max={1.0}
                    min={0.0}
                    step={0.1}
                    className="w-full"
                  />
                  <span className="text-xs text-neutral-500">
                    当前值: {config.noiseScale?.toFixed(1) || 0.1}
                  </span>
                </div>

                {/* 高级调度器参数 */}
                {config.scheduler === 'karras' && (
                  <div className="space-y-2">
                    <label className="text-xs text-neutral-400">Karras sigma_max</label>
                    <Slider
                      value={[config.karrasSigmaMax || 14.6146]}
                      onValueChange={([value]) => updateConfig({ karrasSigmaMax: value })}
                      max={20.0}
                      min={0.1}
                      step={0.1}
                      className="w-full"
                    />
                    <span className="text-xs text-neutral-500">
                      当前值: {config.karrasSigmaMax?.toFixed(1) || 14.6}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}