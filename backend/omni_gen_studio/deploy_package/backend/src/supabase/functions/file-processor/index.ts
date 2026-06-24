// File Processor Edge Function
// 处理文件上传、下载和管理

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

    if (req.method === 'POST' && action === 'upload') {
      // Handle file upload
      const formData = await req.formData()
      const file = formData.get('file') as File
      const bucket = formData.get('bucket') as string || 'inputs'
      const folder = formData.get('folder') as string
      const isPublic = formData.get('public') === 'true'
      const projectId = formData.get('projectId') as string

      if (!file) {
        return new Response(
          JSON.stringify({ error: { code: 'NO_FILE', message: '未提供文件' } }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Generate unique filename
      const fileExt = file.name.split('.').pop()
      const fileName = `${Date.now()}-${Math.random().toString(36).substring(2)}.${fileExt}`
      const filePath = folder ? `${folder}/${fileName}` : fileName

      // Upload to Supabase Storage
      const { data: uploadData, error: uploadError } = await supabaseClient.storage
        .from(bucket)
        .upload(filePath, file, {
          cacheControl: '3600',
          upsert: false
        })

      if (uploadError) {
        console.error('文件上传失败:', uploadError)
        return new Response(
          JSON.stringify({ error: { code: 'UPLOAD_ERROR', message: '文件上传失败' } }),
          { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      // Get public URL
      const { data: urlData } = supabaseClient.storage
        .from(bucket)
        .getPublicUrl(filePath)

      const fileInfo = {
        id: uploadData.path,
        name: file.name,
        size: file.size,
        type: file.type,
        bucket,
        path: filePath,
        url: urlData.publicUrl,
        created_at: new Date().toISOString()
      }

      return new Response(
        JSON.stringify({ 
          success: true, 
          data: { 
            file: fileInfo, 
            url: urlData.publicUrl 
          },
          message: '文件上传成功' 
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    if (req.method === 'GET') {
      // Handle file listing or download
      if (action === 'list') {
        const bucket = url.searchParams.get('bucket')
        const projectId = url.searchParams.get('projectId')
        const fileType = url.searchParams.get('fileType')
        const limit = parseInt(url.searchParams.get('limit') || '50')
        const offset = parseInt(url.searchParams.get('offset') || '0')

        if (!bucket) {
          return new Response(
            JSON.stringify({ error: { code: 'NO_BUCKET', message: '未指定存储桶' } }),
            { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
        }

        // List files from storage
        const { data: files, error: listError } = await supabaseClient.storage
          .from(bucket)
          .list('', {
            limit,
            offset,
            sortBy: { column: 'created_at', order: 'desc' }
          })

        if (listError) {
          console.error('获取文件列表失败:', listError)
          return new Response(
            JSON.stringify({ error: { code: 'LIST_ERROR', message: '获取文件列表失败' } }),
            { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
          )
        }

        // Get public URLs for files
        const filesWithUrls = await Promise.all(
          files.map(async (file) => {
            const { data: urlData } = supabaseClient.storage
              .from(bucket)
              .getPublicUrl(file.name)
            
            return {
              ...file,
              url: urlData.publicUrl
            }
          })
        )

        return new Response(
          JSON.stringify({ 
            success: true, 
            data: { 
              files: filesWithUrls, 
              total: filesWithUrls.length, 
              hasMore: filesWithUrls.length === limit 
            }
          }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }
    }

    if (req.method === 'DELETE') {
      // Handle file deletion
      const { fileId, bucketName } = await req.json()

      if (!fileId || !bucketName) {
        return new Response(
          JSON.stringify({ error: { code: 'MISSING_PARAMS', message: '缺少必要参数' } }),
          { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      const { error: deleteError } = await supabaseClient.storage
        .from(bucketName)
        .remove([fileId])

      if (deleteError) {
        console.error('文件删除失败:', deleteError)
        return new Response(
          JSON.stringify({ error: { code: 'DELETE_ERROR', message: '文件删除失败' } }),
          { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }

      return new Response(
        JSON.stringify({ 
          success: true, 
          message: '文件已删除' 
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
    console.error('File Processor错误:', error)
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