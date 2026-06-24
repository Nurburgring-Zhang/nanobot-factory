import React, { useState, useEffect } from 'react'
import { Sidebar } from './components/layout/Sidebar'
import { ParameterPanel } from './components/layout/ParameterPanel'
import { Workspace } from './components/layout/Workspace'
import { Header } from './components/layout/Header'
import { LocalAuth } from './components/auth/LocalAuth'
import { LocalAuthProvider, useLocalAuth } from './contexts/LocalAuthContext'
import { ModelProvider } from './contexts/ModelContext'
import { GenerationProvider } from './contexts/GenerationContext'
import { ModuleProvider } from './contexts/ModuleContext'
import { ModuleType } from './contexts/ModuleContext'
import './App.css'

// 主应用组件（只有在Supabase连接后才显示）
function MainApp() {
  const [currentModule, setCurrentModule] = useState<ModuleType>('image-gen')
  const [parameterPanelOpen, setParameterPanelOpen] = useState(true)
  const [sidebarExpanded, setSidebarExpanded] = useState(false)

  return (
    <ModuleProvider>
      <ModelProvider>
        <GenerationProvider>
          <div className="h-screen bg-primary-900 text-neutral-100 overflow-hidden">
            {/* Header */}
            <Header 
              parameterPanelOpen={parameterPanelOpen}
              setParameterPanelOpen={setParameterPanelOpen}
            />
            
            <div className="flex h-[calc(100vh-48px)]">
              {/* Sidebar */}
              <Sidebar 
                currentModule={currentModule}
                setCurrentModule={setCurrentModule}
                expanded={sidebarExpanded}
                setExpanded={setSidebarExpanded}
              />
              
              {/* Main Workspace */}
              <div className="flex-1 flex">
                <Workspace 
                  currentModule={currentModule}
                />
                
                {/* Parameter Panel */}
                {parameterPanelOpen && (
                  <ParameterPanel 
                    currentModule={currentModule}
                    onClose={() => setParameterPanelOpen(false)}
                  />
                )}
              </div>
            </div>
          </div>
        </GenerationProvider>
      </ModelProvider>
    </ModuleProvider>
  )
}

// 根组件
function App() {
  return (
    <LocalAuthProvider>
      <AppContent />
    </LocalAuthProvider>
  )
}

// 应用内容组件（检查本地认证状态）
function AppContent() {
  const { connection, isLoading } = useLocalAuth()

  // 如果正在加载，显示加载状态
  if (isLoading) {
    return (
      <div className="min-h-screen bg-primary-900 flex items-center justify-center">
        <div className="text-neutral-100 text-lg">加载中...</div>
      </div>
    )
  }

  // 如果没有连接到本地后端，显示本地登录页面
  if (!connection.isConnected) {
    return <LocalAuth />
  }

  // 如果已连接到本地后端，显示主应用
  return <MainApp />
}

export default App
