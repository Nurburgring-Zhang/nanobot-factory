#!/usr/bin/env python3
"""
Nanobot Factory - Skill Adapter (Security Enhanced)
Skill compatibility and management system with path traversal protection

@author MiniMax Agent
@date 2026-02-25
@description 修复版：增加路径穿越防护、改进解析逻辑、增强错误处理
"""

import os
import json
import yaml
import logging
import hashlib
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# Security Utilities
# ============================================================================

class PathSecurity:
    """Path security validation utilities"""

    @staticmethod
    def validate_path(path: Path, allowed_base: Path) -> Optional[Path]:
        """
        Validate that path is within allowed base directory.
        Prevents path traversal attacks.

        Args:
            path: Path to validate
            allowed_base: Base directory that path must be within

        Returns:
            Resolved path if valid, None if invalid
        """
        try:
            # Resolve to absolute path
            resolved = path.resolve()

            # Resolve allowed base
            allowed = allowed_base.resolve()

            # Check if path is within allowed base
            if not str(resolved).startswith(str(allowed)):
                logger.warning(f"Path {path} is outside allowed base {allowed_base}")
                return None

            return resolved

        except Exception as e:
            logger.error(f"Error validating path {path}: {e}")
            return None

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename to prevent injection.
        """
        # Remove dangerous characters
        filename = re.sub(r'[^\w\s\-_\.]', '', filename)

        # Limit length
        max_length = 255
        if len(filename) > max_length:
            name, ext = os.path.splitext(filename)
            filename = name[:max_length - len(ext)] + ext

        return filename

    @staticmethod
    def is_hidden(path: Path) -> bool:
        """Check if path is a hidden file or directory"""
        return path.name.startswith('.')


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class SkillFunction:
    """Represents a skill function/tool"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: Optional[Dict[str, Any]] = None
    examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Skill:
    """Represents a loaded skill"""
    id: str
    name: str
    description: str
    version: str
    author: str
    category: str
    functions: List[SkillFunction] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    loaded_at: Optional[str] = None


# ============================================================================
# Skill Parser
# ============================================================================

class SkillParser:
    """
    Parser for various skill formats.
    Supports: SKILL.md, .skill (YAML), JSON
    """

    @staticmethod
    def parse_skill_markdown(content: str, file_path: Path) -> Optional[Skill]:
        """
        Parse SKILL.md format.
        """
        try:
            # Split frontmatter and content
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) < 3:
                    return None

                frontmatter_raw = parts[1].strip()
                content_body = parts[2].strip()

                # Parse YAML frontmatter
                frontmatter = yaml.safe_load(frontmatter_raw)
                if not frontmatter:
                    return None
            else:
                # No frontmatter, try to extract from content
                frontmatter = {}
                content_body = content

            # Extract fields from frontmatter
            skill_id = frontmatter.get('id') or PathSecurity.sanitize_filename(
                frontmatter.get('name', file_path.stem)
            )
            name = frontmatter.get('name', skill_id)
            version = frontmatter.get('version', '1.0.0')
            author = frontmatter.get('author', 'Unknown')
            category = frontmatter.get('category', 'General')
            description = frontmatter.get('description', '')

            # Try to extract description from body if not in frontmatter
            if not description and content_body:
                desc_match = re.search(r'## Description\s*\n\s*(.+?)(?=\n##|\Z)',
                                       content_body, re.DOTALL)
                if desc_match:
                    description = desc_match.group(1).strip()

            # Parse functions
            functions = SkillParser._parse_functions(content_body)

            return Skill(
                id=skill_id,
                name=name,
                description=description,
                version=version,
                author=author,
                category=category,
                functions=functions,
                metadata={"source_file": str(file_path)},
                loaded_at=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Error parsing skill markdown {file_path}: {e}")
            return None

    @staticmethod
    def _parse_functions(content: str) -> List[SkillFunction]:
        """Parse function definitions from markdown content"""
        functions = []

        # Find all function sections
        pattern = r'### (\w+)\s*\n(.*?)(?=\n### |\n## |\Z)'
        matches = re.finditer(pattern, content, re.DOTALL)

        for match in matches:
            func_name = match.group(1)
            func_desc = match.group(2).strip()

            # Try to extract parameter info
            params = {}
            param_pattern = r'- (\w+): (\w+(?:\s+\w+)?)'
            param_matches = re.finditer(param_pattern, func_desc)
            for pm in param_matches:
                params[pm.group(1)] = {"type": pm.group(2)}

            # Extract description (before params)
            desc_lines = []
            for line in func_desc.split('\n'):
                if line.strip().startswith('- '):
                    break
                desc_lines.append(line)

            description = '\n'.join(desc_lines).strip()

            functions.append(SkillFunction(
                name=func_name,
                description=description,
                parameters=params
            ))

        return functions

    @staticmethod
    def parse_skill_yaml(content: str, file_path: Path) -> Optional[Skill]:
        """Parse .skill YAML format"""
        try:
            data = yaml.safe_load(content)
            if not data:
                return None

            # Parse functions
            functions = []
            for func_data in data.get('functions', []):
                functions.append(SkillFunction(
                    name=func_data.get('name', ''),
                    description=func_data.get('description', ''),
                    parameters=func_data.get('parameters', {}),
                    returns=func_data.get('returns'),
                    examples=func_data.get('examples', [])
                ))

            return Skill(
                id=data.get('id', PathSecurity.sanitize_filename(file_path.stem)),
                name=data.get('name', file_path.stem),
                description=data.get('description', ''),
                version=data.get('version', '1.0.0'),
                author=data.get('author', 'Unknown'),
                category=data.get('category', 'General'),
                functions=functions,
                config=data.get('config', {}),
                metadata={"source_file": str(file_path)},
                loaded_at=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Error parsing skill yaml {file_path}: {e}")
            return None

    @staticmethod
    def parse_skill_json(content: str, file_path: Path) -> Optional[Skill]:
        """Parse JSON skill format"""
        try:
            data = json.loads(content)

            functions = []
            for func_data in data.get('functions', []):
                functions.append(SkillFunction(
                    name=func_data.get('name', ''),
                    description=func_data.get('description', ''),
                    parameters=func_data.get('parameters', {}),
                    returns=func_data.get('returns'),
                    examples=func_data.get('examples', [])
                ))

            return Skill(
                id=data.get('id', PathSecurity.sanitize_filename(file_path.stem)),
                name=data.get('name', file_path.stem),
                description=data.get('description', ''),
                version=data.get('version', '1.0.0'),
                author=data.get('author', 'Unknown'),
                category=data.get('category', 'General'),
                functions=functions,
                config=data.get('config', {}),
                metadata={"source_file": str(file_path)},
                loaded_at=datetime.now().isoformat()
            )

        except Exception as e:
            logger.error(f"Error parsing skill json {file_path}: {e}")
            return None


# ============================================================================
# Skill Adapter
# ============================================================================

class SkillAdapter:
    """
    Skill management and loading system.
    Handles loading, parsing, and conversion of skills.
    """

    def __init__(self, skills_dir: str = "./skills"):
        self.skills_dir = Path(skills_dir).resolve()
        self.loaded_skills: Dict[str, Skill] = {}
        self._loaded_sources: Dict[str, str] = {}  # skill_id -> source path
        self._parser = SkillParser()

    def initialize(self) -> bool:
        """Initialize and load all skills from directory"""
        try:
            # Create skills directory if it doesn't exist
            self.skills_dir.mkdir(parents=True, exist_ok=True)

            # Load all skills
            self._load_all_skills()

            logger.info(f"Loaded {len(self.loaded_skills)} skills from {self.skills_dir}")
            return True

        except Exception as e:
            logger.error(f"Error initializing skill adapter: {e}")
            return False

    def _load_all_skills(self):
        """Load all skills from the skills directory"""
        if not self.skills_dir.exists():
            return

        # Supported file extensions
        extensions = {
            '.md': self._parser.parse_skill_markdown,
            '.skill': self._parser.parse_skill_yaml,
            '.yaml': self._parser.parse_skill_yaml,
            '.yml': self._parser.parse_skill_yaml,
            '.json': self._parser.parse_skill_json
        }

        # Recursively find all skill files
        for file_path in self.skills_dir.rglob('*'):
            # Skip directories and hidden files
            if not file_path.is_file() or PathSecurity.is_hidden(file_path):
                continue

            # Validate path is within skills directory
            if not PathSecurity.validate_path(file_path, self.skills_dir):
                logger.warning(f"Skipping file outside skills directory: {file_path}")
                continue

            # Parse based on extension
            ext = file_path.suffix.lower()
            if ext in extensions:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    parse_func = extensions[ext]
                    skill = parse_func(content, file_path)

                    if skill:
                        self.loaded_skills[skill.id] = skill
                        self._loaded_sources[skill.id] = str(file_path)
                        logger.info(f"Loaded skill: {skill.name} ({skill.id})")

                except Exception as e:
                    logger.error(f"Error loading skill from {file_path}: {e}")

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a loaded skill by ID"""
        return self.loaded_skills.get(skill_id)

    def get_all_skills(self) -> List[Skill]:
        """Get all loaded skills"""
        return list(self.loaded_skills.values())

    def get_skills_by_category(self, category: str) -> List[Skill]:
        """Get skills filtered by category"""
        return [s for s in self.loaded_skills.values() if s.category == category]

    def get_categories(self) -> List[str]:
        """Get list of all categories"""
        return list(set(s.category for s in self.loaded_skills.values()))

    def reload_skill(self, skill_id: str) -> bool:
        """Reload a specific skill from disk"""
        if skill_id not in self._loaded_sources:
            return False

        source_path = Path(self._loaded_sources[skill_id])

        if not source_path.exists():
            logger.error(f"Skill source file not found: {source_path}")
            return False

        # Validate path
        if not PathSecurity.validate_path(source_path, self.skills_dir):
            logger.error(f"Invalid skill path: {source_path}")
            return False

        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                content = f.read()

            ext = source_path.suffix.lower()
            extensions = {
                '.md': self._parser.parse_skill_markdown,
                '.skill': self._parser.parse_skill_yaml,
                '.yaml': self._parser.parse_skill_yaml,
                '.yml': self._parser.parse_skill_yaml,
                '.json': self._parser.parse_skill_json
            }

            if ext not in extensions:
                return False

            skill = extensions[ext](content, source_path)
            if skill:
                self.loaded_skills[skill_id] = skill
                logger.info(f"Reloaded skill: {skill_id}")
                return True

        except Exception as e:
            logger.error(f"Error reloading skill {skill_id}: {e}")

        return False

    def add_skill(self, skill: Skill) -> bool:
        """Add a new skill to the adapter"""
        try:
            # Validate skill ID
            skill.id = PathSecurity.sanitize_filename(skill.id)

            # Add to loaded skills
            self.loaded_skills[skill.id] = skill

            logger.info(f"Added skill: {skill.name} ({skill.id})")
            return True

        except Exception as e:
            logger.error(f"Error adding skill: {e}")
            return False

    def remove_skill(self, skill_id: str) -> bool:
        """Remove a skill from the adapter"""
        if skill_id in self.loaded_skills:
            del self.loaded_skills[skill_id]

            if skill_id in self._loaded_sources:
                del self._loaded_sources[skill_id]

            logger.info(f"Removed skill: {skill_id}")
            return True

        return False

    def enable_skill(self, skill_id: str) -> bool:
        """Enable a skill"""
        skill = self.get_skill(skill_id)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable_skill(self, skill_id: str) -> bool:
        """Disable a skill"""
        skill = self.get_skill(skill_id)
        if skill:
            skill.enabled = False
            return True
        return False

    def get_enabled_skills(self) -> List[Skill]:
        """Get all enabled skills"""
        return [s for s in self.loaded_skills.values() if s.enabled]

    def export_skill(self, skill_id: str, output_path: str) -> bool:
        """Export a skill to a file"""
        skill = self.get_skill(skill_id)
        if not skill:
            return False

        try:
            output = Path(output_path)

            # Validate output path is within allowed base
            if not PathSecurity.validate_path(output, self.skills_dir.parent):
                logger.error(f"Output path outside allowed directory: {output}")
                return False

            # Convert skill to dict
            skill_dict = {
                'id': skill.id,
                'name': skill.name,
                'description': skill.description,
                'version': skill.version,
                'author': skill.author,
                'category': skill.category,
                'functions': [
                    {
                        'name': f.name,
                        'description': f.description,
                        'parameters': f.parameters,
                        'returns': f.returns,
                        'examples': f.examples
                    }
                    for f in skill.functions
                ],
                'config': skill.config
            }

            # Write based on extension
            if output.suffix.lower() == '.json':
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(skill_dict, f, indent=2, ensure_ascii=False)
            elif output.suffix.lower() in ['.yaml', '.yml', '.skill']:
                with open(output, 'w', encoding='utf-8') as f:
                    yaml.dump(skill_dict, f, allow_unicode=True, default_flow_style=False)
            else:
                # Default to markdown
                content = self._skill_to_markdown(skill)
                with open(output, 'w', encoding='utf-8') as f:
                    f.write(content)

            logger.info(f"Exported skill {skill_id} to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error exporting skill: {e}")
            return False

    def _skill_to_markdown(self, skill: Skill) -> str:
        """Convert skill to markdown format"""
        lines = [
            "---",
            f"name: {skill.name}",
            f"version: {skill.version}",
            f"author: {skill.author}",
            f"category: {skill.category}",
            "---",
            "",
            f"## {skill.name}",
            "",
            skill.description,
            "",
            "## Functions"
        ]

        for func in skill.functions:
            lines.extend([
                f"### {func.name}",
                "",
                func.description,
                ""
            ])

            if func.parameters:
                lines.append("#### Parameters")
                for param_name, param_info in func.parameters.items():
                    param_type = param_info.get('type', 'any')
                    lines.append(f"- {param_name}: {param_type}")
                lines.append("")

        return "\n".join(lines)

    def to_nanobot_format(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        Convert skill to Nanobot tool format.
        Returns tool definition for use in agent system.
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return None

        tools = []

        for func in skill.functions:
            # Build function definition with unique name
            tool_name = f"{skill_id}_{func.name}".replace('-', '_').replace(' ', '_')

            tool = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": func.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }

            # Add parameters
            for param_name, param_info in func.parameters.items():
                tool["function"]["parameters"]["properties"][param_name] = {
                    "type": param_info.get("type", "string"),
                    "description": param_info.get("description", "")
                }

                if param_info.get("required", False):
                    tool["function"]["parameters"]["required"].append(param_name)

            tools.append(tool)

        return {
            "skill_id": skill_id,
            "skill_name": skill.name,
            "tools": tools,
            "metadata": skill.metadata
        }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize adapter
    adapter = SkillAdapter("./skills")
    adapter.initialize()

    # List all skills
    print(f"Loaded {len(adapter.get_all_skills())} skills")

    for skill in adapter.get_all_skills():
        print(f"  - {skill.name} ({skill.category}): {len(skill.functions)} functions")

    # Get enabled skills
    enabled = adapter.get_enabled_skills()
    print(f"\nEnabled: {len(enabled)} skills")

    # Convert to nanobot format
    for skill in enabled[:1]:
        nanobot_tools = adapter.to_nanobot_format(skill.id)
        if nanobot_tools:
            print(f"\nTools for {skill.name}:")
            print(json.dumps(nanobot_tools, indent=2))
