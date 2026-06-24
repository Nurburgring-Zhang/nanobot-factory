import React, { createContext, useContext, useState, ReactNode } from 'react'

export type GenerationStatus = 'idle' | 'generating' | 'completed' | 'error'

interface GenerationConfig {
  prompt: string
  negativePrompt: string
  steps: number
  guidanceScale: number
  seed: number | null
  width: number
  height: number
  sampler: string
  scheduler: string
  loraWeights: Record<string, number>
  controlnetEnabled: boolean
  controlnetStrength: number
  // 高级参数
  samplerEta?: number
  noiseScale?: number
  karrasSigmaMax?: number
  // 优化参数
  batchSize?: number
  parallelTasks?: number
  cacheSize?: string
}

interface GenerationContextType {
  status: GenerationStatus
  progress: number
  setStatus: (status: GenerationStatus) => void
  setProgress: (progress: number) => void
  config: GenerationConfig
  updateConfig: (updates: Partial<GenerationConfig>) => void
  lastResult: string | null
  setLastResult: (result: string | null) => void
  error: string | null
  setError: (error: string | null) => void
}

const GenerationContext = createContext<GenerationContextType | undefined>(undefined)

interface GenerationProviderProps {
  children: ReactNode
}

const defaultConfig: GenerationConfig = {
  prompt: '',
  negativePrompt: 'low quality, blurry, artifacts',
  steps: 20,
  guidanceScale: 7.5,
  seed: null,
  width: 512,
  height: 512,
  sampler: 'dpmpp_2m',
  scheduler: 'simple',
  loraWeights: {},
  controlnetEnabled: false,
  controlnetStrength: 0.8,
  // 高级参数默认值
  samplerEta: 0.0,
  noiseScale: 0.1,
  karrasSigmaMax: 14.6,
  // 优化参数默认值
  batchSize: 1,
  parallelTasks: 2,
  cacheSize: '4GB'
}

export const GenerationProvider: React.FC<GenerationProviderProps> = ({ children }) => {
  const [status, setStatus] = useState<GenerationStatus>('idle')
  const [progress, setProgress] = useState(0)
  const [config, setConfig] = useState<GenerationConfig>(defaultConfig)
  const [lastResult, setLastResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const updateConfig = (updates: Partial<GenerationConfig>) => {
    setConfig(prev => ({ ...prev, ...updates }))
  }

  return (
    <GenerationContext.Provider value={{
      status,
      progress,
      setStatus,
      setProgress,
      config,
      updateConfig,
      lastResult,
      setLastResult,
      error,
      setError
    }}>
      {children}
    </GenerationContext.Provider>
  )
}

export const useGenerationContext = () => {
  const context = useContext(GenerationContext)
  if (context === undefined) {
    throw new Error('useGenerationContext must be used within a GenerationProvider')
  }
  return context
}