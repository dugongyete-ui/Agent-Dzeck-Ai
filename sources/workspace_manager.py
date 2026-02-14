import os
import json
import uuid
import shutil
import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field, asdict
from sources.logger import Logger


@dataclass
class WorkspaceSession:
    session_id: str
    workspace_path: str
    created_at: str
    project_type: str = "general"
    project_name: str = ""
    files: List[str] = field(default_factory=list)
    ports: Dict[str, int] = field(default_factory=dict)
    status: str = "active"
    metadata: Dict = field(default_factory=dict)


class WorkspaceManager:
    def __init__(self, base_dir: str = "/home/runner/workspace/work"):
        self.base_dir = base_dir
        self.sessions: Dict[str, WorkspaceSession] = {}
        self.current_session: Optional[WorkspaceSession] = None
        self.logger = Logger("workspace_manager.log")
        self.sessions_file = os.path.join(base_dir, ".workspace_sessions.json")
        os.makedirs(base_dir, exist_ok=True)
        self._load_sessions()

    def _load_sessions(self):
        try:
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, 'r') as f:
                    data = json.load(f)
                    for sid, sdata in data.items():
                        self.sessions[sid] = WorkspaceSession(**sdata)
        except Exception as e:
            self.logger.error(f"Failed to load sessions: {e}")

    def _save_sessions(self):
        try:
            data = {sid: asdict(s) for sid, s in self.sessions.items()}
            with open(self.sessions_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save sessions: {e}")

    def create_workspace(self, project_name: str = "", project_type: str = "general") -> WorkspaceSession:
        session_id = str(uuid.uuid4())[:8]
        workspace_path = os.path.join(self.base_dir, f"project_{session_id}")
        os.makedirs(workspace_path, exist_ok=True)

        session = WorkspaceSession(
            session_id=session_id,
            workspace_path=workspace_path,
            created_at=datetime.datetime.now().isoformat(),
            project_type=project_type,
            project_name=project_name or f"project_{session_id}",
        )
        self.sessions[session_id] = session
        self.current_session = session
        self._save_sessions()
        self.logger.info(f"Created workspace: {workspace_path}")
        return session

    def get_or_create_workspace(self, project_name: str = "") -> WorkspaceSession:
        if self.current_session and self.current_session.status == "active":
            return self.current_session
        for sid, session in self.sessions.items():
            if session.status == "active":
                self.current_session = session
                return session
        return self.create_workspace(project_name=project_name)

    def get_workspace_path(self) -> str:
        if self.current_session:
            return self.current_session.workspace_path
        return self.base_dir

    def list_workspaces(self) -> List[Dict]:
        result = []
        for sid, session in self.sessions.items():
            files = self._scan_files(session.workspace_path)
            result.append({
                "session_id": sid,
                "project_name": session.project_name,
                "project_type": session.project_type,
                "workspace_path": session.workspace_path,
                "created_at": session.created_at,
                "status": session.status,
                "file_count": len(files),
                "files": files[:20],
            })
        return result

    def _scan_files(self, directory: str) -> List[str]:
        files = []
        skip_dirs = {'__pycache__', 'node_modules', '.git', '.cache', '.venv', 'venv'}
        if not os.path.isdir(directory):
            return files
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in filenames:
                rel_path = os.path.relpath(os.path.join(root, fname), directory)
                files.append(rel_path)
        return files

    def register_file(self, filepath: str):
        if self.current_session:
            rel = os.path.relpath(filepath, self.current_session.workspace_path)
            if rel not in self.current_session.files:
                self.current_session.files.append(rel)
                self._save_sessions()

    def get_project_structure(self, session_id: str = None) -> Dict:
        session = self.sessions.get(session_id) if session_id else self.current_session
        if not session:
            return {"error": "No active workspace"}
        
        files = self._scan_files(session.workspace_path)
        tree = {}
        for f in files:
            parts = f.split(os.sep)
            current = tree
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = None
        
        return {
            "session_id": session.session_id,
            "project_name": session.project_name,
            "project_type": session.project_type,
            "tree": tree,
            "total_files": len(files),
            "files": files,
        }

    def read_file(self, filepath: str, session_id: str = None) -> Optional[str]:
        session = self.sessions.get(session_id) if session_id else self.current_session
        if not session:
            return None
        full_path = os.path.join(session.workspace_path, filepath)
        if not full_path.startswith(session.workspace_path):
            return None
        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except Exception:
            return None

    def delete_workspace(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            return False
        try:
            if os.path.isdir(session.workspace_path):
                shutil.rmtree(session.workspace_path)
            session.status = "deleted"
            self._save_sessions()
            if self.current_session and self.current_session.session_id == session_id:
                self.current_session = None
            self.logger.info(f"Deleted workspace: {session.workspace_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete workspace: {e}")
            return False

    def detect_project_type(self, workspace_path: str) -> str:
        if os.path.exists(os.path.join(workspace_path, "package.json")):
            pkg = {}
            try:
                with open(os.path.join(workspace_path, "package.json"), 'r') as f:
                    pkg = json.load(f)
            except Exception:
                pass
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                return "nextjs"
            if "react" in deps:
                return "react"
            if "vue" in deps:
                return "vue"
            if "express" in deps:
                return "express"
            return "nodejs"
        if os.path.exists(os.path.join(workspace_path, "requirements.txt")):
            return "python"
        if os.path.exists(os.path.join(workspace_path, "go.mod")):
            return "golang"
        html_files = [f for f in os.listdir(workspace_path) if f.endswith('.html')]
        if html_files:
            return "static_html"
        return "general"

    def get_workspace_stats(self) -> Dict:
        total = len(self.sessions)
        active = sum(1 for s in self.sessions.values() if s.status == "active")
        return {
            "total_workspaces": total,
            "active_workspaces": active,
            "base_dir": self.base_dir,
            "current_session": self.current_session.session_id if self.current_session else None,
        }
