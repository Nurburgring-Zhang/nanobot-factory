// AI Generation Edge Function
// 处理AI图像、视频、3D生成请求

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS, PUT, DELETE, PATCH',
  'Access-Control-Max-Age': '86400',
  'Access-Control-Allow-Credentials': 'false'
}

interface GenerationRequest {
  moduleType: string
  prompt: string
  negativePrompt?: string
  modelConfig: any
  parameters: any
  inputFiles?: string[]
  projectId?: string
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

    if (req.method === 'POST') {
      const requestData: GenerationRequest = await req.json()

      // Validate required fields
      if (!requestData.moduleType || !requestData.prompt || !requestData.modelConfig || !requestData.parameters) {
        return new Response(
          JSON.stringify({ error: { code: 'VALIDATION_ERROR', message: '缺少必需字段' } }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Create generation task
      const { data: generation, error: createError } = await supabaseClient
        .from('generation_tasks')
        .insert({
          user_id: user.id,
          project_id: requestData.projectId,
          module_type: requestData.moduleType,
          prompt: requestData.prompt,
          negative_prompt: requestData.negativePrompt,
          model_config: requestData.modelConfig,
          parameters: requestData.parameters,
          input_files: requestData.inputFiles || [],
          status: 'pending'
        })
        .select()
        .single()

      if (createError) {
        console.error('创建生成任务失败:', createError)
        return new Response(
          JSON.stringify({ error: { code: 'DATABASE_ERROR', message: '创建任务失败' } }),
          { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // TODO: 在这里集成实际的AI推理服务
      // 目前返回模拟响应
      const mockResult = {
        generationId: generation.id,
        status: 'processing',
        estimatedTime: 30 // 30秒
      }

      return new Response(
        JSON.stringify({ 
          success: true, 
          data: mockResult,
          message: '生成任务已创建，正在处理中...' 
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Method not allowed
    return new Response(
      JSON.stringify({ error: { code: 'METHOD_NOT_ALLOWED', message: '不支持的请求方法' } }),
      { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('AI Generation错误:', error)
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