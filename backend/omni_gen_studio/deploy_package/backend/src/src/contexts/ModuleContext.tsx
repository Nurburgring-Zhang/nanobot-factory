import React, { createContext, useContext, useState, ReactNode } from 'react'

export type ModuleType = 'image-gen' | 'image-edit' | 'video-gen' | '3d-gen'

export default ModuleType

interface ModuleContextType {
  currentModule: ModuleType
  setCurrentModule: (module: ModuleType) => void
}

const ModuleContext = createContext<ModuleContextType | undefined>(undefined)

interface ModuleProviderProps {
  children: ReactNode
}

export const ModuleProvider: React.FC<ModuleProviderProps> = ({ children }) => {
  const [currentModule, setCurrentModule] = useState<ModuleType>('image-gen')

  return (
    <ModuleContext.Provider value={{ currentModule, setCurrentModule }}>
      {children}
    </ModuleContext.Provider>
  )
}

export const useModuleContext = () => {
  const context = useContext(ModuleContext)
  if (context === undefined) {
    throw new Error('useModuleContext must be used within a ModuleProvider')
  }
  return context
}