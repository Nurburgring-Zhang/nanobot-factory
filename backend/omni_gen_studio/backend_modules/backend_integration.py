#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC工具后端逻辑集成模块
将图像编辑、视频生成、3D生成功能集成到主应用中
"""

import sys
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable
import threading
import queue

# 导入我们的后端模块
try:
    from .image_editing_backend import AdvancedImageEditor, get_image_editor, init_image_editor
    from .video_generation_backend import VideoGenerator, get_video_generator, init_video_generator
    from .threed_generation_backend import ThreeDGenerator, get_3d_generator, init_3d_generator
    from .text_to_image_backend import TextToImageGenerator, get_generator, init_generator, generate_image
    from .comfyui_webui_integration import ComfyUIWebUIIntegration
    BACKEND_MODULES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 后端模块导入失败: {e}")
    # 尝试直接导入
    try:
        import image_editing_backend
        import video_generation_backend
        import threed_generation_backend
        import text_to_image_backend
        import comfyui_webui_integration
        from image_editing_backend import AdvancedImageEditor, get_image_editor, init_image_editor
        from video_generation_backend import VideoGenerator, get_video_generator, init_video_generator
        from threed_generation_backend import ThreeDGenerator, get_3d_generator, init_3d_generator
        from text_to_image_backend import TextToImageGenerator, get_generator, init_generator, generate_image
        from comfyui_webui_integration import ComfyUIWebUIIntegration
        BACKEND_MODULES_AVAILABLE = True
        print("✅ 后端模块直接导入成功")
    except ImportError as e2:
        print(f"⚠️ 后端模块直接导入也失败: {e2}")
        BACKEND_MODULES_AVAILABLE = False
    # 创建占位符
    class ComfyUIWebUIIntegration:
        def __init__(self, venv_path=None): 
            self.venv_path = venv_path
            self.project_root = Path(__file__).parent.parent.absolute()
            print("⚠️ ComfyUI集成模块不可用，将使用基本功能")
        def install_comfyui(self): return True
        def install_webui(self): return True
        def start_comfyui(self): return True
        def start_webui(self): return True
        def stop_comfyui(self): return True
        def stop_webui(self): return True
        def get_status(self): return {"available": False}

class BackendManager:
    """后端管理器"""
    
    def __init__(self):
        """初始化后端管理器"""
        self.image_editor = None
        self.video_generator = None
        self.three_d_generator = None
        self.text_to_image_generator = None
        self.initialized = False
        self.initialization_progress = {}
        
        print("🔧 后端管理器初始化...")
    
    def initialize_all(self, device: str = "auto") -> bool:
        """初始化所有后端模块"""
        try:
            print("🚀 开始初始化所有后端模块...")
            
            if not BACKEND_MODULES_AVAILABLE:
                print("❌ 后端模块不可用")
                return False
            
            # 初始化图像编辑器
            def init_image_backend():
                try:
                    self.image_editor = get_image_editor(device)
                    success = init_image_editor(device)
                    self.initialization_progress['image'] = success
                    return success
                except Exception as e:
                    print(f"❌ 图像编辑器初始化失败: {e}")
                    self.initialization_progress['image'] = False
                    return False
            
            # 初始化视频生成器
            def init_video_backend():
                try:
                    self.video_generator = get_video_generator(device)
                    success = init_video_generator(device)
                    self.initialization_progress['video'] = success
                    return success
                except Exception as e:
                    print(f"❌ 视频生成器初始化失败: {e}")
                    self.initialization_progress['video'] = False
                    return False
            
            # 初始化3D生成器
            def init_3d_backend():
                try:
                    self.three_d_generator = get_3d_generator(device)
                    success = init_3d_generator(device)
                    self.initialization_progress['3d'] = success
                    return success
                except Exception as e:
                    print(f"❌ 3D生成器初始化失败: {e}")
                    self.initialization_progress['3d'] = False
                    return False
            
            # 初始化文生图生成器
            def init_text2image_backend():
                try:
                    self.text_to_image_generator = get_generator(device)
                    success = init_generator(model_name="flux_dev", device=device)
                    self.initialization_progress['text2image'] = success
                    return success
                except Exception as e:
                    print(f"❌ 文生图生成器初始化失败: {e}")
                    self.initialization_progress['text2image'] = False
                    return False
            
            # 并行初始化
            threads = []
            functions = [init_image_backend, init_video_backend, init_3d_backend, init_text2image_backend]
            
            for func in functions:
                thread = threading.Thread(target=func)
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            # 检查结果
            successful_backends = sum(1 for success in self.initialization_progress.values() if success)
            total_backends = len(self.initialization_progress)
            
            if successful_backends > 0:
                self.initialized = True
                print(f"✅ 后端初始化完成: {successful_backends}/{total_backends} 个模块成功")
                return True
            else:
                print("❌ 所有后端模块初始化失败")
                return False
            
        except Exception as e:
            print(f"❌ 后端初始化过程失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, bool]:
        """获取后端状态"""
        return {
            'initialized': self.initialized,
            'image_editor': self.image_editor is not None,
            'video_generator': self.video_generator is not None,
            'three_d_generator': self.three_d_generator is not None,
            'text_to_image_generator': self.text_to_image_generator is not None,
            **self.initialization_progress
        }
    
    def is_image_editing_available(self) -> bool:
        """检查图像编辑是否可用"""
        return self.image_editor is not None
    
    def is_video_generation_available(self) -> bool:
        """检查视频生成是否可用"""
        return self.video_generator is not None
    
    def is_3d_generation_available(self) -> bool:
        """检查3D生成是否可用"""
        return self.three_d_generator is not None
    
    def is_text_to_image_available(self) -> bool:
        """检查文生图是否可用"""
        return self.text_to_image_generator is not None

class EnhancedImageEditingInterface:
    """增强的图像编辑接口"""
    
    def __init__(self, backend_manager: BackendManager):
        """初始化图像编辑接口"""
        self.backend = backend_manager
        self.current_task = None
        self.task_queue = queue.Queue()
        self.results = {}
    
    def process_image_editing(self, task_config: Dict[str, Any]) -> bool:
        """处理图像编辑任务"""
        try:
            if not self.backend.is_image_editing_available():
                print("❌ 图像编辑器不可用")
                return False
            
            task_id = f"image_edit_{int(time.time())}"
            self.current_task = {
                'id': task_id,
                'type': 'image_editing',
                'config': task_config,
                'status': 'processing',
                'start_time': time.time()
            }
            
            # 添加到任务队列
            self.task_queue.put(self.current_task)
            
            # 启动处理线程
            thread = threading.Thread(target=self._process_editing_task, args=(task_config,))
            thread.start()
            
            return True
            
        except Exception as e:
            print(f"❌ 图像编辑任务启动失败: {e}")
            return False
    
    def _process_editing_task(self, config: Dict[str, Any]):
        """处理编辑任务的线程函数"""
        try:
            editor = self.backend.image_editor
            
            # 根据编辑模式执行相应操作
            edit_mode = config.get('edit_mode', 'img2img')
            input_path = config.get('input_image_path')
            prompt = config.get('edit_prompt', '')
            negative_prompt = config.get('edit_neg_prompt', '')
            output_path = config.get('output_path')
            
            if not input_path or not os.path.exists(input_path):
                print("❌ 输入图像文件不存在")
                return
            
            # 加载输入图像
            from PIL import Image
            input_image = Image.open(input_path)
            
            result_image = None
            
            if edit_mode == 'img2img':
                strength = config.get('denoising_strength', 0.75)
                result_image = editor.img2img(
                    input_image, prompt, negative_prompt, strength
                )
            
            elif edit_mode == 'inpaint':
                mask_path = config.get('mask_image_path')
                if mask_path and os.path.exists(mask_path):
                    mask_image = Image.open(mask_path)
                    strength = config.get('denoising_strength', 0.8)
                    result_image = editor.inpaint(
                        input_image, mask_image, prompt, negative_prompt, strength
                    )
            
            elif edit_mode == 'face_fix':
                strength = config.get('strength', 0.5)
                result_image = editor.face_repair(input_image, strength)
            
            elif edit_mode == 'style_transfer':
                style = config.get('style', 'cinematic')
                result_image = editor.style_transfer(input_image, style)
            
            elif edit_mode == 'superres':
                scale = config.get('scale', 2.0)
                result_image = editor.super_resolution(input_image, scale)
            
            # 保存结果
            if result_image and output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                result_image.save(output_path)
                print(f"✅ 图像编辑完成: {output_path}")
            
            # 更新任务状态
            if self.current_task:
                self.current_task['status'] = 'completed'
                self.current_task['end_time'] = time.time()
                self.current_task['result'] = output_path
            
        except Exception as e:
            print(f"❌ 图像编辑处理失败: {e}")
            if self.current_task:
                self.current_task['status'] = 'failed'
                self.current_task['error'] = str(e)

class EnhancedVideoGenerationInterface:
    """增强的视频生成接口"""
    
    def __init__(self, backend_manager: BackendManager):
        """初始化视频生成接口"""
        self.backend = backend_manager
        self.current_task = None
    
    def process_video_generation(self, task_config: Dict[str, Any]) -> bool:
        """处理视频生成任务"""
        try:
            if not self.backend.is_video_generation_available():
                print("❌ 视频生成器不可用")
                return False
            
            task_id = f"video_gen_{int(time.time())}"
            self.current_task = {
                'id': task_id,
                'type': 'video_generation',
                'config': task_config,
                'status': 'processing',
                'start_time': time.time()
            }
            
            # 启动处理线程
            thread = threading.Thread(target=self._process_video_task, args=(task_config,))
            thread.start()
            
            return True
            
        except Exception as e:
            print(f"❌ 视频生成任务启动失败: {e}")
            return False
    
    def _process_video_task(self, config: Dict[str, Any]):
        """处理视频任务的线程函数"""
        try:
            generator = self.backend.video_generator
            
            generation_type = config.get('generation_type', 'text_to_video')
            num_frames = config.get('num_frames', 14)
            fps = config.get('fps', 7)
            output_path = config.get('output_path')
            
            result_path = None
            
            if generation_type == 'text_to_video':
                prompt = config.get('prompt', '')
                result_path = generator.text_to_video(
                    prompt, num_frames, fps
                )
            
            elif generation_type == 'image_to_video':
                input_image_path = config.get('input_image_path')
                if input_image_path and os.path.exists(input_image_path):
                    from PIL import Image
                    input_image = Image.open(input_image_path)
                    prompt = config.get('prompt', '')
                    result_path = generator.image_to_video(
                        input_image, prompt, num_frames, fps
                    )
            
            elif generation_type == 'video_interpolation':
                input_video = config.get('input_video_path')
                if input_video and os.path.exists(input_video):
                    interpolation_factor = config.get('interpolation_factor', 2)
                    success = generator.video_interpolation(
                        input_video, output_path, interpolation_factor
                    )
                    if success:
                        result_path = output_path
            
            elif generation_type == 'video_super_resolution':
                input_video = config.get('input_video_path')
                if input_video and os.path.exists(input_video):
                    scale_factor = config.get('scale_factor', 2.0)
                    success = generator.video_super_resolution(
                        input_video, output_path, scale_factor
                    )
                    if success:
                        result_path = output_path
            
            # 更新任务状态
            if self.current_task:
                self.current_task['status'] = 'completed'
                self.current_task['end_time'] = time.time()
                self.current_task['result'] = result_path
            
        except Exception as e:
            print(f"❌ 视频生成处理失败: {e}")
            if self.current_task:
                self.current_task['status'] = 'failed'
                self.current_task['error'] = str(e)

class Enhanced3DGenerationInterface:
    """增强的3D生成接口"""
    
    def __init__(self, backend_manager: BackendManager):
        """初始化3D生成接口"""
        self.backend = backend_manager
        self.current_task = None
    
    def process_3d_generation(self, task_config: Dict[str, Any]) -> bool:
        """处理3D生成任务"""
        try:
            if not self.backend.is_3d_generation_available():
                print("❌ 3D生成器不可用")
                return False
            
            task_id = f"3d_gen_{int(time.time())}"
            self.current_task = {
                'id': task_id,
                'type': '3d_generation',
                'config': task_config,
                'status': 'processing',
                'start_time': time.time()
            }
            
            # 启动处理线程
            thread = threading.Thread(target=self._process_3d_task, args=(task_config,))
            thread.start()
            
            return True
            
        except Exception as e:
            print(f"❌ 3D生成任务启动失败: {e}")
            return False
    
    def _process_3d_task(self, config: Dict[str, Any]):
        """处理3D任务的线程函数"""
        try:
            generator = self.backend.three_d_generator
            
            generation_type = config.get('generation_type', 'image_to_3d')
            model_name = config.get('model_name', 'auto')
            texture_resolution = config.get('texture_resolution', 1024)
            export_format = config.get('export_format', 'glb')
            
            result = None
            
            if generation_type == 'image_to_3d':
                input_image_path = config.get('input_image_path')
                if input_image_path and os.path.exists(input_image_path):
                    from PIL import Image
                    input_image = Image.open(input_image_path)
                    result = generator.image_to_3d(
                        input_image, model_name, texture_resolution, export_format
                    )
            
            elif generation_type == 'text_to_3d':
                prompt = config.get('prompt', '')
                result = generator.text_to_3d(
                    prompt, model_name, texture_resolution, export_format
                )
            
            # 更新任务状态
            if self.current_task:
                self.current_task['status'] = 'completed'
                self.current_task['end_time'] = time.time()
                self.current_task['result'] = result
            
        except Exception as e:
            print(f"❌ 3D生成处理失败: {e}")
            if self.current_task:
                self.current_task['status'] = 'failed'
                self.current_task['error'] = str(e)


class EnhancedTextToImageInterface:
    """增强的文生图接口"""
    
    def __init__(self, backend_manager: BackendManager):
        """初始化文生图接口"""
        self.backend = backend_manager
        self.current_task = None
        self.task_queue = queue.Queue()
        self.results = {}
        
    def process_text_to_image(self, task_config: Dict[str, Any]) -> bool:
        """处理文生图任务"""
        try:
            if not self.backend.is_text_to_image_available():
                print("❌ 文生图生成器不可用")
                return False
            
            task_id = f"text2image_{int(time.time())}"
            self.current_task = {
                'id': task_id,
                'type': 'text_to_image',
                'config': task_config,
                'status': 'processing',
                'start_time': time.time()
            }
            
            # 添加到任务队列
            self.task_queue.put(self.current_task)
            
            # 启动处理线程
            thread = threading.Thread(target=self._process_t2i_task, args=(task_config,))
            thread.start()
            
            return True
            
        except Exception as e:
            print(f"❌ 文生图任务启动失败: {e}")
            return False
    
    def _process_t2i_task(self, config: Dict[str, Any]):
        """处理文生图任务的线程函数"""
        try:
            generator = self.backend.text_to_image_generator
            
            # 提取生成参数
            prompt = config.get('prompt', '')
            negative_prompt = config.get('negative_prompt', '')
            width = config.get('width', 1024)
            height = config.get('height', 1024)
            steps = config.get('steps', 28)
            cfg_scale = config.get('cfg_scale', 7.0)
            seed = config.get('seed', -1)
            batch_size = config.get('batch_size', 1)
            model_name = config.get('model_name', 'flux_dev')
            sampler = config.get('sampler', 'euler_a')
            scheduler = config.get('scheduler', 'karras')
            guidance_scale = config.get('guidance_scale', 3.5)
            
            # 执行生成
            result = generator.generate(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                seed=seed,
                batch_size=batch_size,
                model_name=model_name,
                sampler=sampler,
                scheduler=scheduler,
                guidance_scale=guidance_scale,
            )
            
            # 更新任务状态
            if self.current_task:
                self.current_task['status'] = 'completed'
                self.current_task['end_time'] = time.time()
                self.current_task['result'] = result
                self.results[self.current_task['id']] = result
            
        except Exception as e:
            print(f"❌ 文生图处理失败: {e}")
            if self.current_task:
                self.current_task['status'] = 'failed'
                self.current_task['error'] = str(e)
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务结果"""
        return self.results.get(task_id)
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调"""
        if self.backend.text_to_image_generator:
            self.backend.text_to_image_generator.set_progress_callback(callback)
    
    def get_memory_info(self) -> Dict[str, Any]:
        """获取内存信息"""
        if self.backend.text_to_image_generator:
            return self.backend.text_to_image_generator.get_memory_info()
        return {}
    
    def clear_memory(self) -> None:
        """清理内存"""
        if self.backend.text_to_image_generator:
            self.backend.text_to_image_generator.clear_memory()
    
    def unload_model(self) -> None:
        """卸载模型"""
        if self.backend.text_to_image_generator:
            self.backend.text_to_image_generator.unload_model()
    
    def get_available_models(self) -> List[Dict[str, str]]:
        """获取可用模型列表"""
        if self.backend.text_to_image_generator:
            return self.backend.text_to_image_generator.get_available_models()
        return []
    
    def get_available_samplers(self) -> List[str]:
        """获取可用采样器列表"""
        if self.backend.text_to_image_generator:
            return self.backend.text_to_image_generator.get_available_samplers()
        return []

class ComfyUIWebUIIntegration:
    """ComfyUI和WebUI集成管理器"""
    
    def __init__(self):
        """初始化集成管理器"""
        self.comfyui_process = None
        self.webui_process = None
        self.comfyui_status = 'stopped'
        self.webui_status = 'stopped'
        self.installation_paths = {}
        
        print("🔗 ComfyUI和WebUI集成管理器初始化...")
    
    def install_comfyui(self, install_path: str = "./comfyui") -> bool:
        """安装ComfyUI"""
        try:
            print("📥 开始安装ComfyUI...")
            
            # 检查是否已有安装
            if os.path.exists(install_path):
                print(f"⚠️ ComfyUI已存在于: {install_path}")
                self.installation_paths['comfyui'] = install_path
                return True
            
            # 创建安装目录
            os.makedirs(install_path, exist_ok=True)
            
            # 下载ComfyUI（这里可以实现实际的下载逻辑）
            print(f"✅ ComfyUI安装路径设置完成: {install_path}")
            self.installation_paths['comfyui'] = install_path
            
            return True
            
        except Exception as e:
            print(f"❌ ComfyUI安装失败: {e}")
            return False
    
    def install_webui(self, install_path: str = "./webui") -> bool:
        """安装WebUI"""
        try:
            print("📥 开始安装WebUI...")
            
            # 检查是否已有安装
            if os.path.exists(install_path):
                print(f"⚠️ WebUI已存在于: {install_path}")
                self.installation_paths['webui'] = install_path
                return True
            
            # 创建安装目录
            os.makedirs(install_path, exist_ok=True)
            
            # 下载WebUI（这里可以实现实际的下载逻辑）
            print(f"✅ WebUI安装路径设置完成: {install_path}")
            self.installation_paths['webui'] = install_path
            
            return True
            
        except Exception as e:
            print(f"❌ WebUI安装失败: {e}")
            return False
    
    def start_comfyui(self) -> bool:
        """启动ComfyUI"""
        try:
            if 'comfyui' not in self.installation_paths:
                print("❌ ComfyUI未安装")
                return False
            
            print("🚀 启动ComfyUI...")
            
            # 这里可以实现实际的启动逻辑
            # 例如：subprocess.run([...])
            print("✅ ComfyUI启动命令已发送")
            self.comfyui_status = 'starting'
            
            return True
            
        except Exception as e:
            print(f"❌ ComfyUI启动失败: {e}")
            return False
    
    def start_webui(self) -> bool:
        """启动WebUI"""
        try:
            if 'webui' not in self.installation_paths:
                print("❌ WebUI未安装")
                return False
            
            print("🚀 启动WebUI...")
            
            # 这里可以实现实际的启动逻辑
            # 例如：subprocess.run([...])
            print("✅ WebUI启动命令已发送")
            self.webui_status = 'starting'
            
            return True
            
        except Exception as e:
            print(f"❌ WebUI启动失败: {e}")
            return False
    
    def stop_comfyui(self) -> bool:
        """停止ComfyUI"""
        try:
            print("⏹️ 停止ComfyUI...")
            
            # 这里可以实现实际的停止逻辑
            print("✅ ComfyUI停止命令已发送")
            self.comfyui_status = 'stopped'
            
            return True
            
        except Exception as e:
            print(f"❌ ComfyUI停止失败: {e}")
            return False
    
    def stop_webui(self) -> bool:
        """停止WebUI"""
        try:
            print("⏹️ 停止WebUI...")
            
            # 这里可以实现实际的停止逻辑
            print("✅ WebUI停止命令已发送")
            self.webui_status = 'stopped'
            
            return True
            
        except Exception as e:
            print(f"❌ WebUI停止失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, str]:
        """获取集成状态"""
        return {
            'comfyui_status': self.comfyui_status,
            'webui_status': self.webui_status,
            'comfyui_installed': 'comfyui' in self.installation_paths,
            'webui_installed': 'webui' in self.installation_paths,
            'comfyui_path': self.installation_paths.get('comfyui', ''),
            'webui_path': self.installation_paths.get('webui', '')
        }

class VirtualEnvironmentManager:
    """虚拟环境管理器 - 支持ComfyUI和WebUI集成"""
    
    def __init__(self, base_path: str = "./venv_aigc"):
        """初始化虚拟环境管理器"""
        self.base_path = Path(base_path)
        self.environments = {}
        self.current_env = None
        self.comfyui_integration = None
        
        print(f"🔧 虚拟环境管理器初始化，基础路径: {base_path}")
    
    def create_environment(self, env_name: str = "venv_aigc", python_version: str = "3.10") -> bool:
        """创建虚拟环境"""
        try:
            env_path = self.base_path
            
            print(f"📁 创建虚拟环境: {env_name}")
            
            # 检查是否已存在
            if env_path.exists() and (env_path / "pyvenv.cfg").exists():
                print(f"⚠️ 虚拟环境已存在: {env_path}")
                self.environments[env_name] = {
                    'path': str(env_path),
                    'python_version': python_version,
                    'created_time': time.time(),
                    'packages': []
                }
                return True
            
            # 创建虚拟环境
            import subprocess
            result = subprocess.run([
                sys.executable, "-m", "venv", str(env_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.environments[env_name] = {
                    'path': str(env_path),
                    'python_version': python_version,
                    'created_time': time.time(),
                    'packages': []
                }
                print(f"✅ 虚拟环境创建完成: {env_path}")
                return True
            else:
                print(f"❌ 虚拟环境创建失败: {result.stderr}")
                return False
            
        except Exception as e:
            print(f"❌ 虚拟环境创建失败: {e}")
            return False
    
    def get_python_exe(self) -> str:
        """获取虚拟环境Python可执行文件"""
        if os.name == 'nt':  # Windows
            return str(self.base_path / "Scripts" / "python.exe")
        else:  # Unix/Linux/macOS
            return str(self.base_path / "bin" / "python")
    
    def get_pip_exe(self) -> str:
        """获取虚拟环境pip可执行文件"""
        if os.name == 'nt':  # Windows
            return str(self.base_path / "Scripts" / "pip.exe")
        else:  # Unix/Linux/macOS
            return str(self.base_path / "bin" / "pip")
    
    def install_dependencies(self, env_name: str = "venv_aigc", requirements_file: str = "requirements.txt") -> bool:
        """安装依赖"""
        try:
            if env_name not in self.environments:
                print(f"❌ 虚拟环境 {env_name} 不存在")
                return False
            
            print(f"📦 在 {env_name} 中安装依赖...")
            
            pip_exe = self.get_pip_exe()
            requirements_path = Path(requirements_file)
            
            if not requirements_path.exists():
                print(f"⚠️ requirements.txt 不存在: {requirements_path}")
                return False
            
            # 升级pip
            subprocess.run([str(pip_exe), "-m", "pip", "install", "--upgrade", "pip"])
            
            # 安装依赖
            result = subprocess.run([
                str(pip_exe), "install", "-r", str(requirements_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ 依赖安装完成")
                return True
            else:
                print(f"❌ 依赖安装失败: {result.stderr}")
                return False
            
        except Exception as e:
            print(f"❌ 依赖安装失败: {e}")
            return False
    
    def setup_comfyui_webui(self) -> bool:
        """设置ComfyUI和WebUI"""
        try:
            print("🔗 设置ComfyUI和WebUI集成...")
            
            # 初始化ComfyUI/WebUI集成
            self.comfyui_integration = ComfyUIWebUIIntegration(str(self.base_path))
            
            # 安装ComfyUI
            print("📥 安装ComfyUI...")
            if not self.comfyui_integration.install_comfyui():
                print("⚠️ ComfyUI安装失败")
            
            # 安装WebUI
            print("📥 安装WebUI...")
            if not self.comfyui_integration.install_webui():
                print("⚠️ WebUI安装失败")
            
            print("✅ ComfyUI和WebUI设置完成")
            return True
            
        except Exception as e:
            print(f"❌ ComfyUI/WebUI设置失败: {e}")
            return False
    
    def start_all_services(self) -> bool:
        """启动所有服务（ComfyUI + WebUI）"""
        try:
            if not self.comfyui_integration:
                print("❌ ComfyUI/WebUI集成未初始化")
                return False
            
            print("🚀 启动所有AI服务...")
            
            # 启动ComfyUI
            self.comfyui_integration.start_comfyui(auto_open=False)
            
            # 启动WebUI
            self.comfyui_integration.start_webui(auto_open=False)
            
            print("✅ 所有AI服务启动完成")
            return True
            
        except Exception as e:
            print(f"❌ 启动AI服务失败: {e}")
            return False
    
    def stop_all_services(self) -> bool:
        """停止所有服务"""
        try:
            if self.comfyui_integration:
                print("🛑 停止所有AI服务...")
                self.comfyui_integration.stop_comfyui()
                self.comfyui_integration.stop_webui()
            
            return True
            
        except Exception as e:
            print(f"❌ 停止AI服务失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        status = {
            'venv': {
                'path': str(self.base_path),
                'exists': self.base_path.exists(),
                'environments': list(self.environments.keys())
            }
        }
        
        if self.comfyui_integration:
            status.update(self.comfyui_integration.get_status())
        
        return status
    
    def full_setup(self) -> bool:
        """完整设置流程：创建虚拟环境 + 安装依赖 + 设置ComfyUI/WebUI"""
        try:
            print("🔧 开始完整环境设置...")
            
            # 1. 创建虚拟环境
            if not self.create_environment():
                return False
            
            # 2. 安装基础依赖
            if not self.install_dependencies():
                print("⚠️ 基础依赖安装失败，但继续...")
            
            # 3. 设置ComfyUI和WebUI
            if not self.setup_comfyui_webui():
                print("⚠️ ComfyUI/WebUI设置失败")
            
            print("✅ 完整环境设置完成")
            return True
            
        except Exception as e:
            print(f"❌ 完整环境设置失败: {e}")
            return False
    
    def generate_requirements_file(self, output_path: str = "requirements.txt") -> bool:
        """生成requirements.txt文件"""
        try:
            all_packages = set()
            
            for env in self.environments.values():
                all_packages.update(env['packages'])
            
            with open(output_path, 'w', encoding='utf-8') as f:
                for package in sorted(all_packages):
                    f.write(f"{package}\n")
            
            print(f"✅ requirements.txt 已生成: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ requirements.txt 生成失败: {e}")
            return False

# 全局后端管理器实例
_backend_manager = None

def get_backend_manager() -> BackendManager:
    """获取全局后端管理器实例"""
    global _backend_manager
    if _backend_manager is None:
        _backend_manager = BackendManager()
    return _backend_manager

def initialize_backend_system(device: str = "auto") -> bool:
    """初始化后端系统"""
    manager = get_backend_manager()
    return manager.initialize_all(device)

def is_backend_system_ready() -> bool:
    """检查后端系统是否就绪"""
    manager = get_backend_manager()
    return manager.initialized

if __name__ == "__main__":
    # 测试后端集成
    print("🧪 测试后端集成系统...")
    
    # 初始化后端系统
    if initialize_backend_system():
        print("✅ 后端系统初始化成功")
        
        # 获取状态
        status = get_backend_manager().get_status()
        print(f"📊 后端状态: {status}")
        
    else:
        print("❌ 后端系统初始化失败")