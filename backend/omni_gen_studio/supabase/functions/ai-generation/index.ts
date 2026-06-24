// General AIGC Enhanced - AI Generation Service
// 处理图片生成、图片编辑、视频生成、3D生成的Edge Function

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'
import { PythonShell } from 'https://esm.sh/python-shell@3.0.1'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS, PUT, DELETE, PATCH',
  'Access-Control-Max-Age': '86400',
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    )

    const { 
      moduleType, 
      prompt, 
      negativePrompt, 
      modelConfig, 
      parameters, 
      inputFiles,
      projectId 
    } = await req.json()

    // 验证必需参数
    if (!moduleType || !prompt || !modelConfig) {
      return new Response(
        JSON.stringify({ error: '缺少必需参数: moduleType, prompt, modelConfig' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 获取用户认证信息
    const authHeader = req.headers.get('Authorization')
    if (!authHeader) {
      return new Response(
        JSON.stringify({ error: '缺少认证头' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    const token = authHeader.replace('Bearer ', '')
    const { data: { user }, error: authError } = await supabaseClient.auth.getUser(token)
    
    if (authError || !user) {
      return new Response(
        JSON.stringify({ error: '认证失败' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 创建生成任务记录
    const { data: generation, error: createError } = await supabaseClient
      .from('generation_history')
      .insert({
        user_id: user.id,
        project_id: projectId,
        module_type: moduleType,
        prompt: prompt,
        negative_prompt: negativePrompt,
        model_config: modelConfig,
        parameters: parameters,
        input_files: inputFiles,
        status: 'processing'
      })
      .select()
      .single()

    if (createError) {
      console.error('创建生成任务失败:', createError)
      return new Response(
        JSON.stringify({ error: '创建生成任务失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 准备Python脚本参数
    const pythonScript = getPythonScriptForModule(moduleType)
    const scriptOptions = {
      mode: 'text',
      pythonPath: 'python3',
      pythonOptions: ['-u'],
      scriptPath: '/tmp',
      args: JSON.stringify({
        generation_id: generation.id,
        module_type: moduleType,
        prompt: prompt,
        negative_prompt: negativePrompt,
        model_config: modelConfig,
        parameters: parameters,
        input_files: inputFiles,
        supabase_url: Deno.env.get('SUPABASE_URL'),
        supabase_key: Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')
      })
    }

    // 在后台执行Python推理脚本
    const pythonShell = new PythonShell('ai_inference.py', scriptOptions)
    
    pythonShell.on('message', (message) => {
      console.log('Python输出:', message)
      // 可以在这里发送实时更新给前端
    })

    pythonShell.on('error', (error) => {
      console.error('Python执行错误:', error)
      // 更新任务状态为失败
      supabaseClient
        .from('generation_history')
        .update({ 
          status: 'failed',
          completed_at: new Date().toISOString()
        })
        .eq('id', generation.id)
    })

    pythonShell.on('close', (code) => {
      if (code === 0) {
        console.log('Python脚本执行成功')
        // 更新任务状态为完成
        supabaseClient
          .from('generation_history')
          .update({ 
            status: 'completed',
            completed_at: new Date().toISOString()
          })
          .eq('id', generation.id)
      } else {
        console.error('Python脚本执行失败，退出码:', code)
        // 更新任务状态为失败
        supabaseClient
          .from('generation_history')
          .update({ 
            status: 'failed',
            completed_at: new Date().toISOString()
          })
          .eq('id', generation.id)
      }
    })

    // 返回任务ID供前端查询状态
    return new Response(
      JSON.stringify({ 
        success: true, 
        generationId: generation.id,
        status: 'processing',
        message: 'AI生成任务已启动'
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('AI生成服务错误:', error)
    return new Response(
      JSON.stringify({ 
        error: 'AI生成服务内部错误',
        details: error.message 
      }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})

// 根据模块类型返回对应的Python脚本
function getPythonScriptForModule(moduleType: string): string {
  const scripts = {
    'image-gen': 'image_generation.py',
    'image-edit': 'image_editing.py', 
    'video-gen': 'video_generation.py',
    '3d-gen': '3d_generation.py'
  }
  return scripts[moduleType] || 'image_generation.py'
}