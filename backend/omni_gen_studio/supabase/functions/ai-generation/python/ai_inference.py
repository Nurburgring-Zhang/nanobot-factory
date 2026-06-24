#!/usr/bin/env python3
"""
General AIGC Enhanced - AI推理引擎
支持图片生成、图片编辑、视频生成、3D生成
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import subprocess
import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/krita_ai_inference.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    """模型配置"""
    id: str
    name: str
    type: str  # checkpoint, lora, controlnet, vae, clip
    path: str
    weight: float = 1.0
    size: Optional[str] = None
    thumbnail: Optional[str] = None

@dataclass
class GenerationParams:
    """生成参数"""
    steps: int = 20
    cfg_scale: float = 7.5
    seed: Optional[int] = None
    sampler: str = "euler"
    scheduler: str = "simple"
    resolution: str = "1024x1024"
    width: int = 1024
    height: int = 1024
    batch_size: int = 1
    batch_count: int = 1

class GeneralAIGCInference:
    """Krita AI推理引擎主类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.temp_dir = "/tmp/krita-ai-temp"
        self.output_dir = "/tmp/krita-ai-output"
        self.cache_dir = "/tmp/diffusers-cache"
        
        # 创建必要的目录
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 环境变量设置
        os.environ.update({
            'DIFFUSERS_CACHE_DIR': self.cache_dir,
            'TRANSFORMERS_CACHE_DIR': self.cache_dir,
            'CUDA_VISIBLE_DEVICES': '0'
        })
        
        self.supabase_client = None
        self.init_supabase_client()
        
    def init_supabase_client(self):
        """初始化Supabase客户端"""
        try:
            from supabase import create_client
            
            self.supabase_client = create_client(
                self.config.get('supabase_url', ''),
                self.config.get('supabase_key', '')
            )
            logger.info("Supabase客户端初始化成功")
        except ImportError:
            logger.warning("Supabase客户端导入失败，将跳过数据库更新")
            
    def check_environment(self):
        """检查运行环境"""
        logger.info("检查运行环境...")
        
        # 检查Python包
        required_packages = [
            'torch', 'torchvision', 'transformers', 'diffusers',
            'accelerate', 'xformers', 'safetensors'
        ]
        
        missing_packages = []
        for package in required_packages:
            try:
                __import__(package)
                logger.info(f"✓ {package} 已安装")
            except ImportError:
                missing_packages.append(package)
                logger.warning(f"✗ {package} 未安装")
                
        if missing_packages:
            logger.warning(f"缺少包: {missing_packages}")
            # 尝试自动安装
            self.install_missing_packages(missing_packages)
            
        # 检查GPU
        try:
            import torch
            if torch.cuda.is_available():
                logger.info(f"✓ CUDA可用: {torch.cuda.get_device_name(0)}")
                logger.info(f"✓ CUDA版本: {torch.version.cuda}")
            else:
                logger.warning("⚠ CUDA不可用，将使用CPU（性能会降低）")
        except Exception as e:
            logger.error(f"检查GPU失败: {e}")
            
    def install_missing_packages(self, packages: List[str]):
        """安装缺少的包"""
        logger.info("尝试自动安装缺少的包...")
        for package in packages:
            try:
                subprocess.run([
                    sys.executable, '-m', 'pip', 'install', package,
                    '--index-url', 'https://pypi.tuna.tsinghua.edu.cn/simple/'
                ], check=True)
                logger.info(f"✓ {package} 安装成功")
            except subprocess.CalledProcessError as e:
                logger.error(f"✗ {package} 安装失败: {e}")
                
    def load_model(self, model_config: ModelConfig):
        """加载AI模型"""
        logger.info(f"加载模型: {model_config.name} ({model_config.type})")
        
        try:
            from diffusers import DiffusionPipeline, StableDiffusionPipeline
            from transformers import AutoTokenizer, AutoModel
            
            if model_config.type == 'checkpoint':
                # 加载主模型
                if 'flux' in model_config.name.lower():
                    from diffusers import FluxPipeline
                    pipeline = FluxPipeline.from_pretrained(
                        model_config.path,
                        torch_dtype=torch.float16,
                        use_safetensors=True
                    )
                elif 'sdxl' in model_config.name.lower():
                    pipeline = StableDiffusionXLPipeline.from_pretrained(
                        model_config.path,
                        torch_dtype=torch.float16,
                        use_safetensors=True
                    )
                else:
                    pipeline = StableDiffusionPipeline.from_pretrained(
                        model_config.path,
                        torch_dtype=torch.float16,
                        use_safetensors=True
                    )
                    
                # 移动到GPU
                if torch.cuda.is_available():
                    pipeline = pipeline.to("cuda")
                    
                return pipeline
                
            elif model_config.type == 'lora':
                # LoRA模型加载逻辑
                logger.info(f"加载LoRA模型: {model_config.name}")
                return model_config
                
            elif model_config.type == 'controlnet':
                # ControlNet模型加载逻辑
                logger.info(f"加载ControlNet模型: {model_config.name}")
                return model_config
                
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            raise
            
    def optimize_prompt(self, prompt: str, module_type: str) -> str:
        """优化提示词"""
        logger.info("优化提示词...")
        
        # 尝试调用本地LLM进行优化
        try:
            ollama_url = os.getenv('OLLAMA_API_URL', 'http://localhost:11434')
            
            # 调用ollama进行提示词优化
            response = requests.post(f"{ollama_url}/api/generate", json={
                "model": "llama3.2",
                "prompt": f"优化以下{module_type}的提示词，使其更加详细和有效:\n\n{prompt}",
                "stream": False
            }, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                optimized_prompt = result.get('response', prompt)
                logger.info("提示词优化完成")
                return optimized_prompt
                
        except Exception as e:
            logger.warning(f"提示词优化失败，使用原提示词: {e}")
            
        return prompt
        
    def generate_image(self, prompt: str, model_config: ModelConfig, params: GenerationParams) -> List[str]:
        """生成图片"""
        logger.info("开始图片生成...")
        
        try:
            import torch
            from diffusers import DiffusionPipeline
            
            # 加载模型
            pipeline = self.load_model(model_config)
            
            # 优化提示词
            optimized_prompt = self.optimize_prompt(prompt, 'image-gen')
            
            # 生成参数
            generator = torch.Generator("cuda").manual_seed(params.seed) if params.seed and torch.cuda.is_available() else None
            
            # 执行生成
            result = pipeline(
                prompt=optimized_prompt,
                negative_prompt=None,  # 可以从参数获取
                num_inference_steps=params.steps,
                guidance_scale=params.cfg_scale,
                width=params.width,
                height=params.height,
                num_images_per_prompt=params.batch_size,
                generator=generator
            )
            
            # 保存生成的图片
            output_paths = []
            for i, image in enumerate(result.images):
                output_path = os.path.join(self.output_dir, f"generated_{int(time.time())}_{i}.png")
                image.save(output_path, "PNG")
                output_paths.append(output_path)
                logger.info(f"图片已保存: {output_path}")
                
            return output_paths
            
        except Exception as e:
            logger.error(f"图片生成失败: {e}")
            raise
            
    def generate_video(self, prompt: str, model_config: ModelConfig, params: GenerationParams) -> List[str]:
        """生成视频"""
        logger.info("开始视频生成...")
        
        try:
            # 暂时使用模拟方式，后续集成真正的视频生成模型
            logger.info("视频生成功能正在开发中...")
            
            # 模拟视频生成过程
            output_path = os.path.join(self.output_dir, f"video_{int(time.time())}.mp4")
            
            # 这里应该调用真正的视频生成模型（如wan2.2, ltx-2等）
            # 例如：
            # from diffusers import VideoDiffusionPipeline
            # pipeline = VideoDiffusionPipeline.from_pretrained(model_config.path)
            # result = pipeline(prompt=prompt, ...)
            
            # 临时创建占位文件
            with open(output_path, 'w') as f:
                f.write("# 视频生成功能开发中")
                
            return [output_path]
            
        except Exception as e:
            logger.error(f"视频生成失败: {e}")
            raise
            
    def generate_3d(self, prompt: str, model_config: ModelConfig, params: GenerationParams) -> List[str]:
        """生成3D模型"""
        logger.info("开始3D模型生成...")
        
        try:
            # 暂时使用模拟方式，后续集成真正的3D生成模型
            logger.info("3D生成功能正在开发中...")
            
            # 模拟3D生成过程
            output_path = os.path.join(self.output_dir, f"3d_{int(time.time())}.glb")
            
            # 这里应该调用真正的3D生成模型（如Hunyuan3D, Trellis-2等）
            # 例如：
            # from huggingface_hub import hf_hub_download
            # model = load_model(model_config.path)
            # result = model.generate_3d(input_image, prompt)
            
            # 临时创建占位文件
            with open(output_path, 'w') as f:
                f.write("# 3D生成功能开发中")
                
            return [output_path]
            
        except Exception as e:
            logger.error(f"3D生成失败: {e}")
            raise
            
    def edit_image(self, prompt: str, model_config: ModelConfig, params: GenerationParams, input_files: List[str]) -> List[str]:
        """图片编辑"""
        logger.info("开始图片编辑...")
        
        try:
            # 暂时使用模拟方式，后续集成真正的图片编辑模型
            logger.info("图片编辑功能正在开发中...")
            
            output_paths = []
            for input_file in input_files:
                output_path = os.path.join(self.output_dir, f"edited_{int(time.time())}.png")
                
                # 这里应该调用真正的图片编辑模型（如qwen edit, Flux.2 Klein等）
                # 例如：
                # from diffusers import StableDiffusionInpaintPipeline
                # pipeline = StableDiffusionInpaintPipeline.from_pretrained(model_config.path)
                # result = pipeline(prompt=prompt, image=input_image, mask=mask)
                
                # 临时创建占位文件
                with open(output_path, 'w') as f:
                    f.write("# 图片编辑功能开发中")
                    
                output_paths.append(output_path)
                
            return output_paths
            
        except Exception as e:
            logger.error(f"图片编辑失败: {e}")
            raise
            
    def update_generation_status(self, generation_id: str, status: str, output_files: List[str] = None):
        """更新生成状态到数据库"""
        if not self.supabase_client:
            return
            
        try:
            update_data = {
                'status': status,
                'completed_at': time.strftime('%Y-%m-%d %H:%M:%S') if status == 'completed' else None
            }
            
            if output_files:
                update_data['output_files'] = output_files
                
            self.supabase_client.table('generation_history').update(update_data).eq('id', generation_id).execute()
            logger.info(f"更新生成状态: {generation_id} -> {status}")
            
        except Exception as e:
            logger.error(f"更新生成状态失败: {e}")

def main():
    """主函数"""
    try:
        # 解析命令行参数
        parser = argparse.ArgumentParser()
        parser.add_argument('--config', type=str, required=True, help='JSON配置文件路径')
        args = parser.parse_args()
        
        # 读取配置
        with open(args.config, 'r') as f:
            config = json.load(f)
            
        # 初始化推理引擎
        engine = KritaAIInference(config)
        
        # 检查环境
        engine.check_environment()
        
        # 获取参数
        generation_id = config.get('generation_id')
        module_type = config.get('module_type')
        prompt = config.get('prompt')
        model_config_data = config.get('model_config')
        parameters = config.get('parameters', {})
        input_files = config.get('input_files', [])
        
        # 构建模型配置
        model_config = ModelConfig(**model_config_data)
        
        # 构建生成参数
        params = GenerationParams(**parameters)
        
        # 更新状态为处理中
        engine.update_generation_status(generation_id, 'processing')
        
        # 根据模块类型执行相应的生成
        if module_type == 'image-gen':
            output_files = engine.generate_image(prompt, model_config, params)
        elif module_type == 'image-edit':
            output_files = engine.edit_image(prompt, model_config, params, input_files)
        elif module_type == 'video-gen':
            output_files = engine.generate_video(prompt, model_config, params)
        elif module_type == '3d-gen':
            output_files = engine.generate_3d(prompt, model_config, params)
        else:
            raise ValueError(f"不支持的模块类型: {module_type}")
            
        # 更新状态为完成
        engine.update_generation_status(generation_id, 'completed', output_files)
        
        logger.info(f"生成完成: {generation_id}")
        print(json.dumps({
            'success': True,
            'generation_id': generation_id,
            'output_files': output_files,
            'module_type': module_type
        }))
        
    except Exception as e:
        logger.error(f"推理失败: {e}")
        
        # 如果有generation_id，更新状态为失败
        try:
            config = json.load(open(args.config))
            generation_id = config.get('generation_id')
            if generation_id:
                engine = KritaAIInference(config)
                engine.update_generation_status(generation_id, 'failed')
        except:
            pass
            
        print(json.dumps({
            'success': False,
            'error': str(e)
        }))
        
        sys.exit(1)

if __name__ == "__main__":
    main()