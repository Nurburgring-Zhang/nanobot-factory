import React from 'react'
import { 
  Image, 
  Edit3, 
  Video, 
  Box, 
  Folder, 
  Settings,
  Plus,
  MoreHorizontal 
} from 'lucide-react'
import { Button } from '../ui/button'
import { ModuleType } from '../../contexts/ModuleContext'

interface SidebarProps {
  currentModule: ModuleType
  setCurrentModule: (module: ModuleType) => void
  expanded: boolean
  setExpanded: (expanded: boolean) => void
}

const modules = [
  {
    id: 'image-gen' as ModuleType,
    name: 'Image Generation',
    icon: Image,
    description: 'Text-to-Image & Image-to-Image'
  },
  {
    id: 'image-edit' as ModuleType,
    name: 'Image Editing',
    icon: Edit3,
    description: 'Inpaint & Outpaint'
  },
  {
    id: 'video-gen' as ModuleType,
    name: 'Video Generation',
    icon: Video,
    description: 'Text-to-Video & I2V'
  },
  {
    id: '3d-gen' as ModuleType,
    name: '3D Generation',
    icon: Box,
    description: 'Text-to-3D & I2-3D'
  }
]

export const Sidebar: React.FC<SidebarProps> = ({ 
  currentModule, 
  setCurrentModule, 
  expanded, 
  setExpanded 
}) => {
  return (
    <div className={`bg-primary-800 border-r border-primary-600 transition-all duration-200 ${
      expanded ? 'w-sidebar-expanded' : 'w-sidebar-width'
    } flex flex-col`}>
      {/* Sidebar Header */}
      <div className="p-2 border-b border-primary-600">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => setExpanded(!expanded)}
        >
          <MoreHorizontal className="w-4 h-4" />
        </Button>
      </div>

      {/* Module Navigation */}
      <nav className="flex-1 py-2">
        {modules.map((module) => {
          const Icon = module.icon
          const isActive = currentModule === module.id
          
          return (
            <button
              key={module.id}
              onClick={() => setCurrentModule(module.id)}
              className={`w-full flex items-center px-3 py-2 mx-2 mb-1 rounded-sm transition-all duration-200 group ${
                isActive 
                  ? 'bg-accent-500/20 text-accent-400 border-l-3 border-accent-500' 
                  : 'text-neutral-400 hover:bg-primary-700 hover:text-neutral-100'
              }`}
              title={!expanded ? module.name : undefined}
            >
              <Icon className={`w-5 h-5 flex-shrink-0 ${
                isActive ? 'text-accent-400' : 'text-neutral-400 group-hover:text-neutral-100'
              }`} />
              
              {expanded && (
                <div className="ml-3 text-left overflow-hidden">
                  <div className={`text-sm font-medium ${
                    isActive ? 'text-accent-400' : 'text-neutral-100'
                  }`}>
                    {module.name}
                  </div>
                  <div className="text-xs text-neutral-400 truncate">
                    {module.description}
                  </div>
                </div>
              )}
            </button>
          )
        })}
      </nav>

      {/* Project Management */}
      <div className="border-t border-primary-600 p-2">
        <Button
          variant="ghost"
          size="icon"
          className="w-full h-8 text-neutral-400 hover:text-neutral-100 hover:bg-primary-700"
          title={!expanded ? 'New Project' : undefined}
        >
          <Plus className="w-4 h-4" />
          {expanded && <span className="ml-2 text-sm">New Project</span>}
        </Button>
        
        <Button
          variant="ghost"
          size="icon"
          className="w-full h-8 text-neutral-400 hover:text-neutral-100 hover:bg-primary-700"
          title={!expanded ? 'Projects' : undefined}
        >
          <Folder className="w-4 h-4" />
          {expanded && <span className="ml-2 text-sm">Projects</span>}
        </Button>
        
        <Button
          variant="ghost"
          size="icon"
          className="w-full h-8 text-neutral-400 hover:text-neutral-100 hover:bg-primary-700"
          title={!expanded ? 'Settings' : undefined}
        >
          <Settings className="w-4 h-4" />
          {expanded && <span className="ml-2 text-sm">Settings</span>}
        </Button>
      </div>
    </div>
  )
}