import React, { useState, useEffect, useRef } from 'react'
import { Upload, Eye, EyeOff, RefreshCw, AlertCircle, Image as ImageIcon } from 'lucide-react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../ui/accordion'
import { Slider } from '../ui/slider'
import { useGenerationContext } from '../../contexts/GenerationContext'
import { ModuleType } from '../../contexts/ModuleContext'
import { GenerationService } from '../../services/api'

interface ControlNetPanelProps {
  currentModule: ModuleType
}

interface Preprocessor {
  id: string
  name: string
  description: string
  type: 'edge' | 'depth' | 'pose' | 'scribble' | 'mlsd' | 'normal' | 'seg'
  enabled: boolean
}

interface ControlNetModel {
  id: string
  name: string
  size: string
  description: string
  supported_preprocessors: string[]
  resolution: string
  download_count?: number
}

interface ProcessedImage {
  url: string
  type: string
  width: number
  height: number
}

export const ControlNetPanel: React.FC<ControlNetPanelProps> = ({ currentModule }) => {
  const { config, updateConfig } = useGenerationContext()
  const [selectedPreprocessor, setSelectedPreprocessor] = useState('canny')
  const [preprocessors, setPreprocessors] = useState<Preprocessor[]>([])
  const [controlnetModels, setControlnetModels] = useState<ControlNetModel[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [referenceImage, setReferenceImage] = useState<File | null>(null)
  const [processedImage, setProcessedImage] = useState<ProcessedImage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [previewEnabled, setPreviewEnabled] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 获取可用的预处理器和模型列表
  const loadControlNetData = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const [processorsData, modelsData] = await Promise.all([
        GenerationService.getControlNetPreprocessors(),
        GenerationService.getControlNetModels()
      ])
      
      setPreprocessors(processorsData)
      setControlnetModels(modelsData)
      
      // 设置默认选中的模型
      if (modelsData.length > 0) {
        setSelectedModel(modelsData[0].id)
      }
    } catch (err) {
      console.error('Failed to load ControlNet data:', err)
      setError('加载ControlNet数据失败，请稍后重试')
      // 使用备用数据
      setPreprocessors([
        { id: 'canny', name: 'Canny Edge', description: 'Edge detection', type: 'edge', enabled: true },
        { id: 'depth', name: 'Depth', description: 'Depth map', type: 'depth', enabled: true },
        { id: 'pose', name: 'OpenPose', description: 'Body pose', type: 'pose', enabled: true },
        { id: 'scribble', name: 'Scribble', description: 'Hand drawn', type: 'scribble', enabled: true },
        { id: 'mlsd', name: 'MLSD', description: 'Line detection', type: 'mlsd', enabled: true }
      ])
      setControlnetModels([
        { id: 'cn1', name: 'ControlNet v1.1', size: '1.4GB', description: 'Standard ControlNet model', supported_preprocessors: ['canny', 'depth', 'pose'], resolution: '512x512' },
        { id: 'cn2', name: 'ControlNet XL', size: '1.8GB', description: 'High-resolution ControlNet', supported_preprocessors: ['canny', 'depth', 'pose', 'scribble'], resolution: '1024x1024' }
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadControlNetData()
  }, [currentModule])

  // 文件上传处理
  const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      setReferenceImage(file)
      setUploadProgress(0)
      
      if (previewEnabled && selectedPreprocessor) {
        // 自动预处理图像
        await processImage(file, selectedPreprocessor)
      }
    } catch (err) {
      console.error('Failed to process image:', err)
      setError('图像处理失败，请检查文件格式')
    }
  }

  // 图像预处理
  const processImage = async (file: File, preprocessorType: string) => {
    try {
      setLoading(true)
      setError(null)
      
      const result = await GenerationService.processControlNetImage(file, preprocessorType)
      
      if (result.success) {
        setProcessedImage(result.data)
      } else {
        setError(result.error || '图像预处理失败')
      }
    } catch (err) {
      console.error('Failed to process ControlNet image:', err)
      setError('图像预处理失败')
    } finally {
      setLoading(false)
    }
  }

  // 预览控制
  const togglePreview = () => {
    setPreviewEnabled(!previewEnabled)
    if (!previewEnabled && referenceImage && selectedPreprocessor) {
      processImage(referenceImage, selectedPreprocessor)
    }
  }

  return (
    <Accordion type="single" defaultValue="controlnet" className="w-full">
      <AccordionItem value="controlnet" className="border border-primary-600 rounded-sm">
        <AccordionTrigger className="px-3 py-2 hover:bg-primary-700">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium">ControlNet 模组</span>
              <Button
                variant={config.controlnetEnabled ? 'default' : 'ghost'}
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  updateConfig({ controlnetEnabled: !config.controlnetEnabled })
                }}
                className="h-5 px-2 text-xs"
              >
                {config.controlnetEnabled ? 'ON' : 'OFF'}
              </Button>
            </div>
            <div className="flex items-center space-x-1">
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={loadControlNetData}
                disabled={loading}
                title="刷新ControlNet数据"
              >
                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
              </Button>
              <label className="cursor-pointer">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleImageUpload}
                  className="hidden"
                />
                <Button variant="ghost" size="icon" className="h-6 w-6" title="上传参考图像">
                  <Upload className="w-3 h-3" />
                </Button>
              </label>
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-6 w-6"
                onClick={togglePreview}
                title={previewEnabled ? "关闭预览" : "开启预览"}
              >
                {previewEnabled ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
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

            {/* 上传进度 */}
            {uploadProgress > 0 && uploadProgress < 100 && (
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-neutral-400">处理中...</span>
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
            {config.controlnetEnabled && (
              <>
                {/* Reference Image */}
                <div className="space-y-2">
                  <label className="text-xs text-neutral-400">参考图像</label>
                  {referenceImage ? (
                    <div className="space-y-2">
                      <div className="relative w-full h-32 bg-primary-700 rounded-sm overflow-hidden">
                        {processedImage && previewEnabled ? (
                          <img 
                            src={processedImage.url} 
                            alt="预处理结果"
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <img 
                            src={URL.createObjectURL(referenceImage)} 
                            alt="参考图像"
                            className="w-full h-full object-cover"
                          />
                        )}
                        {loading && (
                          <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                            <RefreshCw className="w-6 h-6 animate-spin text-white" />
                          </div>
                        )}
                      </div>
                      <div className="flex justify-between items-center text-xs text-neutral-400">
                        <span>{referenceImage.name}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setReferenceImage(null)
                            setProcessedImage(null)
                          }}
                          className="h-6 px-2"
                        >
                          清除
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <label 
                      className="w-full h-24 bg-primary-700 rounded-sm border-2 border-dashed border-primary-600 flex items-center justify-center cursor-pointer hover:bg-primary-600 transition-colors"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <div className="text-center">
                        <ImageIcon className="w-6 h-6 text-neutral-400 mx-auto mb-1" />
                        <span className="text-xs text-neutral-400">拖拽或点击上传</span>
                        <span className="text-xs text-neutral-500 block mt-1">支持 JPG, PNG, WebP</span>
                      </div>
                    </label>
                  )}
                </div>

                {/* Preprocessor Selection */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-neutral-400">预处理类型</label>
                    {loading && (
                      <RefreshCw className="w-4 h-4 animate-spin text-neutral-400" />
                    )}
                  </div>
                  <div className="space-y-1">
                    {preprocessors.length === 0 ? (
                      <div className="text-center py-4 text-xs text-neutral-400">
                        加载中...
                      </div>
                    ) : (
                      preprocessors.map((processor) => (
                        <Button
                          key={processor.id}
                          variant={selectedPreprocessor === processor.id ? 'default' : 'ghost'}
                          size="sm"
                          onClick={() => {
                            setSelectedPreprocessor(processor.id)
                            if (referenceImage && previewEnabled) {
                              processImage(referenceImage, processor.id)
                            }
                          }}
                          className={`w-full justify-start h-8 text-xs ${
                            selectedPreprocessor === processor.id ? 'bg-accent-500' : ''
                          }`}
                          disabled={!processor.enabled}
                        >
                          <div className="text-left">
                            <div className="flex items-center space-x-2">
                              <span>{processor.name}</span>
                              <span className="text-xs px-1.5 py-0.5 bg-primary-600 rounded">
                                {processor.type}
                              </span>
                            </div>
                            <div className="text-xs opacity-60">{processor.description}</div>
                          </div>
                        </Button>
                      ))
                    )}
                  </div>
                </div>

                {/* Strength Control */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-neutral-400">控制权重</label>
                    <span className="text-xs text-neutral-300">
                      {config.controlnetStrength.toFixed(2)}
                    </span>
                  </div>
                  <Slider
                    value={[config.controlnetStrength]}
                    onValueChange={([value]) => updateConfig({ controlnetStrength: value })}
                    max={2.0}
                    min={0.0}
                    step={0.1}
                    className="w-full"
                  />
                </div>

                {/* Model Selection */}
                <div className="space-y-2">
                  <label className="text-xs text-neutral-400">ControlNet 模型</label>
                  <div className="space-y-1">
                    {controlnetModels.length === 0 ? (
                      <div className="text-center py-4 text-xs text-neutral-400">
                        加载中...
                      </div>
                    ) : (
                      controlnetModels.map((model) => (
                        <div
                          key={model.id}
                          className={`p-2 rounded-sm cursor-pointer transition-colors ${
                            selectedModel === model.id 
                              ? 'bg-accent-500/20 border border-accent-500/30' 
                              : 'bg-primary-700 hover:bg-primary-600'
                          }`}
                          onClick={() => setSelectedModel(model.id)}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-medium">{model.name}</span>
                            <span className="text-xs text-neutral-400">{model.size}</span>
                          </div>
                          <div className="text-xs text-neutral-400 mb-1">{model.description}</div>
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-neutral-500">分辨率: {model.resolution}</span>
                            <span className="text-xs text-neutral-500">
                              {model.supported_preprocessors.length} 个预处理器
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}

            {!config.controlnetEnabled && (
              <div className="text-center py-4 text-xs text-neutral-400">
                ControlNet 已禁用
              </div>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}