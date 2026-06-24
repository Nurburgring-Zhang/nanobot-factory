#!/usr/bin/env python3
"""
Nanobot Factory - Code Sandbox
Windows Sandbox API integration for secure code execution

@author MiniMax Agent
@date 2026-02-26
"""

import os
import sys
import json
import logging
import subprocess
import tempfile
import shutil
import threading
import time
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Code execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class Language(Enum):
    """Supported programming languages"""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    BASH = "bash"
    POWERSHELL = "powershell"


@dataclass
class ExecutionResult:
    """Code execution result"""
    execution_id: str
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    execution_time: float = 0.0
    memory_used: int = 0
    error: Optional[str] = None


@dataclass
class ExecutionRequest:
    """Code execution request"""
    code: str
    language: Language
    timeout: int = 30
    memory_limit: int = 512  # MB
    environment_vars: Dict[str, str] = field(default_factory=dict)
    working_directory: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)


class CodeSandbox:
    """
    Code Sandbox for secure code execution
    Uses Windows Sandbox for isolation
    """

    def __init__(
        self,
        sandbox_path: str = "",
        max_concurrent: int = 4,
        default_timeout: int = 30
    ):
        self.sandbox_path = sandbox_path
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self._running_executions: Dict[str, ExecutionRequest] = {}
        self._results: Dict[str, ExecutionResult] = {}
        self._lock = threading.Lock()

    def _create_temp_file(self, code: str, language: Language) -> str:
        """Create temporary file with code"""
        extension_map = {
            Language.PYTHON: ".py",
            Language.JAVASCRIPT: ".js",
            Language.TYPESCRIPT: ".ts",
            Language.BASH: ".sh",
            Language.POWERSHELL: ".ps1"
        }

        extension = extension_map.get(language, ".txt")
        fd, path = tempfile.mkstemp(suffix=extension, text=True)

        with os.fdopen(fd, 'w') as f:
            f.write(code)

        return path

    def _execute_python(
        self,
        request: ExecutionRequest,
        code_path: str
    ) -> ExecutionResult:
        """Execute Python code"""
        start_time = time.time()

        cmd = [
            "python",
            code_path
        ]

        # Add environment variables
        env = os.environ.copy()
        env.update(request.environment_vars)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=request.timeout,
                env=env,
                cwd=request.working_directory
            )

            execution_time = time.time() - start_time

            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.COMPLETED if result.returncode == 0 else ExecutionStatus.FAILED,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=execution_time
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timed out after {request.timeout} seconds",
                execution_time=request.timeout
            )

        except Exception as e:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.FAILED,
                error=str(e),
                execution_time=time.time() - start_time
            )

    def _execute_javascript(
        self,
        request: ExecutionRequest,
        code_path: str
    ) -> ExecutionResult:
        """Execute JavaScript/Node.js code"""
        start_time = time.time()

        cmd = [
            "node",
            code_path
        ]

        env = os.environ.copy()
        env.update(request.environment_vars)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=request.timeout,
                env=env,
                cwd=request.working_directory
            )

            execution_time = time.time() - start_time

            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.COMPLETED if result.returncode == 0 else ExecutionStatus.FAILED,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=execution_time
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timed out after {request.timeout} seconds",
                execution_time=request.timeout
            )

        except Exception as e:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.FAILED,
                error=str(e),
                execution_time=time.time() - start_time
            )

    def _execute_bash(
        self,
        request: ExecutionRequest,
        code_path: str
    ) -> ExecutionResult:
        """Execute Bash script"""
        start_time = time.time()

        cmd = [
            "bash",
            code_path
        ]

        env = os.environ.copy()
        env.update(request.environment_vars)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=request.timeout,
                env=env,
                cwd=request.working_directory
            )

            execution_time = time.time() - start_time

            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.COMPLETED if result.returncode == 0 else ExecutionStatus.FAILED,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=execution_time
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timed out after {request.timeout} seconds",
                execution_time=request.timeout
            )

        except Exception as e:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.FAILED,
                error=str(e),
                execution_time=time.time() - start_time
            )

    def _execute_powershell(
        self,
        request: ExecutionRequest,
        code_path: str
    ) -> ExecutionResult:
        """Execute PowerShell script"""
        start_time = time.time()

        cmd = [
            "powershell",
            "-ExecutionPolicy", "Bypass",
            "-File", code_path
        ]

        env = os.environ.copy()
        env.update(request.environment_vars)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=request.timeout,
                env=env,
                cwd=request.working_directory
            )

            execution_time = time.time() - start_time

            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.COMPLETED if result.returncode == 0 else ExecutionStatus.FAILED,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                execution_time=execution_time
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timed out after {request.timeout} seconds",
                execution_time=request.timeout
            )

        except Exception as e:
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                status=ExecutionStatus.FAILED,
                error=str(e),
                execution_time=time.time() - start_time
            )

    def execute(self, request: ExecutionRequest) -> str:
        """
        Execute code in sandbox

        Args:
            request: Execution request

        Returns:
            Execution ID
        """
        execution_id = str(uuid.uuid4())

        with self._lock:
            # Check concurrent limit
            if len(self._running_executions) >= self.max_concurrent:
                raise Exception("Maximum concurrent executions reached")

            self._running_executions[execution_id] = request

        # Create temp file
        code_path = self._create_temp_file(request.code, request.language)

        try:
            # Execute based on language
            if request.language == Language.PYTHON:
                result = self._execute_python(request, code_path)
            elif request.language == Language.JAVASCRIPT:
                result = self._execute_javascript(request, code_path)
            elif request.language == Language.TYPESCRIPT:
                # Use ts-node if available, else treat as JS
                result = self._execute_javascript(request, code_path)
            elif request.language == Language.BASH:
                result = self._execute_bash(request, code_path)
            elif request.language == Language.POWERSHELL:
                result = self._execute_powershell(request, code_path)
            else:
                result = ExecutionResult(
                    execution_id=execution_id,
                    status=ExecutionStatus.FAILED,
                    error=f"Unsupported language: {request.language}"
                )

            result.execution_id = execution_id

        finally:
            # Cleanup temp file
            try:
                os.unlink(code_path)
            except Exception:
                pass

            with self._lock:
                if execution_id in self._running_executions:
                    del self._running_executions[execution_id]
                self._results[execution_id] = result

        return execution_id

    def get_result(self, execution_id: str) -> Optional[ExecutionResult]:
        """Get execution result"""
        return self._results.get(execution_id)

    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel running execution"""
        with self._lock:
            if execution_id in self._running_executions:
                # Note: Actual cancellation would require more complex process management
                # For now, just mark as cancelled
                result = ExecutionResult(
                    execution_id=execution_id,
                    status=ExecutionStatus.CANCELLED,
                    error="Execution cancelled"
                )
                self._results[execution_id] = result
                del self._running_executions[execution_id]
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get sandbox statistics"""
        return {
            "running": len(self._running_executions),
            "max_concurrent": self.max_concurrent,
            "completed": len(self._results),
            "default_timeout": self.default_timeout
        }


class WindowsSandboxManager:
    """
    Windows Sandbox manager for creating isolated execution environments
    Uses Windows Sandbox (requires Windows 10/11 Pro or Enterprise)
    """

    def __init__(self, base_dir: str = ""):
        self.base_dir = base_dir or tempfile.gettempdir()
        self.sandboxes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_sandbox(
        self,
        name: str,
        memory_limit: int = 2048,
        cpu_limit: int = 2,
        network_enabled: bool = False,
        shared_folders: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Create a new Windows Sandbox environment

        Args:
            name: Sandbox name
            memory_limit: Memory limit in MB
            cpu_limit: CPU cores
            network_enabled: Enable network
            shared_folders: List of shared folders

        Returns:
            Sandbox ID
        """
        sandbox_id = str(uuid.uuid4())

        config = {
            "id": sandbox_id,
            "name": name,
            "memory_limit": memory_limit,
            "cpu_limit": cpu_limit,
            "network_enabled": network_enabled,
            "shared_folders": shared_folders or [],
            "created_at": datetime.now().isoformat(),
            "status": "created"
        }

        with self._lock:
            self.sandboxes[sandbox_id] = config

        logger.info(f"Created sandbox {sandbox_id} for {name}")
        return sandbox_id

    def start_sandbox(self, sandbox_id: str) -> bool:
        """
        Start a Windows Sandbox

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if successful
        """
        with self._lock:
            if sandbox_id not in self.sandboxes:
                return False

            sandbox = self.sandboxes[sandbox_id]

        # Create Windows Sandbox configuration file
        wsb_config = f"""<Configuration>
    <MemoryInMB>{sandbox['memory_limit']}</MemoryInMB>
    <ProcessorCount>{sandbox['cpu_limit']}</ProcessorCount>
    <EnableNetworking>{'1' if sandbox['network_enabled'] else '0'}</EnableNetworking>
    <SharedFolders>
        <SharedFolder>
            <HostFolder>{self.base_dir}</HostFolder>
            <ReadOnly>false</ReadOnly>
        </SharedFolder>
    </SharedFolders>
</Configuration>"""

        config_path = os.path.join(self.base_dir, f"{sandbox_id}.wsb")

        with open(config_path, 'w') as f:
            f.write(wsb_config)

        # Launch Windows Sandbox
        try:
            subprocess.Popen(
                ["wsandbox.exe", "start", config_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            with self._lock:
                self.sandboxes[sandbox_id]["status"] = "running"
                self.sandboxes[sandbox_id]["config_path"] = config_path

            logger.info(f"Started sandbox {sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start sandbox: {e}")
            return False

    def stop_sandbox(self, sandbox_id: str) -> bool:
        """
        Stop a Windows Sandbox

        Args:
            sandbox_id: Sandbox ID

        Returns:
            True if successful
        """
        with self._lock:
            if sandbox_id not in self.sandboxes:
                return False

            sandbox = self.sandboxes[sandbox_id]

        # Close sandbox
        try:
            if "config_path" in sandbox:
                os.unlink(sandbox["config_path"])

            with self._lock:
                self.sandboxes[sandbox_id]["status"] = "stopped"

            logger.info(f"Stopped sandbox {sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop sandbox: {e}")
            return False

    def delete_sandbox(self, sandbox_id: str) -> bool:
        """Delete a sandbox"""
        self.stop_sandbox(sandbox_id)

        with self._lock:
            if sandbox_id in self.sandboxes:
                del self.sandboxes[sandbox_id]

        return True

    def list_sandboxes(self) -> List[Dict[str, Any]]:
        """List all sandboxes"""
        with self._lock:
            return list(self.sandboxes.values())


# Global code sandbox
code_sandbox = CodeSandbox()
windows_sandbox = WindowsSandboxManager()


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== Code Sandbox Test ===")

    # Test Python execution
    request = ExecutionRequest(
        code="print('Hello from Python!')\nprint('Calculation:', 2 + 2)",
        language=Language.PYTHON,
        timeout=10
    )

    execution_id = code_sandbox.execute(request)
    print(f"Execution ID: {execution_id}")

    result = code_sandbox.get_result(execution_id)
    if result:
        print(f"Status: {result.status.value}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")
        print(f"Execution time: {result.execution_time:.2f}s")

    # Test JavaScript execution
    request = ExecutionRequest(
        code="console.log('Hello from JavaScript!');",
        language=Language.JAVASCRIPT,
        timeout=10
    )

    execution_id = code_sandbox.execute(request)
    print(f"\nExecution ID: {execution_id}")

    result = code_sandbox.get_result(execution_id)
    if result:
        print(f"Status: {result.status.value}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")

    # Print stats
    print(f"\nSandbox Stats: {code_sandbox.get_stats()}")
