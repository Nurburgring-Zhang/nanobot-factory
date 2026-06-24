// General AIGC Enhanced - Generation Status Service
// 查询AI生成任务状态的Edge Function

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

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

    const url = new URL(req.url)
    const action = url.searchParams.get('action')

    // 验证认证
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

    switch (action) {
      case 'get':
        return await getGenerationStatus(req, supabaseClient, user.id, corsHeaders)
      case 'list':
        return await listGenerationHistory(req, supabaseClient, user.id, corsHeaders)
      case 'cancel':
        return await cancelGeneration(req, supabaseClient, user.id, corsHeaders)
      case 'retry':
        return await retryGeneration(req, supabaseClient, user.id, corsHeaders)
      case 'stats':
        return await getGenerationStats(req, supabaseClient, user.id, corsHeaders)
      default:
        return new Response(
          JSON.stringify({ error: '无效的操作' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
    }

  } catch (error) {
    console.error('生成状态服务错误:', error)
    return new Response(
      JSON.stringify({ 
        error: '生成状态服务内部错误',
        details: error.message 
      }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})

// 获取单个生成任务状态
async function getGenerationStatus(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const url = new URL(req.url)
    const generationId = url.searchParams.get('id')

    if (!generationId) {
      return new Response(
        JSON.stringify({ error: '缺少生成任务ID' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 获取生成任务详情
    const { data: generation, error } = await supabaseClient
      .from('generation_history')
      .select(`
        *,
        projects!inner (
          id,
          name,
          module_type
        )
      `)
      .eq('id', generationId)
      .eq('user_id', userId)
      .single()

    if (error || !generation) {
      return new Response(
        JSON.stringify({ error: '生成任务不存在或无权限' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 计算进度和耗时
    const now = new Date()
    const createdAt = new Date(generation.created_at)
    const elapsedTime = Math.floor((now.getTime() - createdAt.getTime()) / 1000)

    let progress = 0
    let estimatedTimeRemaining = null

    if (generation.status === 'pending') {
      progress = 0
    } else if (generation.status === 'processing') {
      // 根据模块类型估计进度
      const moduleType = generation.module_type
      if (moduleType === 'image-gen') {
        progress = Math.min(90, (elapsedTime / 30) * 100) // 假设图片生成需要30秒
        estimatedTimeRemaining = Math.max(0, 30 - elapsedTime)
      } else if (moduleType === 'image-edit') {
        progress = Math.min(90, (elapsedTime / 45) * 100) // 图片编辑需要45秒
        estimatedTimeRemaining = Math.max(0, 45 - elapsedTime)
      } else if (moduleType === 'video-gen') {
        progress = Math.min(90, (elapsedTime / 180) * 100) // 视频生成需要3分钟
        estimatedTimeRemaining = Math.max(0, 180 - elapsedTime)
      } else if (moduleType === '3d-gen') {
        progress = Math.min(90, (elapsedTime / 300) * 100) // 3D生成需要5分钟
        estimatedTimeRemaining = Math.max(0, 300 - elapsedTime)
      }
    } else if (generation.status === 'completed') {
      progress = 100
    } else if (generation.status === 'failed') {
      progress = 0
    }

    // 获取输出文件的详细信息
    let outputFiles = []
    if (generation.output_files && generation.output_files.length > 0) {
      outputFiles = generation.output_files.map((filePath: string) => ({
        url: filePath,
        type: getFileType(filePath),
        size: null, // 这里可以从存储服务获取文件大小
        thumbnail: getThumbnailUrl(filePath)
      }))
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        generation: {
          ...generation,
          progress: progress,
          elapsedTime: elapsedTime,
          estimatedTimeRemaining: estimatedTimeRemaining,
          outputFiles: outputFiles,
          canRetry: ['failed'].includes(generation.status),
          canCancel: ['pending', 'processing'].includes(generation.status)
        }
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('获取生成状态失败:', error)
    throw error
  }
}

// 列出生成历史
async function listGenerationHistory(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const url = new URL(req.url)
    const moduleType = url.searchParams.get('moduleType')
    const status = url.searchParams.get('status')
    const projectId = url.searchParams.get('projectId')
    const limit = parseInt(url.searchParams.get('limit') || '20')
    const offset = parseInt(url.searchParams.get('offset') || '0')

    // 构建查询
    let query = supabaseClient
      .from('generation_history')
      .select(`
        *,
        projects!inner (
          id,
          name,
          module_type
        )
      `)
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1)

    if (moduleType) {
      query = query.eq('module_type', moduleType)
    }

    if (status) {
      query = query.eq('status', status)
    }

    if (projectId) {
      query = query.eq('project_id', projectId)
    }

    const { data: generations, error, count } = await query

    if (error) {
      console.error('获取生成历史失败:', error)
      return new Response(
        JSON.stringify({ error: '获取生成历史失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 为每个生成任务添加基本信息
    const enrichedGenerations = generations.map((generation: any) => ({
      ...generation,
      progress: getProgressFromStatus(generation.status, generation.created_at),
      elapsedTime: Math.floor((Date.now() - new Date(generation.created_at).getTime()) / 1000),
      canRetry: ['failed'].includes(generation.status),
      canCancel: ['pending', 'processing'].includes(generation.status)
    }))

    return new Response(
      JSON.stringify({ 
        success: true, 
        generations: enrichedGenerations,
        total: count,
        hasMore: count > offset + limit,
        moduleTypes: ['image-gen', 'image-edit', 'video-gen', '3d-gen'],
        statuses: ['pending', 'processing', 'completed', 'failed']
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('列出生成历史失败:', error)
    throw error
  }
}

// 取消生成任务
async function cancelGeneration(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const { generationId } = await req.json()

    if (!generationId) {
      return new Response(
        JSON.stringify({ error: '缺少生成任务ID' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 验证权限和状态
    const { data: generation, error: fetchError } = await supabaseClient
      .from('generation_history')
      .select('*')
      .eq('id', generationId)
      .eq('user_id', userId)
      .single()

    if (fetchError || !generation) {
      return new Response(
        JSON.stringify({ error: '生成任务不存在或无权限' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (!['pending', 'processing'].includes(generation.status)) {
      return new Response(
        JSON.stringify({ error: '只能取消待处理或处理中的任务' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 更新状态为取消
    const { data: cancelledGeneration, error: updateError } = await supabaseClient
      .from('generation_history')
      .update({ 
        status: 'failed',
        completed_at: new Date().toISOString()
      })
      .eq('id', generationId)
      .eq('user_id', userId)
      .select()
      .single()

    if (updateError) {
      console.error('取消生成任务失败:', updateError)
      return new Response(
        JSON.stringify({ error: '取消生成任务失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        generation: cancelledGeneration,
        message: '生成任务已取消'
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('取消生成任务失败:', error)
    throw error
  }
}

// 重试生成任务
async function retryGeneration(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const { generationId } = await req.json()

    if (!generationId) {
      return new Response(
        JSON.stringify({ error: '缺少生成任务ID' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 获取原始任务信息
    const { data: originalGeneration, error: fetchError } = await supabaseClient
      .from('generation_history')
      .select('*')
      .eq('id', generationId)
      .eq('user_id', userId)
      .single()

    if (fetchError || !originalGeneration) {
      return new Response(
        JSON.stringify({ error: '原始任务不存在或无权限' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (originalGeneration.status !== 'failed') {
      return new Response(
        JSON.stringify({ error: '只能重试失败的任务' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 创建新的生成任务
    const { data: newGeneration, error: createError } = await supabaseClient
      .from('generation_history')
      .insert({
        user_id: userId,
        project_id: originalGeneration.project_id,
        module_type: originalGeneration.module_type,
        prompt: originalGeneration.prompt,
        negative_prompt: originalGeneration.negative_prompt,
        model_config: originalGeneration.model_config,
        parameters: originalGeneration.parameters,
        input_files: originalGeneration.input_files,
        status: 'pending'
      })
      .select()
      .single()

    if (createError) {
      console.error('创建重试任务失败:', createError)
      return new Response(
        JSON.stringify({ error: '创建重试任务失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 这里可以触发重新生成逻辑
    // 例如：调用AI生成服务的重试端点

    return new Response(
      JSON.stringify({ 
        success: true, 
        generation: newGeneration,
        originalGenerationId: generationId,
        message: '重试任务已创建'
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('重试生成任务失败:', error)
    throw error
  }
}

// 获取生成统计信息
async function getGenerationStats(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const url = new URL(req.url)
    const period = url.searchParams.get('period') || '30d' // 7d, 30d, 90d, 1y

    // 计算时间范围
    const now = new Date()
    let startDate = new Date()
    
    switch (period) {
      case '7d':
        startDate.setDate(now.getDate() - 7)
        break
      case '30d':
        startDate.setDate(now.getDate() - 30)
        break
      case '90d':
        startDate.setDate(now.getDate() - 90)
        break
      case '1y':
        startDate.setFullYear(now.getFullYear() - 1)
        break
    }

    // 获取统计数据
    const { data: stats, error } = await supabaseClient
      .from('generation_history')
      .select('status, module_type, created_at')
      .eq('user_id', userId)
      .gte('created_at', startDate.toISOString())

    if (error) {
      console.error('获取统计数据失败:', error)
      return new Response(
        JSON.stringify({ error: '获取统计数据失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 统计各种状态的数量
    const statusCounts = stats.reduce((acc: any, stat: any) => {
      acc[stat.status] = (acc[stat.status] || 0) + 1
      return acc
    }, {})

    // 统计各模块类型的数量
    const moduleTypeCounts = stats.reduce((acc: any, stat: any) => {
      acc[stat.module_type] = (acc[stat.module_type] || 0) + 1
      return acc
    }, {})

    // 计算成功率
    const total = stats.length
    const completed = statusCounts.completed || 0
    const failed = statusCounts.failed || 0
    const successRate = total > 0 ? ((completed / total) * 100).toFixed(1) : '0'

    // 按日期统计（最近7天）
    const dailyStats = []
    for (let i = 6; i >= 0; i--) {
      const date = new Date()
      date.setDate(date.getDate() - i)
      const dateStr = date.toISOString().split('T')[0]
      
      const dayStats = stats.filter((stat: any) => 
        stat.created_at.startsWith(dateStr)
      )
      
      dailyStats.push({
        date: dateStr,
        total: dayStats.length,
        completed: dayStats.filter((s: any) => s.status === 'completed').length,
        failed: dayStats.filter((s: any) => s.status === 'failed').length
      })
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        stats: {
          period: period,
          total: total,
          completed: completed,
          failed: failed,
          pending: statusCounts.pending || 0,
          processing: statusCounts.processing || 0,
          successRate: parseFloat(successRate),
          statusCounts: statusCounts,
          moduleTypeCounts: moduleTypeCounts,
          dailyStats: dailyStats
        }
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('获取生成统计失败:', error)
    throw error
  }
}

// 辅助函数
function getProgressFromStatus(status: string, createdAt: string): number {
  const now = Date.now()
  const created = new Date(createdAt).getTime()
  const elapsed = Math.floor((now - created) / 1000)

  switch (status) {
    case 'pending':
      return 0
    case 'processing':
      return Math.min(90, (elapsed / 60) * 100) // 假设1分钟完成
    case 'completed':
      return 100
    case 'failed':
      return 0
    default:
      return 0
  }
}

function getFileType(filePath: string): string {
  const extension = filePath.split('.').pop()?.toLowerCase()
  
  const imageTypes = ['png', 'jpg', 'jpeg', 'webp']
  const videoTypes = ['mp4', 'webm', 'avi']
  const modelTypes = ['glb', 'gltf', 'obj', 'fbx']
  
  if (imageTypes.includes(extension || '')) return 'image'
  if (videoTypes.includes(extension || '')) return 'video'
  if (modelTypes.includes(extension || '')) return 'model'
  return 'unknown'
}

function getThumbnailUrl(filePath: string): string | null {
  const fileType = getFileType(filePath)
  
  if (fileType === 'image') {
    // 返回缩略图URL（可以是原图的压缩版本）
    return filePath.replace(/\.(png|jpg|jpeg|webp)$/i, '_thumb.$1')
  }
  
  return null
}