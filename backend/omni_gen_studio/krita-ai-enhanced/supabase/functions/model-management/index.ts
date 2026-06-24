// Model Management Edge Function
// 处理模型管理相关操作

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS, PUT, DELETE, PATCH',
  'Access-Control-Max-Age': '86400',
  'Access-Control-Allow-Credentials': 'false'
}

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 200, headers: corsHeaders })
  }

  try {
    // Initialize Supabase client
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
      {
        global: {
          headers: { Authorization: req.headers.get('Authorization')! },
        },
      }
    )

    // Get user from JWT
    const { data: { user }, error: userError } = await supabaseClient.auth.getUser()
    if (userError || !user) {
      return new Response(
        JSON.stringify({ error: { code: 'UNAUTHORIZED', message: '用户未认证' } }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    const url = new URL(req.url)
    const action = url.searchParams.get('action')

    if (req.method === 'GET') {
      switch (action) {
        case 'lora-list':
          // 返回LoRA模型列表
          const loraModels = [
            { id: 'l1', name: 'Anime Style v2', category: 'Style', weight: 0.8, description: '动漫风格LoRA模型' },
            { id: 'l2', name: 'Photorealistic Detail', category: 'Quality', weight: 0.6, description: '写实细节增强' },
            { id: 'l3', name: 'Cinematic Lighting', category: 'Style', weight: 1.0, description: '电影级光影效果' },
            { id: 'l4', name: 'Character Consistency', category: 'Character', weight: 0.7, description: '角色一致性保持' },
            { id: 'l5', name: 'Art Nouveau Style', category: 'Style', weight: 0.9, description: '新艺术风格' },
            { id: 'l6', name: 'Vaporwave Aesthetic', category: 'Style', weight: 0.5, description: '蒸汽波美学' },
            { id: 'l7', name: 'Watercolor Effect', category: 'Style', weight: 0.8, description: '水彩画效果' },
            { id: 'l8', name: 'Portrait Enhancement', category: 'Quality', weight: 0.7, description: '人像增强' }
          ]
          return new Response(
            JSON.stringify({ success: true, loras: loraModels }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )

        case 'controlnet-preprocessors':
          // 返回ControlNet预处理器列表
          const preprocessors = [
            { id: 'canny', name: 'Canny Edge', description: '边缘检测', type: 'edge', enabled: true },
            { id: 'depth', name: 'Depth', description: '深度图', type: 'depth', enabled: true },
            { id: 'pose', name: 'OpenPose', description: '人体姿态', type: 'pose', enabled: true },
            { id: 'scribble', name: 'Scribble', description: '手绘涂鸦', type: 'scribble', enabled: true },
            { id: 'mlsd', name: 'MLSD', description: '直线检测', type: 'mlsd', enabled: true }
          ]
          return new Response(
            JSON.stringify({ success: true, preprocessors }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )

        case 'controlnet-models':
          // 返回ControlNet模型列表
          const controlnetModels = [
            { 
              id: 'cn1', 
              name: 'ControlNet v1.1', 
              size: '1.4GB', 
              description: '标准ControlNet模型', 
              supported_preprocessors: ['canny', 'depth', 'pose'], 
              resolution: '512x512' 
            },
            { 
              id: 'cn2', 
              name: 'ControlNet XL', 
              size: '1.8GB', 
              description: '高分辨率ControlNet', 
              supported_preprocessors: ['canny', 'depth', 'pose', 'scribble'], 
              resolution: '1024x1024' 
            }
          ]
          return new Response(
            JSON.stringify({ success: true, models: controlnetModels }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )

        case 'samplers':
          // 返回采样器列表
          const samplers = [
            { id: 'dpmpp_2m', name: 'DPM++ 2M', description: '快速稳定', speed: 'fast', quality: 'high', memory_usage: 'medium' },
            { id: 'dpmpp_2m_sde', name: 'DPM++ 2M SDE', description: '高质量SDE', speed: 'medium', quality: 'high', memory_usage: 'high' },
            { id: 'euler', name: 'Euler', description: '简单快速', speed: 'fast', quality: 'standard', memory_usage: 'low' },
            { id: 'euler_a', name: 'Euler Ancestral', description: '更有创意', speed: 'fast', quality: 'standard', memory_usage: 'low' },
            { id: 'lcm', name: 'LCM', description: '潜在一致性模型', speed: 'fast', quality: 'draft', memory_usage: 'low' }
          ]
          return new Response(
            JSON.stringify({ success: true, samplers }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )

        case 'schedulers':
          // 返回调度器列表
          const schedulers = [
            { id: 'simple', name: 'Simple', description: '标准调度器', type: 'simple', stability: 'medium' },
            { id: 'karras', name: 'Karras', description: 'Karras噪声调度', type: 'karras', stability: 'high' },
            { id: 'exponential', name: 'Exponential', description: '指数衰减', type: 'exponential', stability: 'medium' }
          ]
          return new Response(
            JSON.stringify({ success: true, schedulers }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )

        case 'aspect-ratios':
          // 返回宽高比列表
          const aspectRatios = [
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
          return new Response(
            JSON.stringify({ success: true, aspectRatios }),
            { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )

        default:
          // 处理其他GET请求
          return new Response(
            JSON.stringify({ error: { code: 'INVALID_ACTION', message: '无效的操作' } }),
            { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
      }
    }

    // Method not allowed
    return new Response(
      JSON.stringify({ error: { code: 'METHOD_NOT_ALLOWED', message: '不支持的请求方法' } }),
      { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('Model Management错误:', error)
    return new Response(
      JSON.stringify({ 
        error: { 
          code: 'INTERNAL_ERROR', 
          message: error.message || '内部服务器错误' 
        } 
      }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})