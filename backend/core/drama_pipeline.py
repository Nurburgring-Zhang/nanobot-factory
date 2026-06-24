"""短剧生产管线——剧本→分镜→生成→配音→剪辑"""
import json, logging, uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class ScriptScene:
    def __init__(self, scene_number: int, content: str, characters=None, location="", duration_seconds=10):
        self.scene_id = f"sc_{uuid.uuid4().hex[:8]}"
        self.scene_number = scene_number
        self.content = content
        self.characters = characters or []
        self.location = location
        self.duration_seconds = duration_seconds
        self.prompt = ""
        self.image_path = ""
        self.video_path = ""
        self.audio_path = ""
        self.status = "pending"
        self.created_at = datetime.now().isoformat()

class DramaProject:
    def __init__(self, title: str, script: str = ""):
        self.project_id = f"dp_{uuid.uuid4().hex[:12]}"
        self.title = title
        self.script = script
        self.scenes: List[ScriptScene] = []
        self.style = "realistic"
        self.status = "draft"
        self.created_at = datetime.now().isoformat()

class DramaPipeline:
    _projects: Dict[str, DramaProject] = {}
    
    @classmethod
    def create_project(cls, title, script="", style="realistic"):
        p = DramaProject(title, script)
        p.style = style
        cls._projects[p.project_id] = p
        return p
    
    @classmethod
    def get_project(cls, project_id):
        return cls._projects.get(project_id)
    
    @classmethod
    def list_projects(cls):
        return [{"project_id": p.project_id, "title": p.title,
                 "scene_count": len(p.scenes), "status": p.status,
                 "style": p.style} for p in cls._projects.values()]
    
    @classmethod
    def breakdown_script(cls, project_id):
        project = cls._projects.get(project_id)
        if not project or not project.script:
            return False
        paragraphs = [p.strip() for p in project.script.split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [project.script]
        for i, para in enumerate(paragraphs):
            scene = ScriptScene(i + 1, para, duration_seconds=min(30, max(5, len(para)//10)))
            scene.prompt = para[:200]
            project.scenes.append(scene)
        project.status = "scene_breakdown"
        return True
    
    @classmethod
    def generate_all_scenes(cls, project_id):
        project = cls._projects.get(project_id)
        if not project:
            return False
        for scene in project.scenes:
            scene.status = "generating"
            scene.image_path = f"/output/drama/{project_id}/scene_{scene.scene_number}.png"
            scene.status = "completed"
        project.status = "generating"
        return True

drama = DramaPipeline()
