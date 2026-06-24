// Generation Status Edge Function
// 处理生成任务状态查询和管理

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

    if (req.method === 'GET') {
      // Query single generation status or list generations
      const generationId = url.searchParams.get('id')
      const action = url.searchParams.get('action')

      if (generationId) {
        // Get single generation status
        const { data: generation, error } = await supabaseClient
          .from('generation_tasks')
          .select('*')
          .eq('id', generationId)
          .eq('user_id', user.id)
          .single()

        if (error) {
          return new Response(
            JSON.stringify({ error: { code: 'NOT_FOUND', message: '生成任务不存在' } }),
            { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
        }

        // TODO: 这里应该检查实际的生成状态
        // 目前返回模拟状态
        const mockStatus = {
          ...generation,
          progress: Math.min(100, generation.progress + Math.floor(Math.random() * 20)),
          estimatedTimeRemaining: Math.max(0, 30 - Math.floor(Math.random() * 30))
        }

        return new Response(
          JSON.stringify({ 
            success: true, 
            generation: mockStatus 
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // List generations
      const moduleType = url.searchParams.get('moduleType')
      const status = url.searchParams.get('status')
      const projectId = url.searchParams.get('projectId')
      const limit = parseInt(url.searchParams.get('limit') || '20')
      const offset = parseInt(url.searchParams.get('offset') || '0')

      let query = supabaseClient
        .from('generation_tasks')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })
        .range(offset, offset + limit - 1)

      if (moduleType) query = query.eq('module_type', moduleType)
      if (status) query = query.eq('status', status)
      if (projectId) query = query.eq('project_id', projectId)

      const { data: generations, error, count } = await query

      if (error) {
        console.error('获取生成历史失败:', error)
        return new Response(
          JSON.stringify({ error: { code: 'DATABASE_ERROR', message: '获取生成历史失败' } }),
          { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      return new Response(
        JSON.stringify({ 
          success: true, 
          data: { 
            generations: generations || [], 
            total: count || 0, 
            hasMore: (generations?.length || 0) === limit 
          }
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (req.method === 'DELETE') {
      // Cancel generation
      const { action, generationId } = await req.json()

      if (action === 'cancel' && generationId) {
        const { data, error } = await supabaseClient
          .from('generation_tasks')
          .update({ 
            status: 'cancelled',
            updated_at: new Date().toISOString()
          })
          .eq('id', generationId)
          .eq('user_id', user.id)
          .select()
          .single()

        if (error) {
          return new Response(
            JSON.stringify({ error: { code: 'CANCEL_ERROR', message: '取消任务失败' } }),
            { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
        }

        return new Response(
          JSON.stringify({ 
            success: true, 
            data,
            message: '任务已取消' 
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }
    }

    if (req.method === 'POST') {
      // Retry generation
      const { action, generationId } = await req.json()

      if (action === 'retry' && generationId) {
        // Get original generation task
        const { data: original, error: fetchError } = await supabaseClient
          .from('generation_tasks')
          .select('*')
          .eq('id', generationId)
          .eq('user_id', user.id)
          .single()

        if (fetchError) {
          return new Response(
            JSON.stringify({ error: { code: 'NOT_FOUND', message: '原始任务不存在' } }),
            { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
        }

        // Create new generation task
        const { data: newGeneration, error: createError } = await supabaseClient
          .from('generation_tasks')
          .insert({
            user_id: user.id,
            project_id: original.project_id,
            module_type: original.module_type,
            prompt: original.prompt,
            negative_prompt: original.negative_prompt,
            model_config: original.model_config,
            parameters: original.parameters,
            input_files: original.input_files,
            status: 'pending'
          })
          .select()
          .single()

        if (createError) {
          return new Response(
            JSON.stringify({ error: { code: 'CREATE_ERROR', message: '创建重试任务失败' } }),
            { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
        }

        return new Response(
          JSON.stringify({ 
            success: true, 
            data: newGeneration,
            message: '重试任务已创建' 
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }
    }

    // Method not allowed
    return new Response(
      JSON.stringify({ error: { code: 'METHOD_NOT_ALLOWED', message: '不支持的请求方法' } }),
      { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('Generation Status错误:', error)
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