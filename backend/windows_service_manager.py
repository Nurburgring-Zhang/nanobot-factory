#!/usr/bin/env python3
"""
Nanobot Factory - Windows Service Management
Windows NSSM (Non-Sucking Service Manager) integration

@author MiniMax Agent
@date 2026-02-26
"""

import os
import sys
import json
import logging
import subprocess
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Windows Service Status"""
    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


@dataclass
class ServiceInfo:
    """Windows Service Information"""
    name: str
    display_name: str
    description: str
    status: ServiceStatus
    executable_path: str
    arguments: List[str]
    working_directory: str
    auto_start: bool
    dependencies: List[str]


class WindowsServiceManager:
    """
    Windows Service Manager using NSSM
    Manages Windows services for Nanobot Factory agents
    """

    def __init__(self, nssm_path: str = "nssm.exe"):
        self.nssm_path = nssm_path
        self._service_cache: Dict[str, ServiceInfo] = {}
        self._lock = threading.Lock()

    def _run_nssm_command(self, command: List[str]) -> tuple:
        """
        Run NSSM command

        Args:
            command: Command arguments (without nssm.exe)

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                [self.nssm_path] + command,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error("NSSM command timeout")
            return -1, "", "Command timeout"
        except FileNotFoundError:
            logger.error(f"NSSM not found at {self.nssm_path}")
            return -1, "", f"NSSM not found at {self.nssm_path}"
        except Exception as e:
            logger.error(f"NSSM command failed: {e}")
            return -1, "", str(e)

    def service_exists(self, service_name: str) -> bool:
        """Check if a service exists"""
        code, stdout, stderr = self._run_nssm_command(["status", service_name])
        return code == 0

    def create_service(
        self,
        service_name: str,
        executable_path: str,
        display_name: str = "",
        arguments: Optional[List[str]] = None,
        working_directory: str = "",
        description: str = "",
        auto_start: bool = True,
        startup_type: str = "auto",
        dependencies: Optional[List[str]] = None
    ) -> bool:
        """
        Create a new Windows service using NSSM

        Args:
            service_name: Service name
            executable_path: Path to executable
            display_name: Display name
            arguments: Command line arguments
            working_directory: Working directory
            description: Service description
            auto_start: Auto-start with Windows
            startup_type: "auto", "manual", or "disabled"
            dependencies: Service dependencies

        Returns:
            True if successful
        """
        if self.service_exists(service_name):
            logger.warning(f"Service {service_name} already exists")
            return False

        # Create service
        cmd = ["install", service_name, executable_path]
        code, stdout, stderr = self._run_nssm_command(cmd)

        if code != 0:
            logger.error(f"Failed to create service: {stderr}")
            return False

        # Set additional parameters
        if arguments:
            args_str = " ".join(arguments)
            self._run_nssm_command(["set", service_name, "AppParameters", args_str])

        if working_directory:
            self._run_nssm_command(["set", service_name, "AppDirectory", working_directory])

        if display_name:
            self._run_nssm_command(["set", service_name, "DisplayName", display_name])

        if description:
            self._run_nssm_command(["set", service_name, "Description", description])

        # Set startup type
        if startup_type == "auto":
            self._run_nssm_command(["set", service_name, "Start", "SERVICE_AUTO_START"])
        elif startup_type == "manual":
            self._run_nssm_command(["set", service_name, "Start", "SERVICE_DEMAND_START"])
        elif startup_type == "disabled":
            self._run_nssm_command(["set", service_name, "Start", "SERVICE_DISABLED"])

        # Set dependencies
        if dependencies:
            deps_str = "/".join(dependencies)
            self._run_nssm_command(["set", service_name, "DependOn", deps_str])

        logger.info(f"Service {service_name} created successfully")
        return True

    def delete_service(self, service_name: str) -> bool:
        """
        Delete a Windows service

        Args:
            service_name: Service name

        Returns:
            True if successful
        """
        if not self.service_exists(service_name):
            logger.warning(f"Service {service_name} does not exist")
            return False

        # Stop service first
        self.stop_service(service_name)

        # Delete service
        code, stdout, stderr = self._run_nssm_command(["remove", service_name, "confirm"])

        if code != 0:
            logger.error(f"Failed to delete service: {stderr}")
            return False

        logger.info(f"Service {service_name} deleted successfully")
        return True

    def start_service(self, service_name: str) -> bool:
        """
        Start a Windows service

        Args:
            service_name: Service name

        Returns:
            True if successful
        """
        code, stdout, stderr = self._run_nssm_command(["start", service_name])

        if code != 0:
            logger.error(f"Failed to start service: {stderr}")
            return False

        logger.info(f"Service {service_name} started successfully")
        return True

    def stop_service(self, service_name: str) -> bool:
        """
        Stop a Windows service

        Args:
            service_name: Service name

        Returns:
            True if successful
        """
        code, stdout, stderr = self._run_nssm_command(["stop", service_name])

        if code != 0:
            logger.error(f"Failed to stop service: {stderr}")
            return False

        logger.info(f"Service {service_name} stopped successfully")
        return True

    def restart_service(self, service_name: str) -> bool:
        """
        Restart a Windows service

        Args:
            service_name: Service name

        Returns:
            True if successful
        """
        if not self.stop_service(service_name):
            return False

        # Wait for service to stop
        import time
        time.sleep(2)

        return self.start_service(service_name)

    def get_service_status(self, service_name: str) -> ServiceStatus:
        """
        Get service status

        Args:
            service_name: Service name

        Returns:
            ServiceStatus enum
        """
        code, stdout, stderr = self._run_nssm_command(["status", service_name])

        if code != 0:
            return ServiceStatus.UNKNOWN

        stdout_lower = stdout.lower()

        if "running" in stdout_lower:
            return ServiceStatus.RUNNING
        elif "stopped" in stdout_lower:
            return ServiceStatus.STOPPED
        elif "start" in stdout_lower:
            return ServiceStatus.STARTING
        elif "stop" in stdout_lower:
            return ServiceStatus.STOPPING

        return ServiceStatus.UNKNOWN

    def get_service_info(self, service_name: str) -> Optional[ServiceInfo]:
        """
        Get detailed service information

        Args:
            service_name: Service name

        Returns:
            ServiceInfo object or None
        """
        # Get service status
        status = self.get_service_status(service_name)

        # Get service parameters
        code, stdout, stderr = self._run_nssm_command(["get", service_name, "AppDirectory"])
        working_directory = stdout.strip() if code == 0 else ""

        code, stdout, stderr = self._run_nssm_command(["get", service_name, "AppParameters"])
        arguments = stdout.strip().split() if code == 0 else []

        code, stdout, stderr = self._run_nssm_command(["get", service_name, "DisplayName"])
        display_name = stdout.strip() if code == 0 else service_name

        code, stdout, stderr = self._run_nssm_command(["get", service_name, "Description"])
        description = stdout.strip() if code == 0 else ""

        code, stdout, stderr = self._run_nssm_command(["get", service_name, "DependOn"])
        dependencies = stdout.strip().split("/") if code == 0 else []

        code, stdout, stderr = self._run_nssm_command(["get", service_name, "Start"])
        auto_start = stdout.strip().lower() == "auto"

        return ServiceInfo(
            name=service_name,
            display_name=display_name,
            description=description,
            status=status,
            executable_path="",  # Would need additional query
            arguments=arguments,
            working_directory=working_directory,
            auto_start=auto_start,
            dependencies=dependencies
        )

    def list_services(self, pattern: Optional[str] = None) -> List[str]:
        """
        List all NSSM-managed services

        Args:
            pattern: Optional pattern to filter services

        Returns:
            List of service names
        """
        # Use Windows sc query to list services
        try:
            result = subprocess.run(
                ["sc", "query", "type=", "service", "state=", "all"],
                capture_output=True,
                text=True,
                timeout=30
            )

            services = []
            for line in result.stdout.split("\n"):
                if "SERVICE_NAME:" in line:
                    service_name = line.split("SERVICE_NAME:")[1].strip()
                    if pattern is None or pattern.lower() in service_name.lower():
                        services.append(service_name)

            return services

        except Exception as e:
            logger.error(f"Failed to list services: {e}")
            return []

    def set_service_restart(
        self,
        service_name: str,
        restart_delay: int = 60000,
        restart_count: int = 3,
        restart_interval: int = 60000
    ) -> bool:
        """
        Configure automatic service restart

        Args:
            service_name: Service name
            restart_delay: Delay before first restart (ms)
            restart_count: Number of restart attempts
            restart_interval: Interval between restarts (ms)

        Returns:
            True if successful
        """
        self._run_nssm_command(["set", service_name, "AppRestartDelay", str(restart_delay)])
        self._run_nssm_command(["set", service_name, "AppRestartCount", str(restart_count)])
        self._run_nssm_command(["set", service_name, "AppRestartInterval", str(restart_interval)])

        logger.info(f"Service {service_name} restart configured")
        return True

    def set_service_output(
        self,
        service_name: str,
        stdout_path: str,
        stderr_path: str = "",
        rotate: bool = True,
        rotate_bytes: int = 10485760,
        rotate_online: int = 1
    ) -> bool:
        """
        Configure service output redirection

        Args:
            service_name: Service name
            stdout_path: Path to stdout log
            stderr_path: Path to stderr log (if different)
            rotate: Enable log rotation
            rotate_bytes: Rotate at this size (bytes)
            rotate_online: Rotate online (1) or on restart (0)

        Returns:
            True if successful
        """
        self._run_nssm_command(["set", service_name, "AppStdout", stdout_path])

        if stderr_path:
            self._run_nssm_command(["set", service_name, "AppStderr", stderr_path])

        if rotate:
            self._run_nssm_command(["set", service_name, "AppRotate", "1"])
            self._run_nssm_command(["set", service_name, "AppRotateBytes", str(rotate_bytes)])
            self._run_nssm_command(["set", service_name, "AppRotateOnline", str(rotate_online)])

        logger.info(f"Service {service_name} output configured")
        return True


# =============================================================================
# Nanobot Factory Service Manager
# =============================================================================

class NanobotServiceManager(WindowsServiceManager):
    """
    Specialized service manager for Nanobot Factory agents
    Manages the 6 agent roles as Windows services
    """

    AGENT_SERVICES = {
        "orchestrator": {
            "display_name": "Nanobot Orchestrator Agent",
            "description": "Main orchestration agent for task coordination",
            "executable": "python",
            "script": "backend/server.py"
        },
        "coder": {
            "display_name": "Nanobot Coder Agent",
            "description": "Code generation and review agent",
            "executable": "python",
            "script": "backend/production_agents.py"
        },
        "designer": {
            "display_name": "Nanobot Designer Agent",
            "description": "UI/UX design agent",
            "executable": "python",
            "script": "backend/skills.py"
        },
        "qa": {
            "display_name": "Nanobot QA Agent",
            "description": "Quality assurance and testing agent",
            "executable": "python",
            "script": "backend/cluster_scheduler.py"
        },
        "deployer": {
            "display_name": "Nanobot Deployer Agent",
            "description": "Deployment and CI/CD agent",
            "executable": "python",
            "script": "backend/deploy.py"
        },
        "monitor": {
            "display_name": "Nanobot Monitor Agent",
            "description": "System monitoring and health check agent",
            "executable": "python",
            "script": "backend/monitor.py"
        }
    }

    def __init__(self, base_dir: str = ""):
        super().__init__()
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def install_all_agents(self) -> Dict[str, bool]:
        """
        Install all Nanobot agent services

        Returns:
            Dict of service_name -> success
        """
        results = {}

        for agent_name, config in self.AGENT_SERVICES.items():
            service_name = f"nanobot_{agent_name}"
            executable_path = config["executable"]
            script_path = os.path.join(self.base_dir, config["script"])

            success = self.create_service(
                service_name=service_name,
                executable_path=executable_path,
                display_name=config["display_name"],
                arguments=[script_path],
                working_directory=self.base_dir,
                description=config["description"],
                auto_start=True
            )

            results[agent_name] = success

        return results

    def start_all_agents(self) -> Dict[str, bool]:
        """Start all Nanobot agents"""
        results = {}

        for agent_name in self.AGENT_SERVICES.keys():
            service_name = f"nanobot_{agent_name}"
            results[agent_name] = self.start_service(service_name)

        return results

    def stop_all_agents(self) -> Dict[str, bool]:
        """Stop all Nanobot agents"""
        results = {}

        for agent_name in self.AGENT_SERVICES.keys():
            service_name = f"nanobot_{agent_name}"
            results[agent_name] = self.stop_service(service_name)

        return results

    def get_all_agents_status(self) -> Dict[str, ServiceStatus]:
        """Get status of all Nanobot agents"""
        results = {}

        for agent_name in self.AGENT_SERVICES.keys():
            service_name = f"nanobot_{agent_name}"
            results[agent_name] = self.get_service_status(service_name)

        return results


# Global service manager
service_manager = NanobotServiceManager()


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: List all services
    print("=== Nanobot Factory Service Manager ===")

    # List services
    services = service_manager.list_services("nanobot")
    print(f"\nFound {len(services)} Nanobot services:")
    for svc in services:
        print(f"  - {svc}")

    # Check status
    print("\nAgent Status:")
    status = service_manager.get_all_agents_status()
    for agent, st in status.items():
        print(f"  {agent}: {st.value}")
