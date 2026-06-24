"""
ComfyUI Workflow Execution Engine
=================================
Manages ComfyUI workflow discovery, execution, and status polling.
Connects to local ComfyUI server at http://127.0.0.1:8188 (default).

Usage:
    engine = ComfyUIEngine()
    workflows = await engine.list_workflows()
    result = await engine.run_workflow(workflow_id, {"prompt": "cat"})
    status = await engine.get_status(result["prompt_id"])
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Default ComfyUI API address
DEFAULT_COMFYUI_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1")
DEFAULT_COMFYUI_PORT = int(os.environ.get("COMFYUI_PORT", "8188"))
DEFAULT_COMFYUI_URL = f"http://{DEFAULT_COMFYUI_HOST}:{DEFAULT_COMFYUI_PORT}"

# Default workflows directory (relative to project root)
DEFAULT_WORKFLOWS_DIR = os.environ.get(
    "COMFYUI_WORKFLOWS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")
)


class ComfyUIWorkflow:
    """Represents a single ComfyUI workflow definition"""
    def __init__(self, workflow_id: str, name: str, filepath: str,
                 description: str = "", category: str = "通用"):
        self.workflow_id = workflow_id
        self.name = name
        self.filepath = filepath
        self.description = description
        self.category = category

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "filepath": self.filepath,
            "description": self.description,
            "category": self.category,
        }


class ComfyUIEngine:
    """
    ComfyUI Workflow Execution Engine

    Features:
      - Scans workflows/ directory for .json workflow files
      - Submits workflows to ComfyUI API for execution
      - Polls execution status
      - Replaces prompt text in CLIPTextEncode nodes
    """

    def __init__(self, base_url: str = DEFAULT_COMFYUI_URL,
                 workflows_dir: str = DEFAULT_WORKFLOWS_DIR,
                 timeout: int = 600):
        self.base_url = base_url.rstrip("/")
        self.workflows_dir = Path(workflows_dir)
        self.timeout = timeout
        self._session = None

    async def _get_session(self):
        """Lazy-initialize httpx session"""
        if self._session is None:
            import httpx
            self._session = httpx.AsyncClient(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session:
            await self._session.aclose()
            self._session = None

    # ── Workflow Discovery ────────────────────────────────────────────────

    def list_workflows(self) -> List[ComfyUIWorkflow]:
        """
        Scan workflows/ directory for .json workflow files.

        Returns a list of ComfyUIWorkflow objects with metadata.
        """
        workflows: List[ComfyUIWorkflow] = []

        if not self.workflows_dir.exists():
            logger.warning(f"Workflows directory not found: {self.workflows_dir}")
            return workflows

        for filepath in sorted(self.workflows_dir.glob("*.json")):
            workflow_id = filepath.stem
            name = workflow_id.replace("_", " ").replace("-", " ").title()
            description = ""
            category = "通用"

            # Try to extract metadata from JSON content
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    description = data.get("_description", "")
                    category = data.get("_category", "通用")
            except (json.JSONDecodeError, OSError):
                pass

            workflows.append(ComfyUIWorkflow(
                workflow_id=workflow_id,
                name=name,
                filepath=str(filepath),
                description=description,
                category=category,
            ))

        logger.info(f"Discovered {len(workflows)} ComfyUI workflows in {self.workflows_dir}")
        return workflows

    def get_workflow(self, workflow_id: str) -> Optional[ComfyUIWorkflow]:
        """Get a single workflow by ID"""
        for wf in self.list_workflows():
            if wf.workflow_id == workflow_id:
                return wf
        return None

    # ── Workflow Execution ────────────────────────────────────────────────

    async def run_workflow(self, workflow_id: str,
                           params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a ComfyUI workflow.

        Args:
            workflow_id: Name of the workflow file (without .json)
            params: Parameters to inject into the workflow (e.g., {"prompt": "..."})

        Returns:
            Dict with prompt_id and status on success, or error info.
        """
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return {
                "ok": False,
                "error": f"Workflow '{workflow_id}' not found",
                "workflows_available": [w.workflow_id for w in self.list_workflows()],
            }

        # Load workflow JSON
        try:
            with open(workflow.filepath, "r", encoding="utf-8") as f:
                workflow_json = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return {"ok": False, "error": f"Failed to load workflow: {e}"}

        # Inject parameters into workflow nodes
        prompt_text = params.get("prompt", "")
        negative_prompt = params.get("negative_prompt", "")
        workflow_json = self._inject_params(workflow_json, {
            "prompt": prompt_text,
            "negative_prompt": negative_prompt,
            **params.get("overrides", {}),
        })

        # Submit to ComfyUI API
        session = await self._get_session()
        try:
            resp = await session.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow_json},
            )
            if resp.status_code >= 400:
                error_detail = resp.text[:500]
                logger.error(f"ComfyUI API error: HTTP {resp.status_code} - {error_detail}")
                return {"ok": False, "error": error_detail, "status_code": resp.status_code}

            data = resp.json()
            prompt_id = data.get("prompt_id", "")
            logger.info(f"ComfyUI workflow '{workflow_id}' submitted. prompt_id={prompt_id}")
            return {
                "ok": True,
                "prompt_id": prompt_id,
                "workflow_id": workflow_id,
                "status": "queued",
            }

        except Exception as e:
            logger.error(f"ComfyUI connection failed: {e}")
            return {"ok": False, "error": str(e)}

    # ── Status Polling ────────────────────────────────────────────────────

    async def get_status(self, prompt_id: str) -> Dict[str, Any]:
        """
        Query execution status of a submitted workflow.

        Returns:
            Dict with status, progress, and outputs (if completed).
        """
        session = await self._get_session()
        try:
            # ComfyUI has /history/{prompt_id} for completed runs
            resp = await session.get(
                f"{self.base_url}/history/{prompt_id}",
            )
            if resp.status_code == 200:
                history = resp.json()
                if prompt_id in history:
                    entry = history[prompt_id]
                    status = entry.get("status", {})
                    outputs = entry.get("outputs", {})

                    completed = status.get("completed", False)
                    if completed:
                        # Collect output images/files
                        results = self._extract_outputs(outputs)
                        return {
                            "ok": True,
                            "prompt_id": prompt_id,
                            "status": "completed",
                            "outputs": results,
                        }
                    else:
                        return {
                            "ok": True,
                            "prompt_id": prompt_id,
                            "status": "running",
                        }
                else:
                    # Not in history yet — check queue
                    return {
                        "ok": True,
                        "prompt_id": prompt_id,
                        "status": "queued",
                    }

            # Check /queue for running status
            queue_resp = await session.get(f"{self.base_url}/queue")
            if queue_resp.status_code == 200:
                queue_data = queue_resp.json()
                queue_running = queue_data.get("queue_running", [])
                queue_pending = queue_data.get("queue_pending", [])
                for item in queue_running:
                    if item.get("prompt_id") == prompt_id:
                        return {
                            "ok": True,
                            "prompt_id": prompt_id,
                            "status": "running",
                            "progress": item.get("progress", 0),
                        }
                for item in queue_pending:
                    if item.get("prompt_id") == prompt_id:
                        return {
                            "ok": True,
                            "prompt_id": prompt_id,
                            "status": "queued",
                        }

            return {
                "ok": True,
                "prompt_id": prompt_id,
                "status": "unknown",
            }

        except Exception as e:
            logger.error(f"Failed to query status for {prompt_id}: {e}")
            return {"ok": False, "error": str(e)}

    # ── Internal Helpers ──────────────────────────────────────────────────

    def _inject_params(self, workflow: Dict[str, Any],
                       params: Dict[str, Any]) -> Dict[str, Any]:
        """Inject prompt text into CLIPTextEncode nodes"""
        prompt_text = params.get("prompt", "")
        negative_prompt = params.get("negative_prompt", "")

        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type", "")).lower()
            inputs = node.get("inputs", {})

            if "cliptextencode" in class_type:
                # Check if it's a positive or negative prompt node
                current = str(inputs.get("text", "")).lower()
                if "negative" in current or not prompt_text:
                    if negative_prompt:
                        node["inputs"]["text"] = negative_prompt
                else:
                    if prompt_text:
                        node["inputs"]["text"] = prompt_text

            # Also handle CheckpointLoaderSimple model overrides
            if "checkpointloadersimple" in class_type:
                model_name = params.get("model", "")
                if model_name:
                    node["inputs"]["ckpt_name"] = model_name

        return workflow

    def _extract_outputs(self, outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract output image/file info from ComfyUI history outputs"""
        results = []
        for node_id, node_outputs in outputs.items():
            if isinstance(node_outputs, dict):
                for media_type, media_list in node_outputs.items():
                    if isinstance(media_list, list):
                        for item in media_list:
                            if isinstance(item, dict):
                                results.append({
                                    "node_id": node_id,
                                    "type": media_type,
                                    "filename": item.get("filename", ""),
                                    "subfolder": item.get("subfolder", ""),
                                    "type_label": item.get("type", ""),
                                })
        return results

    async def wait_for_completion(self, prompt_id: str,
                                  poll_interval: float = 1.0,
                                  max_wait: float = 600.0) -> Dict[str, Any]:
        """Poll until workflow completes or times out"""
        start = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > max_wait:
                return {"ok": False, "error": "timeout", "prompt_id": prompt_id}

            result = await self.get_status(prompt_id)
            if result.get("status") == "completed":
                return result
            if result.get("status") == "failed":
                return result

            await asyncio.sleep(poll_interval)
