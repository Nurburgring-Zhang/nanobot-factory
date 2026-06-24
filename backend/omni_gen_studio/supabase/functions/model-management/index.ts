// General AIGC Enhanced - Model Management Service
// 处理模型上传、下载、更新、管理的Edge Function

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
      case 'list':
        return await listModels(supabaseClient, user.id, corsHeaders)
      case 'upload':
        return await uploadModel(req, supabaseClient, user.id, corsHeaders)
      case 'delete':
        return await deleteModel(req, supabaseClient, user.id, corsHeaders)
      case 'update':
        return await updateModel(req, supabaseClient, user.id, corsHeaders)
      case 'check-updates':
        return await checkModelUpdates(req, supabaseClient, user.id, corsHeaders)
      default:
        return new Response(
          JSON.stringify({ error: '无效的操作' }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
    }

  } catch (error) {
    console.error('模型管理服务错误:', error)
    return new Response(
      JSON.stringify({ 
        error: '模型管理服务内部错误',
        details: error.message 
      }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})

// 列出用户模型
async function listModels(supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const { data: models, error } = await supabaseClient
      .from('model_configs')
      .select('*')
      .eq('user_id', userId)
      .eq('is_active', true)
      .order('created_at', { ascending: false })

    if (error) {
      console.error('获取模型列表失败:', error)
      return new Response(
        JSON.stringify({ error: '获取模型列表失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        models: models,
        count: models.length 
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('列出模型失败:', error)
    throw error
  }
}

// 上传模型
async function uploadModel(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const formData = await req.formData()
    const file = formData.get('file') as File
    const modelType = formData.get('type') as string
    const modelName = formData.get('name') as string
    const description = formData.get('description') as string

    if (!file || !modelType || !modelName) {
      return new Response(
        JSON.stringify({ error: '缺少必需参数: file, type, name' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 验证文件类型
    const allowedTypes = ['safetensors', 'ckpt', 'bin', 'gguf', 'pth', 'json']
    const fileExtension = file.name.split('.').pop()?.toLowerCase()
    
    if (!allowedTypes.includes(fileExtension)) {
      return new Response(
        JSON.stringify({ error: '不支持的文件类型' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 检查文件大小（最大50GB）
    const maxSize = 50 * 1024 * 1024 * 1024
    if (file.size > maxSize) {
      return new Response(
        JSON.stringify({ error: '文件太大，最大支持50GB' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 生成文件路径
    const timestamp = Date.now()
    const fileName = `${timestamp}_${file.name}`
    const filePath = `${userId}/models/${fileName}`

    // 上传文件到存储桶
    const { data: uploadData, error: uploadError } = await supabaseClient.storage
      .from('models')
      .upload(filePath, file, {
        cacheControl: '3600',
        upsert: false
      })

    if (uploadError) {
      console.error('文件上传失败:', uploadError)
      return new Response(
        JSON.stringify({ error: '文件上传失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 获取文件URL
    const { data: urlData } = supabaseClient.storage
      .from('models')
      .getPublicUrl(filePath)

    // 创建模型配置记录
    const modelConfig = {
      user_id: userId,
      name: modelName,
      type: modelType,
      path: urlData.publicUrl,
      size: `${(file.size / (1024 * 1024 * 1024)).toFixed(2)}GB`,
      is_active: true,
      description: description || ''
    }

    const { data: modelData, error: modelError } = await supabaseClient
      .from('model_configs')
      .insert(modelConfig)
      .select()
      .single()

    if (modelError) {
      console.error('创建模型配置失败:', modelError)
      
      // 删除已上传的文件
      await supabaseClient.storage
        .from('models')
        .remove([filePath])

      return new Response(
        JSON.stringify({ error: '创建模型配置失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        model: modelData,
        message: '模型上传成功'
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('上传模型失败:', error)
    throw error
  }
}

// 删除模型
async function deleteModel(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const { modelId } = await req.json()

    if (!modelId) {
      return new Response(
        JSON.stringify({ error: '缺少模型ID' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 获取模型信息
    const { data: model, error: fetchError } = await supabaseClient
      .from('model_configs')
      .select('*')
      .eq('id', modelId)
      .eq('user_id', userId)
      .single()

    if (fetchError || !model) {
      return new Response(
        JSON.stringify({ error: '模型不存在或无权限' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 从路径提取文件名
    const filePath = model.path.replace(`${Deno.env.get('SUPABASE_URL')}/storage/v1/object/public/models/`, '')
    
    // 删除存储文件
    await supabaseClient.storage
      .from('models')
      .remove([filePath])

    // 删除数据库记录
    const { error: deleteError } = await supabaseClient
      .from('model_configs')
      .delete()
      .eq('id', modelId)
      .eq('user_id', userId)

    if (deleteError) {
      console.error('删除模型记录失败:', deleteError)
      return new Response(
        JSON.stringify({ error: '删除模型失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        message: '模型删除成功'
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('删除模型失败:', error)
    throw error
  }
}

// 更新模型
async function updateModel(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    const { modelId, updates } = await req.json()

    if (!modelId || !updates) {
      return new Response(
        JSON.stringify({ error: '缺少必需参数: modelId, updates' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 验证权限
    const { data: model, error: fetchError } = await supabaseClient
      .from('model_configs')
      .select('*')
      .eq('id', modelId)
      .eq('user_id', userId)
      .single()

    if (fetchError || !model) {
      return new Response(
        JSON.stringify({ error: '模型不存在或无权限' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // 更新模型配置
    const { data: updatedModel, error: updateError } = await supabaseClient
      .from('model_configs')
      .update({
        ...updates,
        updated_at: new Date().toISOString()
      })
      .eq('id', modelId)
      .eq('user_id', userId)
      .select()
      .single()

    if (updateError) {
      console.error('更新模型失败:', updateError)
      return new Response(
        JSON.stringify({ error: '更新模型失败' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        model: updatedModel,
        message: '模型更新成功'
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('更新模型失败:', error)
    throw error
  }
}

// 检查模型更新
async function checkModelUpdates(req: Request, supabaseClient: any, userId: string, corsHeaders: any) {
  try {
    // 这里可以实现检查Hugging Face、GitHub等平台的模型更新
    // 暂时返回模拟数据
    
    const updates = [
      {
        modelId: 'model_1',
        currentVersion: '1.0',
        latestVersion: '1.1',
        releaseDate: '2026-01-15',
        description: '性能优化和bug修复'
      },
      {
        modelId: 'model_2', 
        currentVersion: '2.0',
        latestVersion: '2.0',
        releaseDate: null,
        description: '当前版本已是最新'
      }
    ]

    return new Response(
      JSON.stringify({ 
        success: true, 
        updates: updates,
        message: '模型更新检查完成'
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )

  } catch (error) {
    console.error('检查模型更新失败:', error)
    throw error
  }
}