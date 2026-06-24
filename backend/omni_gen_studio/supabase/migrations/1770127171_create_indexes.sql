-- Migration: create_indexes
-- Created at: 1770127171

-- 为主要表创建索引以优化查询性能
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_generation_tasks_user_id ON generation_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_project_id ON generation_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_status ON generation_tasks(status);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_created_at ON generation_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_module_type ON generation_tasks(module_type);

CREATE INDEX IF NOT EXISTS idx_model_configs_user_id ON model_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_model_configs_type ON model_configs(type);
CREATE INDEX IF NOT EXISTS idx_model_configs_is_active ON model_configs(is_active);

CREATE INDEX IF NOT EXISTS idx_parameter_presets_user_id ON parameter_presets(user_id);
CREATE INDEX IF NOT EXISTS idx_parameter_presets_module_type ON parameter_presets(module_type);
CREATE INDEX IF NOT EXISTS idx_parameter_presets_is_public ON parameter_presets(is_public);
CREATE INDEX IF NOT EXISTS idx_parameter_presets_usage_count ON parameter_presets(usage_count DESC);

CREATE INDEX IF NOT EXISTS idx_optimization_presets_user_id ON optimization_presets(user_id);
CREATE INDEX IF NOT EXISTS idx_optimization_presets_module_type ON optimization_presets(module_type);
CREATE INDEX IF NOT EXISTS idx_optimization_presets_is_public ON optimization_presets(is_public);
CREATE INDEX IF NOT EXISTS idx_optimization_presets_usage_count ON optimization_presets(usage_count DESC);;