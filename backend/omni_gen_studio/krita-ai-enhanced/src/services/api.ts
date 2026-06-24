// General AIGC Enhanced - Frontend API Service
// 前端与本地后端API集成服务

// 本地API配置
const API_BASE_URL = 'http://127.0.0.1:8000'

// 本地存储键名
const TOKEN_KEY = 'aigc_local_token'
const USER_KEY = 'aigc_local_user'

// 获取存储的token
const getStoredToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY)
}

// 获取当前用户信息
const getCurrentUser = () => {
  const userStr = localStorage.getItem(USER_KEY)
  return userStr ? JSON.parse(userStr) : null
}

// 存储用户信息和token
const storeAuthData = (user: any, token: string) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
  localStorage.setItem(TOKEN_KEY, token)
}

// API响应类型定义
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

export interface GenerationTask {
  id: string
  user_id: string
  project_id?: string
  module_type: 'image-gen' | 'image-edit' | 'video-gen' | '3d-gen'
  prompt: string
  negative_prompt?: string
  model_config: any
  parameters: any
  input_files?: string[]
  output_files?: string[]
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  completed_at?: string
  progress?: number
  elapsedTime?: number
  estimatedTimeRemaining?: number
  canRetry?: boolean
  canCancel?: boolean
}

export interface ModelConfig {
  id: string
  user_id: string
  name: string
  type: 'checkpoint' | 'lora' | 'controlnet' | 'vae' | 'clip'
  path: string
  weight?: number
  size?: string
  thumbnail?: string
  is_active: boolean
  created_at: string
  description?: string
}

export interface LoRAModel {
  id: string
  name: string
  category: string
  weight: number
  description?: string
  tags?: string[]
  download_count?: number
  size?: string
  thumbnail?: string
  author?: string
  version?: string
  created_at?: string
  updated_at?: string
}

// 本地认证服务
export class AuthService {
  private static async makeRequest(url: string, options: RequestInit = {}): Promise<any> {
    const token = getStoredToken()
    
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers
    }

    try {
      const response = await fetch(`${API_BASE_URL}${url}`, {
        ...options,
        headers
      })

      const result = await response.json()
      
      if (!response.ok) {
        throw new Error(result.detail || result.error || '请求失败')
      }

      return result
    } catch (error: any) {
      throw new Error(error.message)
    }
  }

  static async signUp(email: string, password: string, username: string): Promise<ApiResponse> {
    try {
      const response = await this.makeRequest('/api/auth/signup', {
        method: 'POST',
        body: JSON.stringify({ email, password, username })
      })

      if (response.success) {
        storeAuthData(response.data.user, response.data.token)
        return { success: true, data: response.data, message: response.message }
      }

      return { success: false, error: '注册失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async signIn(email: string, password: string): Promise<ApiResponse> {
    try {
      const response = await this.makeRequest('/api/auth/signin', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      })

      if (response.success) {
        storeAuthData(response.data.user, response.data.token)
        return { success: true, data: response.data, message: response.message }
      }

      return { success: false, error: '登录失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async signOut(): Promise<ApiResponse> {
    try {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      return { success: true, message: '已退出登录' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async getCurrentUser() {
    return getCurrentUser()
  }

  static isAuthenticated(): boolean {
    return !!getStoredToken() && !!getCurrentUser()
  }

  static getToken(): string | null {
    return getStoredToken()
  }
}

// 本地AI生成服务
export class GenerationService {
  static baseUrl = API_BASE_URL
  
  private static async makeRequest(url: string, options: RequestInit = {}): Promise<any> {
    const token = getStoredToken()
    
    if (!token) {
      throw new Error('用户未登录')
    }

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers
    }

    try {
      const response = await fetch(`${API_BASE_URL}${url}`, {
        ...options,
        headers
      })

      const result = await response.json()
      
      if (!response.ok) {
        throw new Error(result.detail || result.error || '请求失败')
      }

      return result
    } catch (error: any) {
      throw new Error(error.message)
    }
  }

  private static async getAuthHeaders(): Promise<Record<string, string>> {
    const token = getStoredToken()
    
    if (!token) {
      throw new Error('用户未登录')
    }

    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    }
  }

  static async startGeneration(params: {
    moduleType: string
    prompt: string
    negativePrompt?: string
    modelConfig: any
    parameters: any
    inputFiles?: string[]
    projectId?: string
  }): Promise<ApiResponse<{ generationId: string, status: string }>> {
    try {
      // 将参数转换为表单数据格式（兼容FastAPI的Form接收）
      const formData = new FormData()
      formData.append('module_type', params.moduleType)
      formData.append('prompt', params.prompt)
      if (params.negativePrompt) {
        formData.append('negative_prompt', params.negativePrompt)
      }
      formData.append('model_config', JSON.stringify(params.modelConfig))
      formData.append('parameters', JSON.stringify(params.parameters))
      if (params.projectId) {
        formData.append('project_id', params.projectId)
      }

      const response = await this.makeRequest('/api/ai-generation', {
        method: 'POST',
        body: formData
      })

      if (response.success) {
        return { success: true, data: response.data }
      }

      return { success: false, error: response.error || '生成失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async getGenerationStatus(generationId: string): Promise<ApiResponse<GenerationTask>> {
    try {
      const response = await this.makeRequest(`/api/generation-status?id=${generationId}`)

      if (response.success) {
        return { success: true, data: response.data.generations[0] }
      }

      return { success: false, error: response.error || '获取状态失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async listGenerationHistory(params: {
    moduleType?: string
    status?: string
    projectId?: string
    limit?: number
    offset?: number
  } = {}): Promise<ApiResponse<{ generations: GenerationTask[], total: number, hasMore: boolean }>> {
    try {
      const searchParams = new URLSearchParams()

      if (params.moduleType) searchParams.append('module_type', params.moduleType)
      if (params.status) searchParams.append('status', params.status)
      if (params.projectId) searchParams.append('project_id', params.projectId)
      if (params.limit) searchParams.append('limit', params.limit.toString())
      if (params.offset) searchParams.append('offset', params.offset.toString())

      const response = await this.makeRequest(`/api/generation-status?${searchParams}`)

      if (response.success) {
        return { success: true, data: response.data }
      }

      return { success: false, error: response.error || '获取历史失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async cancelGeneration(generationId: string): Promise<ApiResponse> {
    try {
      const response = await this.makeRequest(`/api/generation-status?generationId=${generationId}`, {
        method: 'DELETE'
      })

      if (response.success) {
        return { success: true, message: response.message || '任务已取消' }
      }

      return { success: false, error: response.error || '取消失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async retryGeneration(generationId: string): Promise<ApiResponse> {
    try {
      const response = await this.makeRequest('/api/generation-status', {
        method: 'POST',
        body: JSON.stringify({ generationId })
      })

      if (response.success) {
        return { success: true, message: response.message || '重试任务已创建' }
      }

      return { success: false, error: response.error || '重试失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async getGenerationStats(period: '7d' | '30d' | '90d' | '1y' = '30d'): Promise<ApiResponse<any>> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/generation-status?action=stats&period=${period}`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '获取统计失败' }
      }

      return { success: true, data: result.stats }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  // LoRA相关方法
  static async getLoRAList(): Promise<LoRAModel[]> {
    try {
      const response = await this.makeRequest('/api/model-management?action=lora-list')

      if (response.success) {
        return response.data.loras || []
      }

      // 返回备用数据
      return [
        { id: 'l1', name: 'Anime Style v2', category: 'Style', weight: 0.8 },
        { id: 'l2', name: 'Photorealistic Detail', category: 'Quality', weight: 0.6 },
        { id: 'l3', name: 'Cinematic Lighting', category: 'Style', weight: 1.0 },
        { id: 'l4', name: 'Character Consistency', category: 'Character', weight: 0.7 },
        { id: 'l5', name: 'Art Nouveau Style', category: 'Style', weight: 0.9 },
        { id: 'l6', name: 'Vaporwave Aesthetic', category: 'Style', weight: 0.5 },
        { id: 'l7', name: 'Watercolor Effect', category: 'Style', weight: 0.8 },
        { id: 'l8', name: 'Portrait Enhancement', category: 'Quality', weight: 0.7 }
      ]
    } catch (error: any) {
      console.error('Failed to load LoRA list:', error)
      // 返回备用数据
      return [
        { id: 'l1', name: 'Anime Style v2', category: 'Style', weight: 0.8 },
        { id: 'l2', name: 'Photorealistic Detail', category: 'Quality', weight: 0.6 },
        { id: 'l3', name: 'Cinematic Lighting', category: 'Style', weight: 1.0 },
        { id: 'l4', name: 'Character Consistency', category: 'Character', weight: 0.7 },
        { id: 'l5', name: 'Art Nouveau Style', category: 'Style', weight: 0.9 },
        { id: 'l6', name: 'Vaporwave Aesthetic', category: 'Style', weight: 0.5 },
        { id: 'l7', name: 'Watercolor Effect', category: 'Style', weight: 0.8 },
        { id: 'l8', name: 'Portrait Enhancement', category: 'Quality', weight: 0.7 }
      ]
    }
  }

  static async uploadLoRA(file: File, onProgress?: (progress: number) => void): Promise<ApiResponse<{ lora: LoRAModel }>> {
    try {
      const headers = await this.getAuthHeaders()
      const formData = new FormData()

      formData.append('file', file)
      formData.append('type', 'lora')

      // 创建XMLHttpRequest以支持进度回调
      return new Promise((resolve) => {
        const xhr = new XMLHttpRequest()

        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable && onProgress) {
            const progress = Math.round((event.loaded / event.total) * 100)
            onProgress(progress)
          }
        })

        xhr.addEventListener('load', () => {
          try {
            const result = JSON.parse(xhr.responseText)
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve({ success: true, data: result, message: 'LoRA上传成功' })
            } else {
              resolve({ success: false, error: result.error || '上传失败' })
            }
          } catch (error) {
            resolve({ success: false, error: '解析响应失败' })
          }
        })

        xhr.addEventListener('error', () => {
          resolve({ success: false, error: '网络错误' })
        })

        xhr.open('POST', `${this.baseUrl}/model-management?action=upload`)
        const authHeader = Array.isArray(headers) 
          ? headers.find(h => h[0] === 'Authorization')?.[1] || ''
          : (headers as any).Authorization || ''
        xhr.setRequestHeader('Authorization', authHeader)
        xhr.send(formData)
      })
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  // ControlNet相关方法
  static async getControlNetPreprocessors(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=controlnet-preprocessors`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取预处理器列表失败')
      }

      return result.preprocessors || []
    } catch (error: any) {
      console.error('Failed to load ControlNet preprocessors:', error)
      // 返回备用数据
      return [
        { id: 'canny', name: 'Canny Edge', description: 'Edge detection', type: 'edge', enabled: true },
        { id: 'depth', name: 'Depth', description: 'Depth map', type: 'depth', enabled: true },
        { id: 'pose', name: 'OpenPose', description: 'Body pose', type: 'pose', enabled: true },
        { id: 'scribble', name: 'Scribble', description: 'Hand drawn', type: 'scribble', enabled: true },
        { id: 'mlsd', name: 'MLSD', description: 'Line detection', type: 'mlsd', enabled: true }
      ]
    }
  }

  static async getControlNetModels(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=controlnet-models`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取ControlNet模型列表失败')
      }

      return result.models || []
    } catch (error: any) {
      console.error('Failed to load ControlNet models:', error)
      // 返回备用数据
      return [
        { 
          id: 'cn1', 
          name: 'ControlNet v1.1', 
          size: '1.4GB', 
          description: 'Standard ControlNet model', 
          supported_preprocessors: ['canny', 'depth', 'pose'], 
          resolution: '512x512' 
        },
        { 
          id: 'cn2', 
          name: 'ControlNet XL', 
          size: '1.8GB', 
          description: 'High-resolution ControlNet', 
          supported_preprocessors: ['canny', 'depth', 'pose', 'scribble'], 
          resolution: '1024x1024' 
        }
      ]
    }
  }

  static async processControlNetImage(file: File, preprocessorType: string): Promise<ApiResponse<any>> {
    try {
      const headers = await this.getAuthHeaders()
      const formData = new FormData()

      formData.append('file', file)
      formData.append('preprocessor', preprocessorType)

      const response = await fetch(`${this.baseUrl}/model-management?action=process-controlnet-image`, {
        method: 'POST',
        headers,
        body: formData
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '图像预处理失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  // 参数管理相关方法
  static async getSamplers(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=samplers`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取采样器列表失败')
      }

      return result.samplers || []
    } catch (error: any) {
      console.error('Failed to load samplers:', error)
      // 返回备用数据
      return [
        { id: 'dpmpp_2m', name: 'DPM++ 2M', description: 'Fast and stable', speed: 'fast', quality: 'high', memory_usage: 'medium' },
        { id: 'dpmpp_2m_sde', name: 'DPM++ 2M SDE', description: 'High quality SDE', speed: 'medium', quality: 'high', memory_usage: 'high' },
        { id: 'euler', name: 'Euler', description: 'Simple and fast', speed: 'fast', quality: 'standard', memory_usage: 'low' },
        { id: 'euler_a', name: 'Euler Ancestral', description: 'More creative', speed: 'fast', quality: 'standard', memory_usage: 'low' },
        { id: 'lcm', name: 'LCM', description: 'Latent Consistency Model', speed: 'fast', quality: 'draft', memory_usage: 'low' }
      ]
    }
  }

  static async getSchedulers(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=schedulers`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取调度器列表失败')
      }

      return result.schedulers || []
    } catch (error: any) {
      console.error('Failed to load schedulers:', error)
      // 返回备用数据
      return [
        { id: 'simple', name: 'Simple', description: 'Standard scheduler', type: 'simple', stability: 'medium' },
        { id: 'karras', name: 'Karras', description: 'Karras noise schedule', type: 'karras', stability: 'high' },
        { id: 'exponential', name: 'Exponential', description: 'Exponential decay', type: 'exponential', stability: 'medium' }
      ]
    }
  }

  static async getParameterPresets(moduleType: string): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=presets&moduleType=${moduleType}`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取参数预设失败')
      }

      return result.presets || []
    } catch (error: any) {
      console.error('Failed to load parameter presets:', error)
      return []
    }
  }

  static async saveParameterPreset(params: {
    name: string
    description: string
    module_type: string
    parameters: any
  }): Promise<ApiResponse> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=save-preset`, {
        method: 'POST',
        headers,
        body: JSON.stringify(params)
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '保存预设失败' }
      }

      return { success: true, data: result, message: '预设保存成功' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async incrementPresetUsage(presetId: string): Promise<ApiResponse> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=increment-preset-usage`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ presetId })
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '更新使用次数失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  // 分辨率管理相关方法
  static async getAspectRatios(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=aspect-ratios`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取宽高比列表失败')
      }

      return result.aspectRatios || []
    } catch (error: any) {
      console.error('Failed to load aspect ratios:', error)
      // 返回备用数据
      return [
        { id: '1:1', name: '1:1 (512×512)', width: 512, height: 512, category: 'square', megapixels: 0.26, usage_frequency: 85 },
        { id: '4:3', name: '4:3 (640×480)', width: 640, height: 480, category: 'landscape', megapixels: 0.31, usage_frequency: 70 },
        { id: '3:2', name: '3:2 (768×512)', width: 768, height: 512, category: 'landscape', megapixels: 0.39, usage_frequency: 75 },
        { id: '16:9', name: '16:9 (768×432)', width: 768, height: 432, category: 'landscape', megapixels: 0.33, usage_frequency: 80 },
        { id: '21:9', name: '21:9 (896×384)', width: 896, height: 384, category: 'wide', megapixels: 0.34, usage_frequency: 60 },
        { id: '9:16', name: '9:16 (512×896)', width: 512, height: 896, category: 'portrait', megapixels: 0.46, usage_frequency: 90 },
        { id: '2:3', name: '2:3 (512×768)', width: 512, height: 768, category: 'portrait', megapixels: 0.39, usage_frequency: 70 },
        { id: '3:4', name: '3:4 (480×640)', width: 480, height: 640, category: 'portrait', megapixels: 0.31, usage_frequency: 65 },
        { id: '9:21', name: '9:21 (384×896)', width: 384, height: 896, category: 'ultrawide', megapixels: 0.34, usage_frequency: 45 }
      ]
    }
  }

  static async getResolutionPresets(moduleType: string): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=resolution-presets&moduleType=${moduleType}`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取分辨率预设失败')
      }

      return result.presets || []
    } catch (error: any) {
      console.error('Failed to load resolution presets:', error)
      return []
    }
  }

  static async getModelCompatibility(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=model-compatibility`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取模型兼容性信息失败')
      }

      return result.compatibility || []
    } catch (error: any) {
      console.error('Failed to load model compatibility:', error)
      return []
    }
  }

  static async optimizeResolution(width: number, height: number): Promise<ApiResponse<any>> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=optimize-resolution`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ width, height })
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '分辨率优化失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  // 优化管理相关方法
  static async getUpscalingMethods(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=upscaling-methods`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取放大方法列表失败')
      }

      return result.methods || []
    } catch (error: any) {
      console.error('Failed to load upscaling methods:', error)
      // 返回备用数据
      return [
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
      ]
    }
  }

  static async getStyleFilters(): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=style-filters`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取风格滤镜列表失败')
      }

      return result.filters || []
    } catch (error: any) {
      console.error('Failed to load style filters:', error)
      // 返回备用数据
      return [
        { id: 'cinematic', name: '电影感', description: '电影级调色', type: 'cinematic', intensity: 0.8, parameters: {}, preview_available: true, processing_time: 2 },
        { id: 'vintage', name: '复古', description: '复古滤镜', type: 'vintage', intensity: 0.7, parameters: {}, preview_available: true, processing_time: 1 },
        { id: 'cyberpunk', name: '赛博朋克', description: '赛博朋克风格', type: 'modern', intensity: 0.9, parameters: {}, preview_available: true, processing_time: 3 }
      ]
    }
  }

  static async getOptimizationPresets(moduleType: string): Promise<any[]> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=optimization-presets&moduleType=${moduleType}`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取优化预设失败')
      }

      return result.presets || []
    } catch (error: any) {
      console.error('Failed to load optimization presets:', error)
      return []
    }
  }

  static async saveOptimizationPreset(params: {
    name: string
    description: string
    module_type: string
    settings: any
  }): Promise<ApiResponse> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=save-optimization-preset`, {
        method: 'POST',
        headers,
        body: JSON.stringify(params)
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '保存预设失败' }
      }

      return { success: true, data: result, message: '预设保存成功' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async getPerformanceMetrics(): Promise<any> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=performance-metrics`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || '获取性能指标失败')
      }

      return result.metrics || null
    } catch (error: any) {
      console.error('Failed to load performance metrics:', error)
      return {
        gpu_usage: 0,
        memory_usage: 0,
        processing_speed: 1.0,
        quality_score: 5.0,
        efficiency_rating: 'fair'
      }
    }
  }

  static async startPerformanceMonitoring(): Promise<ApiResponse> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=start-performance-monitoring`, {
        method: 'POST',
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '启动性能监控失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async stopPerformanceMonitoring(): Promise<ApiResponse> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=stop-performance-monitoring`, {
        method: 'POST',
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '停止性能监控失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }
}

// 本地模型管理服务
export class ModelService {
  static baseUrl = API_BASE_URL
  
  private static async getAuthHeaders(): Promise<Record<string, string>> {
    const token = getStoredToken()
    
    if (!token) {
      throw new Error('用户未登录')
    }

    return {
      'Authorization': `Bearer ${token}`
    }
  }

  private static async makeRequest(url: string, options: RequestInit = {}): Promise<any> {
    const token = getStoredToken()
    
    if (!token) {
      throw new Error('用户未登录')
    }

    const headers = {
      'Authorization': `Bearer ${token}`,
      ...options.headers
    }

    try {
      const response = await fetch(`${API_BASE_URL}${url}`, {
        ...options,
        headers
      })

      const result = await response.json()
      
      if (!response.ok) {
        throw new Error(result.detail || result.error || '请求失败')
      }

      return result
    } catch (error: any) {
      throw new Error(error.message)
    }
  }

  static async listModels(): Promise<ApiResponse<{ models: ModelConfig[], count: number }>> {
    try {
      const response = await this.makeRequest('/api/model-management?action=list')

      if (response.success) {
        return { success: true, data: response.data }
      }

      return { success: false, error: response.error || '获取模型列表失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async uploadModel(params: {
    file: File
    type: string
    name: string
    description?: string
  }): Promise<ApiResponse<{ model: ModelConfig }>> {
    try {
      const headers = await this.getAuthHeaders()
      const formData = new FormData()

      formData.append('file', params.file)
      formData.append('type', params.type)
      formData.append('name', params.name)
      if (params.description) {
        formData.append('description', params.description)
      }

      const response = await fetch(`${this.baseUrl}/model-management?action=upload`, {
        method: 'POST',
        headers,
        body: formData
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '上传失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async deleteModel(modelId: string): Promise<ApiResponse> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=delete`, {
        method: 'DELETE',
        headers,
        body: JSON.stringify({ modelId })
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '删除失败' }
      }

      return { success: true, data: result, message: '模型已删除' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async updateModel(modelId: string, updates: Partial<ModelConfig>): Promise<ApiResponse<{ model: ModelConfig }>> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=update`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ modelId, updates })
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '更新失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async checkModelUpdates(): Promise<ApiResponse<{ updates: any[] }>> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/model-management?action=check-updates`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '检查更新失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }
}

// 本地文件处理服务
export class FileService {
  static baseUrl = API_BASE_URL
  
  private static async getAuthHeaders(): Promise<Record<string, string>> {
    const token = getStoredToken()
    
    if (!token) {
      throw new Error('用户未登录')
    }

    return {
      'Authorization': `Bearer ${token}`
    }
  }

  private static async makeRequest(url: string, options: RequestInit = {}): Promise<any> {
    const token = getStoredToken()
    
    if (!token) {
      throw new Error('用户未登录')
    }

    const headers = {
      'Authorization': `Bearer ${token}`,
      ...options.headers
    }

    try {
      const response = await fetch(`${API_BASE_URL}${url}`, {
        ...options,
        headers
      })

      const result = await response.json()
      
      if (!response.ok) {
        throw new Error(result.detail || result.error || '请求失败')
      }

      return result
    } catch (error: any) {
      throw new Error(error.message)
    }
  }

  static async uploadFile(params: {
    file: File
    bucket?: string
    folder?: string
    isPublic?: boolean
    projectId?: string
  }): Promise<ApiResponse<{ file: any, url: string }>> {
    try {
      const formData = new FormData()
      formData.append('action', 'upload')
      formData.append('file', params.file)
      if (params.bucket) formData.append('bucket', params.bucket)
      if (params.folder) formData.append('folder', params.folder)
      if (params.projectId) formData.append('project_id', params.projectId)

      const response = await this.makeRequest('/api/file-processor', {
        method: 'POST',
        body: formData
      })

      if (response.success) {
        return { success: true, data: response.data }
      }

      return { success: false, error: response.error || '上传失败' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async downloadFile(fileId: string, bucketName: string): Promise<ApiResponse<{ downloadUrl: string, fileInfo: any }>> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/file-processor?action=download&fileId=${fileId}&bucket=${bucketName}`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '下载失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async listFiles(params: {
    bucket: string
    projectId?: string
    fileType?: string
    limit?: number
    offset?: number
  }): Promise<ApiResponse<{ files: any[], total: number, hasMore: boolean }>> {
    try {
      const headers = await this.getAuthHeaders()
      const searchParams = new URLSearchParams()

      searchParams.append('action', 'list')
      searchParams.append('bucket', params.bucket)
      if (params.projectId) searchParams.append('projectId', params.projectId)
      if (params.fileType) searchParams.append('fileType', params.fileType)
      if (params.limit) searchParams.append('limit', params.limit.toString())
      if (params.offset) searchParams.append('offset', params.offset.toString())

      const response = await fetch(`${this.baseUrl}/file-processor?${searchParams}`, {
        headers
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '获取文件列表失败' }
      }

      return { success: true, data: result }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async deleteFile(fileId: string, bucketName: string): Promise<ApiResponse> {
    try {
      const headers = await this.getAuthHeaders()

      const response = await fetch(`${this.baseUrl}/file-processor?action=delete`, {
        method: 'DELETE',
        headers,
        body: JSON.stringify({ fileId, bucketName })
      })

      const result = await response.json()

      if (!response.ok) {
        return { success: false, error: result.error || '删除失败' }
      }

      return { success: true, data: result, message: '文件已删除' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }
}

// 本地项目管理服务
export class ProjectService {
  private static async makeRequest(url: string, options: RequestInit = {}): Promise<any> {
    const token = getStoredToken()
    
    if (!token) {
      throw new Error('用户未登录')
    }

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers
    }

    try {
      const response = await fetch(`${API_BASE_URL}${url}`, {
        ...options,
        headers
      })

      const result = await response.json()
      
      if (!response.ok) {
        throw new Error(result.detail || result.error || '请求失败')
      }

      return result
    } catch (error: any) {
      throw new Error(error.message)
    }
  }

  // 暂时使用本地存储作为项目管理的临时实现
  static async createProject(params: {
    name: string
    description?: string
    moduleType: string
  }) {
    try {
      // 使用localStorage临时存储项目管理数据
      const projects = JSON.parse(localStorage.getItem('aigc_projects') || '[]')
      const newProject = {
        id: Date.now().toString(),
        name: params.name,
        description: params.description || '',
        module_type: params.moduleType,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
      
      projects.push(newProject)
      localStorage.setItem('aigc_projects', JSON.stringify(projects))
      
      return { success: true, data: newProject }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async listProjects(limit: number = 20, offset: number = 0) {
    try {
      const projects = JSON.parse(localStorage.getItem('aigc_projects') || '[]')
      const sortedProjects = projects.sort((a: any, b: any) => 
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      )
      
      const paginatedProjects = sortedProjects.slice(offset, offset + limit)
      
      return { 
        success: true, 
        data: paginatedProjects, 
        total: projects.length 
      }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }

  static async deleteProject(projectId: string) {
    try {
      const projects = JSON.parse(localStorage.getItem('aigc_projects') || '[]')
      const filteredProjects = projects.filter((p: any) => p.id !== projectId)
      localStorage.setItem('aigc_projects', JSON.stringify(filteredProjects))
      
      return { success: true, message: '项目已删除' }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  }
}