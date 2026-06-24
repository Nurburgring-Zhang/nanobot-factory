import React, { useState, useRef } from 'react'
import { Upload, Shuffle, ArrowUpDown, Zap, Languages, AlertCircle, RefreshCw, FileText } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'
import { Slider } from '../ui/slider'
import { useGenerationContext } from '../../contexts/GenerationContext'
import { ModuleType } from '../../contexts/ModuleContext'

interface PromptPanelProps {
  currentModule: ModuleType
}

export const PromptPanel: React.FC<PromptPanelProps> = ({ currentModule }) => {
  const { config, updateConfig } = useGenerationContext()
  const [promptMode, setPromptMode] = useState<'manual' | 'batch'>('manual')
  const [batchMode, setBatchMode] = useState<'sequential' | 'random'>('sequential')
  const [positivePreset, setPositivePreset] = useState('')
  const [negativePreset, setNegativePreset] = useState('')
  const [translationEnabled, setTranslationEnabled] = useState(false)
  const [batchPrompts, setBatchPrompts] = useState<string[]>([])
  const [currentBatchIndex, setCurrentBatchIndex] = useState(0)
  const [optimizing, setOptimizing] = useState(false)
  const [translating, setTranslating] = useState(false)
  const [fileUploading, setFileUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const stylePresets = {
    positive: [
      { id: 'anime', name: 'Anime Style', prompt: 'anime style, high quality, detailed' },
      { id: 'realistic', name: 'Photorealistic', prompt: 'photorealistic, high resolution, detailed' },
      { id: 'cinematic', name: 'Cinematic', prompt: 'cinematic lighting, dramatic composition, movie quality' },
      { id: 'oil', name: 'Oil Painting', prompt: 'oil painting style, classical art, masterpiece' },
      { id: 'cyberpunk', name: 'Cyberpunk', prompt: 'cyberpunk style, neon lights, futuristic, dark atmosphere' }
    ],
    negative: [
      { id: 'basic', name: 'Basic', prompt: 'low quality, blurry, artifacts, distorted' },
      { id: 'nsfw', name: 'NSFW Filter', prompt: 'nsfw, inappropriate, unsafe for work' },
      { id: 'artifacts', name: 'No Artifacts', prompt: 'no artifacts, clean, smooth, perfect' }
    ]
  }

  // Handle preset selection
  const handlePresetSelect = (type: 'positive' | 'negative', preset: any) => {
    if (type === 'positive') {
      const combinedPrompt = `${preset.prompt}, ${config.prompt}`.trim()
      updateConfig({ prompt: combinedPrompt })
      setPositivePreset(preset.id)
    } else {
      const combinedNegative = `${preset.prompt}, ${config.negativePrompt}`.trim()
      updateConfig({ negativePrompt: combinedNegative })
      setNegativePreset(preset.id)
    }
  }

  // Handle file upload for batch prompts
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    setFileUploading(true)
    setError(null)

    try {
      const text = await file.text()
      const lines = text.split('\n').filter(line => line.trim())
      
      if (lines.length === 0) {
        throw new Error('文件中没有有效的提示词')
      }

      setBatchPrompts(lines)
      setCurrentBatchIndex(0)
      updateConfig({ prompt: lines[0] })
      
    } catch (err: any) {
      setError(err.message)
    } finally {
      setFileUploading(false)
      if (event.target) {
        event.target.value = ''
      }
    }
  }

  // Handle AI optimization
  const handleAIOptimization = async () => {
    if (!config.prompt.trim()) {
      setError('请先输入提示词')
      return
    }

    setOptimizing(true)
    setError(null)

    try {
      // 这里应该调用实际的AI优化API
      // 暂时模拟优化结果
      const optimizedPrompt = `[enhanced] ${config.prompt} [masterpiece, high quality, detailed]`
      
      // 模拟API调用延迟
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      updateConfig({ prompt: optimizedPrompt })
      
    } catch (err: any) {
      setError(err.message)
    } finally {
      setOptimizing(false)
    }
  }

  // Handle translation
  const handleTranslation = async () => {
    if (!config.prompt.trim()) {
      setError('请先输入提示词')
      return
    }

    setTranslating(true)
    setError(null)

    try {
      // 这里应该调用实际的翻译API
      // 暂时模拟翻译结果
      const translatedPrompt = `[中文] ${config.prompt}`
      
      // 模拟API调用延迟
      await new Promise(resolve => setTimeout(resolve, 800))
      
      updateConfig({ prompt: translatedPrompt })
      
    } catch (err: any) {
      setError(err.message)
    } finally {
      setTranslating(false)
    }
  }

  // Handle batch prompt navigation
  const handleBatchNavigation = (direction: 'prev' | 'next') => {
    if (direction === 'prev' && currentBatchIndex > 0) {
      const newIndex = currentBatchIndex - 1
      setCurrentBatchIndex(newIndex)
      updateConfig({ prompt: batchPrompts[newIndex] })
    } else if (direction === 'next' && currentBatchIndex < batchPrompts.length - 1) {
      const newIndex = currentBatchIndex + 1
      setCurrentBatchIndex(newIndex)
      updateConfig({ prompt: batchPrompts[newIndex] })
    }
  }

  // Random prompt selection
  const handleRandomPrompt = () => {
    if (batchPrompts.length > 0) {
      const randomIndex = Math.floor(Math.random() * batchPrompts.length)
      setCurrentBatchIndex(randomIndex)
      updateConfig({ prompt: batchPrompts[randomIndex] })
    }
  }

  const loadBatchPrompts = () => {
    // Mock batch loading - in real app, would open file dialog
    const mockPrompts = [
      "A beautiful landscape with mountains and lake",
      "A futuristic cityscape with flying cars",
      "A portrait of a warrior in armor",
      "A magical forest with glowing mushrooms"
    ]
    console.log('Loaded batch prompts:', mockPrompts)
  }

  return (
    <Accordion type="single" defaultValue="prompt" className="w-full">
      <AccordionItem value="prompt" className="border border-primary-600 rounded-sm">
        <AccordionTrigger className="px-3 py-2 hover:bg-primary-700">
          <div className="flex items-center justify-between w-full">
            <span className="text-sm font-medium">提示词模组</span>
            <div className="flex items-center space-x-1">
              <Button variant="ghost" size="icon" className="h-6 w-6">
                <Upload className="w-3 h-3" />
              </Button>
              <Button variant="ghost" size="icon" className="h-6 w-6">
                <Languages className="w-3 h-3" />
              </Button>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent className="px-0 pb-2">
          <div className="px-3 space-y-3">
            {/* Prompt Mode Toggle */}
            <div className="flex space-x-1">
              <Button
                variant={promptMode === 'manual' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setPromptMode('manual')}
                className="text-xs h-7 flex-1"
              >
                手动输入
              </Button>
              <Button
                variant={promptMode === 'batch' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setPromptMode('batch')}
                className="text-xs h-7 flex-1"
              >
                批量处理
              </Button>
            </div>

            {/* Positive Prompt */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs text-neutral-400">正向提示词</label>
                <Button variant="ghost" size="icon" className="h-6 w-6">
                  <Shuffle className="w-3 h-3" />
                </Button>
              </div>
              
              <textarea
                value={config.prompt}
                onChange={(e) => updateConfig({ prompt: e.target.value })}
                placeholder="描述你想要的图像..."
                className="w-full h-20 px-3 py-2 bg-primary-700 border border-primary-600 rounded-sm text-sm text-neutral-100 placeholder:text-neutral-400 resize-none focus:outline-none focus:ring-1 focus:ring-accent-500"
              />

              {/* Style Presets */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">风格预设</label>
                <div className="grid grid-cols-2 gap-1">
                  {stylePresets.positive.map((preset) => (
                    <Button
                      key={preset.id}
                      variant={positivePreset === preset.id ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => handlePresetSelect('positive', preset)}
                      className="text-xs h-6"
                    >
                      {preset.name}
                    </Button>
                  ))}
                </div>
              </div>
            </div>

            {/* Negative Prompt */}
            <div className="space-y-2">
              <label className="text-xs text-neutral-400">负向提示词</label>
              <textarea
                value={config.negativePrompt}
                onChange={(e) => updateConfig({ negativePrompt: e.target.value })}
                placeholder="不想要的元素..."
                className="w-full h-16 px-3 py-2 bg-primary-700 border border-primary-600 rounded-sm text-sm text-neutral-100 placeholder:text-neutral-400 resize-none focus:outline-none focus:ring-1 focus:ring-accent-500"
              />

              {/* Negative Presets */}
              <div className="space-y-1">
                <label className="text-xs text-neutral-400">负向预设</label>
                <div className="grid grid-cols-1 gap-1">
                  {stylePresets.negative.map((preset) => (
                    <Button
                      key={preset.id}
                      variant={negativePreset === preset.id ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => handlePresetSelect('negative', preset)}
                      className="text-xs h-6 justify-start"
                    >
                      {preset.name}
                    </Button>
                  ))}
                </div>
              </div>
            </div>

            {/* Advanced Options */}
            <div className="space-y-2 pt-2 border-t border-primary-600">
              <div className="flex items-center justify-between">
                <span className="text-xs text-neutral-400">AI 优化</span>
                <Button variant="ghost" size="icon" className="h-6 w-6">
                  <Zap className="w-3 h-3" />
                </Button>
              </div>
              
              <div className="flex items-center justify-between">
                <span className="text-xs text-neutral-400">本地翻译</span>
                <Button
                  variant={translationEnabled ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setTranslationEnabled(!translationEnabled)}
                  className="h-6 px-2 text-xs"
                >
                  {translationEnabled ? 'ON' : 'OFF'}
                </Button>
              </div>
            </div>

            {/* Batch Mode Options */}
            {promptMode === 'batch' && (
              <div className="space-y-2 pt-2 border-t border-primary-600">
                <div className="flex space-x-1">
                  <Button
                    variant={batchMode === 'sequential' ? 'default' : 'ghost'}
                    size="sm"
                    onClick={() => setBatchMode('sequential')}
                    className="text-xs h-7 flex-1"
                  >
                    <ArrowUpDown className="w-3 h-3 mr-1" />
                    顺序
                  </Button>
                  <Button
                    variant={batchMode === 'random' ? 'default' : 'ghost'}
                    size="sm"
                    onClick={() => setBatchMode('random')}
                    className="text-xs h-7 flex-1"
                  >
                    <Shuffle className="w-3 h-3 mr-1" />
                    随机
                  </Button>
                </div>
                
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadBatchPrompts}
                  className="w-full text-xs h-8"
                >
                  <Upload className="w-3 h-3 mr-1" />
                  加载提示词文件
                </Button>
              </div>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}