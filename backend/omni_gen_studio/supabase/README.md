---
AIGC:
    ContentProducer: Minimax Agent AI
    ContentPropagator: Minimax Agent AI
    Label: AIGC
    ProduceID: "00000000000000000000000000000000"
    PropagateID: "00000000000000000000000000000000"
    ReservedCode1: 3045022057a33f91c86c02677707b255396de130532d5ec1b74702cd0fa495d28b4c51bf022100f80be13b9f8f0e1736083e95896f9674b8439c3b73c13b3f4f8eec71da492fd2
    ReservedCode2: 3045022016db98787fe40c4367f4829a400c60ff77a124c209e4151ce60ec5ea1b980252022100da8fdaf6f2e4350b44a27c236e77f6046aafe3968b3121675c0a108c92301a27
---

# General AIGC Enhanced Supabase Configuration
# Supabase配置文件和部署指南

## 项目设置

### 1. 创建Supabase项目
1. 访问 https://supabase.com 并创建新项目
2. 选择合适的地区（建议选择亚洲地区以获得更好性能）
3. 等待项目创建完成

### 2. 数据库设置
1. 在Supabase控制台的SQL编辑器中运行：
   ```sql
   -- 复制 supabase/migrations/202602030001_initial_schema.sql 中的内容
   -- 并在SQL编辑器中执行
   ```

### 3. 存储桶设置
在Supabase控制台的Storage页面创建以下存储桶：

#### buckets.json
```json
{
  "buckets": [
    {
      "name": "models",
      "public": false,
      "file_size_limit": 53687091200,
      "allowed_mime_types": [
        "application/octet-stream",
        "application/json",
        "text/plain",
        "image/png",
        "image/jpeg"
      ]
    },
    {
      "name": "generated-content",
      "public": true,
      "file_size_limit": 2147483648,
      "allowed_mime_types": [
        "image/png",
        "image/jpeg",
        "image/webp",
        "video/mp4",
        "video/webm",
        "model/gltf+json",
        "model/gltf-binary"
      ]
    },
    {
      "name": "user-uploads",
      "public": false,
      "file_size_limit": 1073741824,
      "allowed_mime_types": [
        "image/png",
        "image/jpeg",
        "image/webp",
        "text/plain",
        "application/json"
      ]
    },
    {
      "name": "temp-files",
      "public": false,
      "file_size_limit": 536870912,
      "allowed_mime_types": [
        "*"
      ]
    }
  ]
}
```

#### Storage策略
在Supabase控制台的Storage页面创建以下RLS策略：

```sql
-- 模型文件存储策略
CREATE POLICY "Users can upload their own models" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'models' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can view their own models" ON storage.objects FOR SELECT USING (bucket_id = 'models' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can update their own models" ON storage.objects FOR UPDATE USING (bucket_id = 'models' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can delete their own models" ON storage.objects FOR DELETE USING (bucket_id = 'models' AND auth.uid()::text = (storage.foldername(name))[1]);

-- 生成内容存储策略（公开读取）
CREATE POLICY "Anyone can view generated content" ON storage.objects FOR SELECT USING (bucket_id = 'generated-content');
CREATE POLICY "Users can upload generated content" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'generated-content' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can update their own generated content" ON storage.objects FOR UPDATE USING (bucket_id = 'generated-content' AND auth.uid()::text = (storage.foldername(name))[1]);
CREATE POLICY "Users can delete their own generated content" ON storage.objects FOR DELETE USING (bucket_id = 'generated-content' AND auth.uid()::text = (storage.foldername(name))[1]);

-- 用户上传文件策略
CREATE POLICY "Users can manage their own uploads" ON storage.objects FOR ALL USING (bucket_id = 'user-uploads' AND auth.uid()::text = (storage.foldername(name))[1]);

-- 临时文件策略
CREATE POLICY "Users can manage temp files" ON storage.objects FOR ALL USING (bucket_id = 'temp-files' AND auth.uid()::text = (storage.foldername(name))[1]);
```

### 4. 环境变量设置
在Supabase控制台的Settings > Environment Variables中添加：

```env
# AI模型配置
DIFFUSERS_CACHE_DIR=/tmp/diffusers-cache
COMFYUI_MODELS_DIR=/tmp/comfyui-models
TRANSFORMERS_CACHE_DIR=/tmp/transformers-cache

# API配置
OLLAMA_API_URL=http://localhost:11434
VLLM_API_URL=http://localhost:8001
LM_STUDIO_API_URL=http://localhost:1234

# 文件处理配置
MAX_FILE_SIZE=2147483648
TEMP_DIR=/tmp/krita-ai-temp
OUTPUT_DIR=/tmp/krita-ai-output

# GPU配置
CUDA_VISIBLE_DEVICES=0
TORCH_CUDA_ARCH_LIST="8.6;8.9;9.0"
```

### 5. Edge Functions部署
使用提供的Edge Functions代码：
- `ai-generation`: AI生成服务
- `model-management`: 模型管理服务
- `file-processor`: 文件处理服务
- `webhook-handler`: Webhook处理服务

### 6. 认证设置
在Supabase控制台的Authentication > Settings中：

1. **Site URL**: 设置为您的应用域名
2. **Additional URLs**: 添加重定向URLs
3. **启用邮箱认证**: 确保邮箱认证已启用
4. **配置SMTP**: 设置邮件发送服务

### 7. API密钥
在Supabase控制台的Settings > API中获取：
- `anon public key`: 用于客户端
- `service_role key`: 用于服务端操作

## 部署脚本

### 初始化脚本
```bash
#!/bin/bash
# supabase-setup.sh

echo "设置 General AIGC Enhanced Supabase 项目..."

# 1. 创建项目（需要手动完成）
echo "请在 https://supabase.com 创建项目"

# 2. 运行数据库迁移
echo "运行数据库迁移..."
supabase db push

# 3. 创建存储桶
echo "创建存储桶..."
supabase storage create models
supabase storage create generated-content
supabase storage create user-uploads
supabase storage create temp-files

# 4. 部署Edge Functions
echo "部署Edge Functions..."
supabase functions deploy ai-generation
supabase functions deploy model-management
supabase functions deploy file-processor
supabase functions deploy webhook-handler

# 5. 设置环境变量
echo "配置环境变量..."
supabase secrets set DIFFUSERS_CACHE_DIR=/tmp/diffusers-cache
supabase secrets set CUDA_VISIBLE_DEVICES=0

echo "Supabase 设置完成！"
```

### 本地开发
```bash
# 安装Supabase CLI
npm install -g @supabase/cli

# 登录
supabase login

# 链接项目
supabase link --project-ref YOUR_PROJECT_ID

# 本地开发
supabase start
supabase functions serve
```

## 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查项目URL和API密钥
   - 验证RLS策略设置

2. **存储上传失败**
   - 检查存储桶权限
   - 验证文件大小限制

3. **Edge Functions超时**
   - 优化函数执行时间
   - 检查外部API调用

4. **认证问题**
   - 验证Site URL设置
   - 检查邮箱配置

### 日志查看
```bash
# 查看Edge Functions日志
supabase functions logs ai-generation

# 查看数据库日志
supabase logs --project-ref YOUR_PROJECT_ID
```