import asyncio
import json
import time
from typing import Dict, Set, Optional
from fastapi import WebSocket
from sources.logger import Logger


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.logger = Logger("realtime.log")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self.logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict):
        if not self.active_connections:
            return
        dead = set()
        msg_text = json.dumps(message, ensure_ascii=False)
        for ws in self.active_connections:
            try:
                await ws.send_text(msg_text)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active_connections.discard(ws)

    async def send_status(self, agent_name: str, status: str, progress: float = 0.0, details: str = ""):
        await self.broadcast({
            "type": "status",
            "agent_name": agent_name,
            "status": status,
            "progress": progress,
            "details": details,
            "timestamp": time.time(),
        })

    async def send_execution_update(self, language: str, code_snippet: str, result: str, success: bool):
        await self.broadcast({
            "type": "execution",
            "language": language,
            "code_snippet": code_snippet[:500],
            "result": result[:1000],
            "success": success,
            "timestamp": time.time(),
        })

    async def send_file_update(self, action: str, filepath: str, content: str = ""):
        await self.broadcast({
            "type": "file_update",
            "action": action,
            "filepath": filepath,
            "content": content[:2000] if content else "",
            "timestamp": time.time(),
        })

    async def send_plan_update(self, plan: list, current_step: int = 0):
        await self.broadcast({
            "type": "plan",
            "plan": plan,
            "current_step": current_step,
            "timestamp": time.time(),
        })

    async def send_preview_ready(self, preview_url: str, project_type: str):
        await self.broadcast({
            "type": "preview_ready",
            "preview_url": preview_url,
            "project_type": project_type,
            "timestamp": time.time(),
        })

    async def send_peor_update(self, phase: str, step_id: int = 0, details: str = ""):
        await self.broadcast({
            "type": "peor",
            "phase": phase,
            "step_id": step_id,
            "details": details,
            "timestamp": time.time(),
        })

    async def send_agent_switch(self, agent_name: str, agent_type: str):
        await self.broadcast({
            "type": "agent_switch",
            "agent_name": agent_name,
            "agent_type": agent_type,
            "timestamp": time.time(),
        })

    async def send_agent_thinking(self, agent_name: str, thinking_message: str):
        await self.broadcast({
            "type": "agent_thinking",
            "agent_name": agent_name,
            "thinking_message": thinking_message,
            "timestamp": time.time(),
        })

    async def send_execution_log(self, level: str, message: str, agent_name: str = ""):
        await self.broadcast({
            "type": "execution_log",
            "level": level,
            "message": message,
            "agent_name": agent_name,
            "timestamp": time.time(),
        })

    async def send_plan_progress(self, total_steps: int, completed_steps: int, failed_steps: int,
                                  current_step_id: int = 0, current_step_description: str = "",
                                  elapsed_time: float = 0.0, estimated_remaining: float = 0.0,
                                  success_rate: float = 0.0):
        await self.broadcast({
            "type": "plan_progress",
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "current_step_id": current_step_id,
            "current_step_description": current_step_description,
            "elapsed_time": elapsed_time,
            "estimated_remaining": estimated_remaining,
            "success_rate": success_rate,
            "timestamp": time.time(),
        })


ws_manager = ConnectionManager()
