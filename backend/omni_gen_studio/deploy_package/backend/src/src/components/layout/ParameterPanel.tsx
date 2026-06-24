import React from 'react'
import { X } from 'lucide-react'
import { Button } from '../ui/button'
import { ModelPanel } from '../parameters/ModelPanel'
import { PromptPanel } from '../parameters/PromptPanel'
import { LoRAPanel } from '../parameters/LoRAPanel'
import { ControlNetPanel } from '../parameters/ControlNetPanel'
import { ParametersPanel } from '../parameters/ParametersPanel'
import { ResolutionPanel } from '../parameters/ResolutionPanel'
import { OptimizationPanel } from '../parameters/OptimizationPanel'
import { ModuleType } from '../../contexts/ModuleContext'

interface ParameterPanelProps {
  currentModule: ModuleType
  onClose: () => void
}

const parameterModules = [
  { id: 'model', name: 'Model', component: ModelPanel },
  { id: 'prompt', name: 'Prompt', component: PromptPanel },
  { id: 'lora', name: 'LoRA', component: LoRAPanel },
  { id: 'controlnet', name: 'ControlNet', component: ControlNetPanel },
  { id: 'parameters', name: 'Parameters', component: ParametersPanel },
  { id: 'resolution', name: 'Resolution', component: ResolutionPanel },
  { id: 'optimization', name: 'Optimization', component: OptimizationPanel }
]

export const ParameterPanel: React.FC<ParameterPanelProps> = ({ 
  currentModule, 
  onClose 
}) => {
  return (
    <div className="w-panel-width bg-primary-800 border-l border-primary-600 flex flex-col">
      {/* Panel Header */}
      <div className="h-12 bg-primary-700 border-b border-primary-600 flex items-center justify-between px-3">
        <h3 className="text-sm font-semibold text-neutral-100">
          {currentModule === 'image-gen' && 'Image Generation'}
          {currentModule === 'image-edit' && 'Image Editing'}
          {currentModule === 'video-gen' && 'Video Generation'}
          {currentModule === '3d-gen' && '3D Generation'}
        </h3>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={onClose}
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Parameter Modules */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-2 space-y-1">
          {parameterModules.map((module) => {
            const Component = module.component
            return (
              <div key={module.id} className="mb-3">
                <Component currentModule={currentModule} />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}