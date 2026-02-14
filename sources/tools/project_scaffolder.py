import os
import json
import subprocess
from typing import Optional, Dict, List
from sources.logger import Logger


PROJECT_TEMPLATES = {
    "python_flask": {
        "name": "Flask Web App",
        "structure": {
            "app.py": (
                "from flask import Flask, render_template, jsonify, request\n"
                "\n"
                "app = Flask(__name__)\n"
                "\n"
                "@app.route('/')\n"
                "def index():\n"
                "    return render_template('index.html')\n"
                "\n"
                "@app.route('/api/status')\n"
                "def status():\n"
                "    return jsonify({'status': 'ok'})\n"
            ),
            "templates/index.html": (
                "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                "    <meta charset=\"UTF-8\">\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                "    <title>Flask App</title>\n"
                "    <link rel=\"stylesheet\" href=\"/static/style.css\">\n"
                "</head>\n<body>\n"
                "    <div id=\"app\"><h1>Flask App</h1></div>\n"
                "    <script src=\"/static/script.js\"></script>\n"
                "</body>\n</html>"
            ),
            "static/style.css": "* { margin: 0; padding: 0; box-sizing: border-box; }\nbody { font-family: sans-serif; }\n",
            "static/script.js": "document.addEventListener('DOMContentLoaded', () => { console.log('App loaded'); });\n",
            "requirements.txt": "flask\n",
        },
        "dependencies": ["flask"],
        "type": "python",
    },
    "python_fastapi": {
        "name": "FastAPI Backend",
        "structure": {
            "main.py": (
                "from fastapi import FastAPI\n"
                "from fastapi.middleware.cors import CORSMiddleware\n"
                "\n"
                "app = FastAPI()\n"
                "app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])\n"
                "\n"
                "@app.get('/')\n"
                "async def root():\n"
                "    return {'message': 'Hello World'}\n"
                "\n"
                "@app.get('/api/status')\n"
                "async def status():\n"
                "    return {'status': 'ok'}\n"
            ),
            "requirements.txt": "fastapi\nuvicorn\n",
        },
        "dependencies": ["fastapi", "uvicorn"],
        "type": "python",
    },
    "html_static": {
        "name": "Static HTML Website",
        "structure": {
            "index.html": (
                "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                "    <meta charset=\"UTF-8\">\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                "    <title>Website</title>\n"
                "    <link rel=\"stylesheet\" href=\"style.css\">\n"
                "</head>\n<body>\n"
                "    <header><h1>Welcome</h1></header>\n"
                "    <main><p>Content here</p></main>\n"
                "    <script src=\"script.js\"></script>\n"
                "</body>\n</html>"
            ),
            "style.css": "* { margin: 0; padding: 0; box-sizing: border-box; }\nbody { font-family: sans-serif; }\n",
            "script.js": "document.addEventListener('DOMContentLoaded', () => { console.log('Loaded'); });\n",
        },
        "dependencies": [],
        "type": "static",
    },
    "python_script": {
        "name": "Python Script",
        "structure": {
            "main.py": "#!/usr/bin/env python3\n\ndef main():\n    pass\n\nif __name__ == '__main__':\n    main()\n",
        },
        "dependencies": [],
        "type": "python",
    },
    "node_express": {
        "name": "Node.js Express API",
        "structure": {
            "package.json": json.dumps({
                "name": "express-app",
                "version": "1.0.0",
                "main": "server.js",
                "scripts": {"start": "node server.js", "dev": "node server.js"},
                "dependencies": {"express": "^4.18.0", "cors": "^2.8.5"}
            }, indent=2),
            "server.js": (
                "const express = require('express');\n"
                "const cors = require('cors');\n"
                "const path = require('path');\n"
                "\n"
                "const app = express();\n"
                "app.use(cors());\n"
                "app.use(express.json());\n"
                "app.use(express.static('public'));\n"
                "\n"
                "app.get('/api/status', (req, res) => {\n"
                "    res.json({ status: 'ok' });\n"
                "});\n"
                "\n"
                "const PORT = process.env.PORT || 3000;\n"
                "app.listen(PORT, () => console.log(`Server running on port ${PORT}`));\n"
            ),
            "public/index.html": (
                "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                "    <meta charset=\"UTF-8\">\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                "    <title>Express App</title>\n"
                "</head>\n<body>\n"
                "    <h1>Express App</h1>\n"
                "</body>\n</html>"
            ),
        },
        "dependencies": [],
        "type": "node",
        "post_init": "npm install",
    },
    "fullstack_python": {
        "name": "Full-Stack Python (Flask + HTML/CSS/JS)",
        "structure": {
            "app.py": (
                "from flask import Flask, render_template, jsonify, request, send_from_directory\n"
                "import sqlite3\n"
                "import os\n"
                "\n"
                "app = Flask(__name__, static_folder='static', template_folder='templates')\n"
                "DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')\n"
                "\n"
                "def get_db():\n"
                "    conn = sqlite3.connect(DB_PATH)\n"
                "    conn.row_factory = sqlite3.Row\n"
                "    return conn\n"
                "\n"
                "def init_db():\n"
                "    conn = get_db()\n"
                "    conn.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')\n"
                "    conn.commit()\n"
                "    conn.close()\n"
                "\n"
                "init_db()\n"
                "\n"
                "@app.route('/')\n"
                "def index():\n"
                "    return render_template('index.html')\n"
                "\n"
                "@app.route('/api/items', methods=['GET'])\n"
                "def get_items():\n"
                "    conn = get_db()\n"
                "    items = [dict(row) for row in conn.execute('SELECT * FROM items ORDER BY id DESC').fetchall()]\n"
                "    conn.close()\n"
                "    return jsonify(items)\n"
                "\n"
                "@app.route('/api/items', methods=['POST'])\n"
                "def add_item():\n"
                "    data = request.get_json()\n"
                "    conn = get_db()\n"
                "    conn.execute('INSERT INTO items (name) VALUES (?)', (data.get('name', ''),))\n"
                "    conn.commit()\n"
                "    conn.close()\n"
                "    return jsonify({'status': 'ok'})\n"
            ),
            "templates/index.html": (
                "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                "    <meta charset=\"UTF-8\">\n"
                "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
                "    <title>Full-Stack App</title>\n"
                "    <link rel=\"stylesheet\" href=\"/static/style.css\">\n"
                "</head>\n<body>\n"
                "    <div id=\"app\">\n"
                "        <h1>Full-Stack App</h1>\n"
                "        <div id=\"content\"></div>\n"
                "    </div>\n"
                "    <script src=\"/static/script.js\"></script>\n"
                "</body>\n</html>"
            ),
            "static/style.css": (
                "* { margin: 0; padding: 0; box-sizing: border-box; }\n"
                "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; }\n"
                "#app { max-width: 800px; margin: 0 auto; padding: 2rem; }\n"
                "h1 { margin-bottom: 1rem; }\n"
            ),
            "static/script.js": (
                "async function loadItems() {\n"
                "    const res = await fetch('/api/items');\n"
                "    const items = await res.json();\n"
                "    const el = document.getElementById('content');\n"
                "    el.innerHTML = items.map(i => `<div class='item'>${i.name}</div>`).join('');\n"
                "}\n"
                "document.addEventListener('DOMContentLoaded', loadItems);\n"
            ),
            "requirements.txt": "flask\n",
        },
        "dependencies": ["flask"],
        "type": "python",
    },
}


class ProjectScaffolder:
    def __init__(self, base_dir: str = "/home/runner/workspace/work"):
        self.base_dir = base_dir
        self.logger = Logger("scaffolder.log")
        os.makedirs(base_dir, exist_ok=True)

    def detect_project_type(self, description: str) -> str:
        desc = description.lower()
        if any(kw in desc for kw in ['fullstack', 'full-stack', 'full stack', 'database', 'crud', 'api + frontend']):
            return "fullstack_python"
        if any(kw in desc for kw in ['flask', 'python web', 'python website']):
            return "python_flask"
        if any(kw in desc for kw in ['fastapi', 'rest api', 'backend api']):
            return "python_fastapi"
        if any(kw in desc for kw in ['express', 'node.js', 'nodejs', 'node web']):
            return "node_express"
        if any(kw in desc for kw in ['html', 'website', 'landing', 'portfolio', 'statis', 'static']):
            return "html_static"
        if any(kw in desc for kw in ['python', 'script', 'program', 'automation']):
            return "python_script"
        return "html_static"

    def scaffold(self, project_name: str, template_key: str = None, description: str = "") -> Dict:
        if not template_key:
            template_key = self.detect_project_type(description)

        template = PROJECT_TEMPLATES.get(template_key)
        if not template:
            return {"success": False, "error": f"Template '{template_key}' not found", "path": ""}

        safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in project_name.lower())
        project_path = os.path.join(self.base_dir, safe_name)
        os.makedirs(project_path, exist_ok=True)

        created_files = []
        for filepath, content in template["structure"].items():
            full_path = os.path.join(project_path, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
            created_files.append(filepath)

        if template.get("dependencies") and template["type"] == "python":
            self._install_python_deps(template["dependencies"])

        post_init = template.get("post_init")
        if post_init:
            self._run_post_init(project_path, post_init)

        self.logger.info(f"Scaffolded project '{project_name}' at {project_path} using template '{template_key}'")

        return {
            "success": True,
            "path": project_path,
            "template": template_key,
            "template_name": template["name"],
            "files": created_files,
            "type": template["type"],
        }

    def _install_python_deps(self, deps: List[str]):
        for dep in deps:
            try:
                subprocess.run(
                    ['pip', 'install', '--break-system-packages', '--quiet', dep],
                    capture_output=True, text=True, timeout=60
                )
                self.logger.info(f"Installed Python dep: {dep}")
            except Exception as e:
                self.logger.warning(f"Failed to install {dep}: {e}")

    def _run_post_init(self, project_path: str, command: str):
        try:
            subprocess.run(
                command, shell=True, cwd=project_path,
                capture_output=True, text=True, timeout=120
            )
            self.logger.info(f"Post-init command completed: {command}")
        except Exception as e:
            self.logger.warning(f"Post-init error: {e}")

    def list_templates(self) -> List[Dict]:
        return [
            {"key": k, "name": v["name"], "type": v["type"]}
            for k, v in PROJECT_TEMPLATES.items()
        ]

    def get_project_info(self, project_path: str) -> Dict:
        if not os.path.isdir(project_path):
            return {"exists": False}

        files = []
        for root, dirs, fnames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git')]
            for fname in fnames:
                rel = os.path.relpath(os.path.join(root, fname), project_path)
                files.append(rel)

        project_type = "unknown"
        if any(f.endswith('.py') for f in files):
            project_type = "python"
        if 'package.json' in files:
            project_type = "node"
        if any(f.endswith('.html') for f in files) and project_type == "unknown":
            project_type = "static"

        return {
            "exists": True,
            "path": project_path,
            "type": project_type,
            "files": files,
            "file_count": len(files),
        }
