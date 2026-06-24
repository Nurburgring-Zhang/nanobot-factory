-- Krita AI Enhanced Database Schema
-- 创建数据库表结构

-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 项目表
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    module_type VARCHAR(50) NOT NULL CHECK (module_type IN ('image-gen', 'image-edit', 'video-gen', '3d-gen')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 模型配置表
CREATE TABLE model_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('checkpoint', 'lora', 'controlnet', 'vae', 'clip')),
    path TEXT NOT NULL,
    weight DECIMAL(5,2) DEFAULT 1.0,
    size VARCHAR(20),
    thumbnail TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 生成历史表
CREATE TABLE generation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    module_type VARCHAR(50) NOT NULL,
    prompt TEXT,
    negative_prompt TEXT,
    model_config JSONB,
    parameters JSONB,
    input_files JSONB,
    output_files JSONB,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- 参数预设表
CREATE TABLE parameter_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    module_type VARCHAR(50) NOT NULL,
    parameters JSONB NOT NULL,
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 文件存储表
CREATE TABLE file_storage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_model_configs_user_id ON model_configs(user_id);
CREATE INDEX idx_generation_history_user_id ON generation_history(user_id);
CREATE INDEX idx_generation_history_project_id ON generation_history(project_id);
CREATE INDEX idx_parameter_presets_user_id ON parameter_presets(user_id);
CREATE INDEX idx_file_storage_user_id ON file_storage(user_id);

-- 启用行级安全 (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE parameter_presets ENABLE ROW LEVEL SECURITY;
ALTER TABLE file_storage ENABLE ROW LEVEL SECURITY;

-- RLS 策略
-- 用户只能访问自己的数据
CREATE POLICY "Users can view own data" ON users FOR ALL USING (auth.uid() = id);
CREATE POLICY "Users can view own projects" ON projects FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can view own models" ON model_configs FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can view own history" ON generation_history FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can view own presets" ON parameter_presets FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can view own files" ON file_storage FOR ALL USING (auth.uid() = user_id);

-- 公开的预设所有人都可以看到
CREATE POLICY "Public presets are viewable by everyone" ON parameter_presets FOR SELECT USING (is_public = true);