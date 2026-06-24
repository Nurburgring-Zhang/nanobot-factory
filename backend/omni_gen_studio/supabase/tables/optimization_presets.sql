CREATE TABLE optimization_presets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    module_type TEXT NOT NULL CHECK (module_type IN ('image-gen',
    'image-edit',
    'video-gen',
    '3d-gen')),
    settings JSONB DEFAULT '{}',
    usage_count INTEGER DEFAULT 0,
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);