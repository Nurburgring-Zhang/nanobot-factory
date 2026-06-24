import React, { createContext, useContext, useState, ReactNode } from 'react'

export interface ModelConfig {
  id: string
  name: string
  type: 'checkpoint' | 'lora' | 'controlnet' | 'vae' | 'clip'
  path: string
  size?: string
  thumbnail?: string
  weight?: number
}

interface ModelContextType {
  currentCheckpoint: string
  setCurrentCheckpoint: (checkpoint: string) => void
  selectedModels: ModelConfig[]
  addModel: (model: ModelConfig) => void
  removeModel: (id: string) => void
  updateModelWeight: (id: string, weight: number) => void
}

const ModelContext = createContext<ModelContextType | undefined>(undefined)

interface ModelProviderProps {
  children: ReactNode
}

export const ModelProvider: React.FC<ModelProviderProps> = ({ children }) => {
  const [currentCheckpoint, setCurrentCheckpoint] = useState('')
  const [selectedModels, setSelectedModels] = useState<ModelConfig[]>([])

  const addModel = (model: ModelConfig) => {
    setSelectedModels(prev => [...prev, model])
  }

  const removeModel = (id: string) => {
    setSelectedModels(prev => prev.filter(model => model.id !== id))
  }

  const updateModelWeight = (id: string, weight: number) => {
    setSelectedModels(prev => 
      prev.map(model => 
        model.id === id ? { ...model, weight } : model
      )
    )
  }

  return (
    <ModelContext.Provider value={{
      currentCheckpoint,
      setCurrentCheckpoint,
      selectedModels,
      addModel,
      removeModel,
      updateModelWeight
    }}>
      {children}
    </ModelContext.Provider>
  )
}

export const useModelContext = () => {
  const context = useContext(ModelContext)
  if (context === undefined) {
    throw new Error('useModelContext must be used within a ModelProvider')
  }
  return context
}