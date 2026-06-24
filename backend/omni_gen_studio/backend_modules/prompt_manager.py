#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt Manager Module for nanobot-factory
Manages prompt loading, optimization, and translation
"""

import os
import json
import random
import logging
from pathlib import Path
from typing import List, Optional, Dict
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not available")

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


class PromptManager:
    """Prompt Manager for loading, managing, and optimizing prompts."""

    DEFAULT_POSITIVE_TEMPLATES = {
        "detailed": "Provide a highly detailed description with specific elements, intricate textures, sharp focus, professional photography, 8K resolution, studio quality lighting.",
        "artistic": "Artistic masterpiece, creative composition, expressive brushwork, gallery-worthy, emotional depth, unique perspective, masterful color palette.",
        "cinematic": "Cinematic scene, dramatic lighting, movie still quality, film grain texture, anamorphic lens, movie poster style, epic scale.",
        "realistic": "Photorealistic, hyperrealistic, true-to-life details, natural lighting, life-like texture, anatomical accuracy.",
        "abstract": "Abstract art, conceptual design, minimalist composition, geometric patterns, surreal elements.",
        "anime": "Anime style, manga illustration, cel-shaded rendering, vibrant colors, dynamic pose, Japanese animation quality.",
        "portrait": "Professional portrait, studio lighting, shallow depth of field, 高画质, 杂志封面级别.",
        "landscape": "Breathtaking landscape, golden hour lighting, panoramic view, atmospheric perspective."
    }

    DEFAULT_NEGATIVE_TEMPLATES = {
        "default": "low quality, blurry, distorted, deformed, ugly, poorly drawn, bad anatomy, extra limbs, missing limbs, mutation.",
        "realistic": "cartoon, anime, illustration, painting, drawing, art, soft edges.",
        "artistic": "photorealistic, photograph, realistic shading, boring composition.",
        "cinematic": "flat lighting, dull colors, static pose, poor composition.",
        "anime": "realistic, photorealistic, 3D render, western cartoon."
    }

    def __init__(self, prompts_dir: str = ""):
        self.prompts_dir = prompts_dir
        self.prompts: List[str] = []
        self.current_index: int = 0
        self.positive_templates = self.DEFAULT_POSITIVE_TEMPLATES.copy()
        self.negative_templates = self.DEFAULT_NEGATIVE_TEMPLATES.copy()
        self.ollama_url = "http://localhost:11434/api/generate"
        self.vllm_url = "http://localhost:8000/v1/completions"
        self.lm_studio_url = "http://localhost:1234/v1/completions"
        logger.info(f"PromptManager initialized: {prompts_dir}")

    def load_prompts_from_file(self, file_path: str) -> List[str]:
        """Load prompts from a single file (txt, csv, xls, json)."""
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return []

        prompts: List[str] = []
        ext = file_path.suffix.lower()

        try:
            if ext == '.txt':
                prompts = self._load_txt(file_path)
            elif ext == '.csv':
                prompts = self._load_csv(file_path)
            elif ext in ['.xls', '.xlsx']:
                prompts = self._load_xls(file_path)
            elif ext == '.json':
                prompts = self._load_json(file_path)
            else:
                logger.warning(f"Unsupported format: {ext}")
                return []

            logger.info(f"Loaded {len(prompts)} prompts from {file_path.name}")
            return prompts
        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
            return []

    def _load_txt(self, file_path: Path) -> List[str]:
        prompts = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    prompts.append(line)
        return prompts

    def _load_csv(self, file_path: Path) -> List[str]:
        prompts = []
        df = pd.read_csv(file_path)
        if 'prompt' in df.columns:
            prompts = df['prompt'].dropna().astype(str).tolist()
        elif len(df.columns) > 0:
            prompts = df.iloc[:, 0].dropna().astype(str).tolist()
        return [p.strip() for p in prompts if p.strip()]

    def _load_xls(self, file_path: Path) -> List[str]:
        prompts = []
        if not HAS_OPENPYXL:
            return prompts
        try:
            if file_path.suffix.lower() == '.xlsx':
                df = pd.read_excel(file_path, engine='openpyxl')
            else:
                df = pd.read_excel(file_path, engine='xlrd')
            if 'prompt' in df.columns:
                prompts = df['prompt'].dropna().astype(str).tolist()
            elif len(df.columns) > 0:
                prompts = df.iloc[:, 0].dropna().astype(str).tolist()
        except Exception as e:
            logger.error(f"Excel read error: {e}")
        return [p.strip() for p in prompts if p.strip()]

    def _load_json(self, file_path: Path) -> List[str]:
        prompts = []
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    prompts.append(item)
                elif isinstance(item, dict):
                    if 'prompt' in item:
                        prompts.append(item['prompt'])
                    elif 'text' in item:
                        prompts.append(item['text'])
        elif isinstance(data, dict):
            if 'prompts' in data:
                prompts = data['prompts']
            elif 'prompt' in data:
                prompts = [data['prompt']]
        return [p.strip() for p in prompts if p.strip()]

    def load_batch_prompts(self, directory: str = "", extensions: List[str] = None) -> List[str]:
        """Load prompts from multiple files in a directory."""
        if not directory:
            directory = self.prompts_dir
        if not directory:
            logger.warning("No prompts directory specified")
            return []

        dir_path = Path(directory)
        if not dir_path.exists():
            logger.error(f"Directory not found: {directory}")
            return []

        if extensions is None:
            extensions = ['.txt', '.csv', '.xls', '.xlsx', '.json']

        all_prompts: List[str] = []
        try:
            for ext in extensions:
                for file_path in dir_path.glob(f"*{ext}"):
                    prompts = self.load_prompts_from_file(str(file_path))
                    all_prompts.extend(prompts)

            seen = set()
            unique_prompts = []
            for p in all_prompts:
                if p not in seen:
                    seen.add(p)
                    unique_prompts.append(p)

            self.prompts = unique_prompts
            self.current_index = 0
            logger.info(f"Batch loaded {len(unique_prompts)} prompts")
            return unique_prompts
        except Exception as e:
            logger.error(f"Batch loading error: {e}")
            return []

    def get_random_prompt(self) -> str:
        """Get a random prompt."""
        if not self.prompts:
            logger.warning("No prompts loaded")
            return ""
        return random.choice(self.prompts)

    def get_sequential_prompt(self) -> str:
        """Get next prompt in sequence (round-robin)."""
        if not self.prompts:
            logger.warning("No prompts loaded")
            return ""
        prompt = self.prompts[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.prompts)
        return prompt

    def add_prefix_suffix(self, prompt: str, prefix: str = "", suffix: str = "") -> str:
        """Add prefix and suffix to a prompt."""
        enhanced = prompt
        if prefix:
            enhanced = f"{prefix} {enhanced}"
        if suffix:
            enhanced = f"{enhanced} {suffix}"
        return enhanced

    def get_positive_template(self, template_name: str) -> str:
        """Get positive template by name."""
        return self.positive_templates.get(template_name.lower(), "")

    def get_negative_template(self, template_name: str) -> str:
        """Get negative template by name."""
        return self.negative_templates.get(template_name.lower(), "")

    def add_positive_template(self, name: str, template: str) -> None:
        """Add or update positive template."""
        self.positive_templates[name.lower()] = template
        logger.info(f"Added positive template: {name}")

    def add_negative_template(self, name: str, template: str) -> None:
        """Add or update negative template."""
        self.negative_templates[name.lower()] = template
        logger.info(f"Added negative template: {name}")

    def optimize_prompt(self, prompt: str, style: str = "detailed") -> str:
        """Optimize prompt using AI."""
        optimization_prompts = {
            "detailed": f"Enhance this prompt with more details, specific elements, descriptive language for AI image generation. Include lighting, texture, composition, quality tags. Prompt: {prompt}",
            "artistic": f"Transform this prompt into an artistic description emphasizing creative expression, artistic style, emotional impact. Prompt: {prompt}",
            "cinematic": f"Convert this prompt into a cinematic scene with dramatic lighting, storytelling elements. Prompt: {prompt}",
            "realistic": f"Rewrite this prompt to emphasize photorealistic details, natural lighting, true-to-life accuracy. Prompt: {prompt}"
        }
        style_lower = style.lower()
        if style_lower not in optimization_prompts:
            style_lower = "detailed"

        try:
            response = self.call_llm_api(optimization_prompts[style_lower], "ollama", "llama2")
            if response:
                logger.info(f"Prompt optimized with style: {style}")
                return response.strip()
        except Exception as e:
            logger.error(f"Optimization error: {e}")
        return prompt

    def translate_prompt(self, prompt: str, target_lang: str = "en") -> str:
        """Translate prompt using local LLM."""
        lang_names = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German"}
        lang_name = lang_names.get(target_lang.lower(), target_lang)
        translation_prompt = f"Translate to {lang_name} for AI image generation. Only output translated text. Prompt: {prompt}"

        try:
            response = self.call_llm_api(translation_prompt, "ollama", "llama2")
            if response:
                logger.info(f"Prompt translated to {target_lang}")
                return response.strip()
        except Exception as e:
            logger.error(f"Translation error: {e}")
        return prompt

    def call_llm_api(self, prompt: str, api_type: str = "ollama", model: str = "llama2") -> str:
        """Call local LLM API (ollama, vllm, lm_studio)."""
        if not HAS_REQUESTS:
            logger.error("requests not available")
            return ""

        api_type = api_type.lower()
        try:
            if api_type == "ollama":
                return self._call_ollama(prompt, model)
            elif api_type == "vllm":
                return self._call_vllm(prompt, model)
            elif api_type == "lm_studio":
                return self._call_lm_studio(prompt, model)
            else:
                logger.error(f"Unknown API type: {api_type}")
                return ""
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return ""

    def _call_ollama(self, prompt: str, model: str) -> str:
        payload = {"model": model, "prompt": prompt, "stream": False}
        response = requests.post(self.ollama_url, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json().get("response", "")
        logger.error(f"Ollama error: {response.status_code}")
        return ""

    def _call_vllm(self, prompt: str, model: str) -> str:
        payload = {"prompt": prompt, "max_tokens": 512, "temperature": 0.7}
        headers = {"Content-Type": "application/json"}
        response = requests.post(self.vllm_url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json().get("choices", [{}])[0].get("text", "")
        logger.error(f"vLLM error: {response.status_code}")
        return ""

    def _call_lm_studio(self, prompt: str, model: str) -> str:
        payload = {"prompt": prompt, "max_tokens": 512, "temperature": 0.7, "stream": False}
        headers = {"Content-Type": "application/json"}
        response = requests.post(self.lm_studio_url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json().get("choices", [{}])[0].get("text", "")
        logger.error(f"LM Studio error: {response.status_code}")
        return ""

    def enhance_prompt_with_templates(self, prompt: str, positive_template: str = "detailed", negative_template: str = "default", prefix: str = "", suffix: str = "") -> tuple:
        """Enhance prompt with positive/negative templates."""
        positive_enhancement = self.get_positive_template(positive_template)
        enhanced = prompt
        if positive_enhancement:
            enhanced = f"{prompt}, {positive_enhancement}"
        if prefix:
            enhanced = f"{prefix} {enhanced}"
        if suffix:
            enhanced = f"{enhanced} {suffix}"
        negative = self.get_negative_template(negative_template)
        return enhanced, negative

    def get_prompt_count(self) -> int:
        return len(self.prompts)

    def clear_prompts(self) -> None:
        self.prompts = []
        self.current_index = 0
        logger.info("Cleared all prompts")

    def list_templates(self) -> Dict[str, List[str]]:
        return {
            "positive": list(self.positive_templates.keys()),
            "negative": list(self.negative_templates.keys())
        }


_manager_instance: Optional[PromptManager] = None

def get_prompt_manager(prompts_dir: str = "") -> PromptManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PromptManager(prompts_dir)
    return _manager_instance

def init_prompt_manager(prompts_dir: str = "") -> PromptManager:
    global _manager_instance
    _manager_instance = PromptManager(prompts_dir)
    if prompts_dir:
        _manager_instance.load_batch_prompts(prompts_dir)
    logger.info(f"PromptManager initialized: {prompts_dir}")
    return _manager_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    print("=" * 50)
    print("Prompt Manager Test")
    print("=" * 50)

    pm = PromptManager()
    print(f"\nTemplates: {pm.list_templates()}")
    print(f"\nDetailed template: {pm.get_positive_template('detailed')}")

    test_prompt = "a beautiful sunset over the ocean"
    enhanced_pos, negative = pm.enhance_prompt_with_templates(test_prompt, "cinematic", "default")
    print(f"\nOriginal: {test_prompt}")
    print(f"Enhanced: {enhanced_pos}")
    print(f"Negative: {negative}")
    print("\n" + "=" * 50)