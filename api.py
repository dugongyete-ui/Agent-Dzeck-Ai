#!/usr/bin/env python3

import os, sys
import uvicorn
import aiofiles
import configparser
import asyncio
import time
import zipfile
import io
import shutil
import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid

from sources.llm_provider import Provider
from sources.interaction import Interaction
from sources.agents import CasualAgent, CoderAgent, FileAgent, PlannerAgent, BrowserAgent
from sources.browser import Browser, create_driver
from sources.utility import pretty_print
from sources.logger import Logger
from sources.schemas import QueryRequest, QueryResponse
from sources.workspace_manager import WorkspaceManager
from sources.realtime import ws_manager
from pydantic import BaseModel

class ModelConfigUpdate(BaseModel):
    provider_name: str
    model: str

from dotenv import load_dotenv

load_dotenv()


def is_running_in_docker():
    if os.path.exists('/.dockerenv'):
        return True
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        pass
    return False


api = FastAPI(title="Agent Dzeck AI API", version="0.2.0")
logger = Logger("backend.log")
config = configparser.ConfigParser()
config.read('config.ini')

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists(".screenshots"):
    os.makedirs(".screenshots")
api.mount("/screenshots", StaticFiles(directory=".screenshots"), name="screenshots")

work_dir_path = os.getenv('WORK_DIR') or config["MAIN"].get("work_dir", "/home/runner/workspace/work")
if not os.path.exists(work_dir_path):
    os.makedirs(work_dir_path, exist_ok=True)
    print(f"[Agent Dzeck AI] Created work directory: {work_dir_path}")
print(f"[Agent Dzeck AI] Work directory: {work_dir_path}")

workspace_mgr = WorkspaceManager(base_dir=work_dir_path)

api.mount("/workspace", StaticFiles(directory=work_dir_path, html=True), name="workspace")

def initialize_system():
    stealth_mode = config.getboolean('BROWSER', 'stealth_mode')
    personality_folder = "jarvis" if config.getboolean('MAIN', 'jarvis_personality') else "base"
    languages = config["MAIN"]["languages"].split(' ')
    
    headless = config.getboolean('BROWSER', 'headless_browser')
    if is_running_in_docker() and not headless:
        print("\n" + "*" * 70)
        print("*** WARNING: Detected Docker environment - forcing headless_browser=True ***")
        print("*** INFO: To see the browser, run 'python cli.py' on your host machine ***")
        print("*" * 70 + "\n")
        sys.stdout.flush()
        logger.warning("Detected Docker environment - forcing headless_browser=True")
        headless = True
    
    provider = Provider(
        provider_name=config["MAIN"]["provider_name"],
        model=config["MAIN"]["provider_model"],
        server_address=config["MAIN"]["provider_server_address"],
        is_local=config.getboolean('MAIN', 'is_local')
    )
    logger.info(f"Provider initialized: {provider.provider_name} ({provider.model})")

    browser = Browser(
        create_driver(headless=headless, stealth_mode=stealth_mode, lang=languages[0]),
        anticaptcha_manual_install=stealth_mode
    )
    logger.info("Browser initialized")

    agents = [
        CasualAgent(
            name=config["MAIN"]["agent_name"],
            prompt_path=f"prompts/{personality_folder}/casual_agent.txt",
            provider=provider, verbose=False
        ),
        CoderAgent(
            name="coder",
            prompt_path=f"prompts/{personality_folder}/coder_agent.txt",
            provider=provider, verbose=False
        ),
        FileAgent(
            name="File Agent",
            prompt_path=f"prompts/{personality_folder}/file_agent.txt",
            provider=provider, verbose=False
        ),
        BrowserAgent(
            name="Browser",
            prompt_path=f"prompts/{personality_folder}/browser_agent.txt",
            provider=provider, verbose=False, browser=browser
        ),
        PlannerAgent(
            name="Planner",
            prompt_path=f"prompts/{personality_folder}/planner_agent.txt",
            provider=provider, verbose=False, browser=browser, ws_manager=ws_manager
        )
    ]
    logger.info("Agents initialized")

    interaction = Interaction(
        agents,
        tts_enabled=config.getboolean('MAIN', 'speak'),
        stt_enabled=config.getboolean('MAIN', 'listen'),
        recover_last_session=config.getboolean('MAIN', 'recover_last_session'),
        langs=languages
    )
    logger.info("Interaction initialized")
    return interaction

try:
    interaction = initialize_system()
except Exception as e:
    logger.error(f"Failed to initialize system: {str(e)}")
    print(f"[Agent Dzeck AI] FATAL: Failed to initialize system: {str(e)}")
    interaction = None
is_generating = False
query_resp_history = []


@api.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


@api.get("/screenshot")
async def get_screenshot():
    logger.info("Screenshot endpoint called")
    screenshot_path = ".screenshots/updated_screen.png"
    if os.path.exists(screenshot_path):
        return FileResponse(screenshot_path)
    logger.error("No screenshot available")
    return JSONResponse(
        status_code=404,
        content={"error": "No screenshot available"}
    )

@api.get("/health")
async def health_check():
    logger.info("Health check endpoint called")
    if interaction is None:
        return {"status": "degraded", "version": "0.2.0", "error": "System not fully initialized. Check API key configuration."}
    return {
        "status": "healthy",
        "version": "0.2.0",
        "features": {
            "websocket": True,
            "workspace_manager": True,
            "live_preview": True,
            "realtime_status": True,
        }
    }

@api.get("/is_active")
async def is_active():
    logger.info("Is active endpoint called")
    if interaction is None:
        return {"is_active": False, "error": "System not initialized. Check OPENAI_API_KEY."}
    return {"is_active": interaction.is_active}

@api.get("/stop")
async def stop():
    global is_generating
    logger.info("Stop endpoint called")
    if interaction is None or interaction.current_agent is None:
        return JSONResponse(status_code=503, content={"error": "System not initialized"})
    interaction.current_agent.request_stop()
    is_generating = False
    await ws_manager.send_status("system", "Dihentikan", 0.0, "Proses dihentikan oleh pengguna")
    return JSONResponse(status_code=200, content={"status": "stopped"})

@api.post("/new_chat")
async def new_chat():
    global query_resp_history, is_generating
    logger.info("New chat endpoint called")
    is_generating = False
    query_resp_history = []
    if interaction is not None:
        if config.getboolean('MAIN', 'save_session'):
            interaction.save_session()
        interaction.last_answer = None
        interaction.last_reasoning = None
        interaction.last_query = None
        interaction.current_agent = None
        for agent in interaction.agents:
            agent.memory.reset()
            agent.blocks_result = []
            agent.stop = False
            agent.success = True
            agent.last_answer = ""
            agent.last_reasoning = ""
            agent.status_message = "Siap"
    await ws_manager.send_status("system", "Chat baru dimulai", 0.0)
    return JSONResponse(status_code=200, content={"status": "new_chat_created"})

@api.post("/new_project")
async def new_project():
    global query_resp_history, is_generating
    logger.info("New project endpoint called - clearing work_dir and resetting all state")
    is_generating = False
    query_resp_history = []

    if interaction is not None:
        if config.getboolean('MAIN', 'save_session'):
            interaction.save_session()
        interaction.last_answer = None
        interaction.last_reasoning = None
        interaction.last_query = None
        interaction.current_agent = None
        for agent in interaction.agents:
            agent.memory.reset()
            agent.blocks_result = []
            agent.stop = False
            agent.success = True
            agent.last_answer = ""
            agent.last_reasoning = ""
            agent.status_message = "Siap"

    cleared_files = 0
    try:
        if os.path.isdir(work_dir_path):
            for item in os.listdir(work_dir_path):
                item_path = os.path.join(work_dir_path, item)
                if item.startswith('.'):
                    continue
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        cleared_files += 1
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        cleared_files += 1
                except Exception as e:
                    logger.error(f"Failed to remove {item_path}: {e}")
        logger.info(f"Cleared {cleared_files} items from work_dir")
    except Exception as e:
        logger.error(f"Failed to clear work_dir: {e}")

    await ws_manager.send_status("system", "Project baru dimulai", 0.0)
    return JSONResponse(status_code=200, content={
        "status": "new_project_created",
        "cleared_files": cleared_files
    })

@api.post("/clear_history")
async def clear_history():
    global query_resp_history
    logger.info("Clear history endpoint called")
    query_resp_history = []
    if interaction is not None:
        if config.getboolean('MAIN', 'save_session'):
            interaction.save_session()
        interaction.last_answer = None
        interaction.last_reasoning = None
        interaction.last_query = None
        for agent in interaction.agents:
            agent.memory.reset()
            agent.blocks_result = []
            agent.stop = False
            agent.success = True
            agent.last_answer = ""
            agent.last_reasoning = ""
    return JSONResponse(status_code=200, content={"status": "history_cleared"})

@api.get("/latest_answer")
async def get_latest_answer():
    global query_resp_history
    if interaction is None or interaction.current_agent is None:
        return JSONResponse(status_code=200, content={
            "done": "true",
            "answer": "",
            "reasoning": "",
            "agent_name": "None",
            "success": "false",
            "blocks": {},
            "status": "Agent siap" if interaction is not None else "Sistem memulai...",
            "uid": str(uuid.uuid4())
        })

    if not is_generating:
        status_msg = interaction.current_agent.get_status_message if interaction.current_agent else "Siap"
        return JSONResponse(status_code=200, content={
            "done": "true",
            "answer": "",
            "reasoning": "",
            "agent_name": interaction.current_agent.agent_name if interaction.current_agent else "None",
            "success": "true",
            "blocks": {},
            "status": status_msg,
            "uid": str(uuid.uuid4())
        })

    return JSONResponse(status_code=200, content={
        "done": "false",
        "answer": "",
        "reasoning": "",
        "agent_name": interaction.current_agent.agent_name if interaction.current_agent else "None",
        "success": "false",
        "blocks": {},
        "status": interaction.current_agent.get_status_message if interaction.current_agent else "Memproses...",
        "uid": str(uuid.uuid4())
    })

async def think_wrapper(interaction, query):
    try:
        interaction.last_query = query
        logger.info("Agents request is being processed")
        await ws_manager.send_status("system", "Memproses permintaan...", 0.1, query[:100])

        agent = interaction.router.select_agent(query)
        if agent:
            await ws_manager.send_agent_switch(agent.agent_name, agent.type)

        success = await interaction.think()
        if not success:
            interaction.last_answer = "Error: No answer from agent"
            interaction.last_reasoning = "Error: No reasoning from agent"
            interaction.last_success = False
            await ws_manager.send_status("system", "Gagal memproses", 1.0)
        else:
            interaction.last_success = True
            await ws_manager.send_status("system", "Selesai", 1.0)
        pretty_print(interaction.last_answer)
        interaction.speak_answer()
        return success
    except Exception as e:
        logger.error(f"Error in think_wrapper: {str(e)}")
        interaction.last_answer = f"Error: {str(e)}"
        interaction.last_reasoning = f"Error: {str(e)}"
        interaction.last_success = False
        await ws_manager.send_status("system", f"Error: {str(e)[:100]}", 1.0)
        raise e

@api.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    global is_generating, query_resp_history
    logger.info(f"Processing query: {request.query}")
    query_resp = QueryResponse(
        done="false",
        answer="",
        reasoning="",
        agent_name="Unknown",
        success="false",
        blocks={},
        status="Ready",
        uid=str(uuid.uuid4())
    )
    if interaction is None:
        query_resp.answer = "System not initialized. Please check your API key configuration."
        query_resp.done = "true"
        return JSONResponse(status_code=503, content=query_resp.jsonify())
    if is_generating:
        logger.warning("Another query is being processed, please wait.")
        return JSONResponse(status_code=429, content=query_resp.jsonify())

    try:
        is_generating = True
        success = await think_wrapper(interaction, request.query)
        is_generating = False

        if not success:
            query_resp.answer = interaction.last_answer or ""
            query_resp.reasoning = interaction.last_reasoning or ""
            return JSONResponse(status_code=400, content=query_resp.jsonify())

        if interaction.current_agent:
            blocks_json = {f'{i}': block.jsonify() for i, block in enumerate(interaction.current_agent.get_blocks_result())}
        else:
            logger.error("No current agent found")
            blocks_json = {}
            query_resp.answer = "Error: No current agent"
            return JSONResponse(status_code=400, content=query_resp.jsonify())

        formatted_answer = interaction.current_agent.get_formatted_answer()
        if not formatted_answer or formatted_answer.strip() == "":
            formatted_answer = interaction.last_answer or ""

        logger.info(f"Answer: {formatted_answer}")
        logger.info(f"Blocks: {blocks_json}")
        query_resp.done = "true"
        query_resp.answer = formatted_answer
        query_resp.reasoning = interaction.last_reasoning or ""
        query_resp.agent_name = interaction.current_agent.agent_name
        query_resp.success = str(interaction.last_success)
        query_resp.blocks = blocks_json
        
        query_resp_dict = {
            "done": query_resp.done,
            "answer": query_resp.answer,
            "agent_name": query_resp.agent_name,
            "success": query_resp.success,
            "blocks": query_resp.blocks,
            "status": query_resp.status,
            "uid": query_resp.uid
        }
        query_resp_history.append(query_resp_dict)

        await _check_and_notify_preview()

        logger.info("Query processed successfully")
        return JSONResponse(status_code=200, content=query_resp.jsonify())
    except Exception as e:
        is_generating = False
        error_msg = str(e)
        logger.error(f"An error occurred: {error_msg}")
        if "402" in error_msg or "payment" in error_msg.lower() or "credit" in error_msg.lower() or "depleted" in error_msg.lower():
            query_resp.answer = "Kredit API habis. Silakan ganti ke provider Groq di pengaturan Model AI, atau isi ulang kredit HuggingFace Anda."
            query_resp.done = "true"
            return JSONResponse(status_code=200, content=query_resp.jsonify())
        if "429" in error_msg or "rate_limit" in error_msg.lower() or "rate limit" in error_msg.lower():
            query_resp.answer = "Batas penggunaan API tercapai. Silakan tunggu beberapa menit dan coba lagi."
            query_resp.done = "true"
            return JSONResponse(status_code=200, content=query_resp.jsonify())
        if "api_key" in error_msg.lower() or "api key" in error_msg.lower():
            query_resp.answer = "API Key tidak ditemukan atau tidak valid. Silakan periksa pengaturan API Key Anda."
            query_resp.done = "true"
            return JSONResponse(status_code=200, content=query_resp.jsonify())
        query_resp.answer = f"Terjadi kesalahan saat memproses. Silakan coba lagi. Detail: {error_msg[:200]}"
        query_resp.reasoning = f"Exception terjadi saat pemrosesan."
        query_resp.done = "true"
        return JSONResponse(status_code=200, content=query_resp.jsonify())
    finally:
        is_generating = False
        logger.info("Processing finished")
        if config.getboolean('MAIN', 'save_session'):
            interaction.save_session()


async def _check_and_notify_preview():
    try:
        files = []
        all_files = []
        for root, dirs, fnames in os.walk(work_dir_path):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.cache')]
            for fname in fnames:
                rel = os.path.relpath(os.path.join(root, fname), work_dir_path)
                all_files.append(rel)
                if fname.endswith('.html'):
                    files.append(rel)

        for f in all_files:
            await ws_manager.send_file_update("create", f)

        if files:
            main_file = "index.html" if "index.html" in files else files[0]
            await ws_manager.send_preview_ready(f"/api/preview/{main_file}", "static_html")
            logger.info(f"Preview ready: /api/preview/{main_file}, total files: {len(all_files)}")
        elif all_files:
            logger.info(f"Files created but no HTML: {all_files}")
    except Exception as e:
        logger.error(f"Error in _check_and_notify_preview: {e}")


@api.get("/api/preview/{file_path:path}")
async def serve_preview(file_path: str):
    abs_work_dir = os.path.abspath(work_dir_path)
    full_path = os.path.abspath(os.path.join(abs_work_dir, file_path))
    if not full_path.startswith(abs_work_dir):
        return JSONResponse(status_code=403, content={"error": "Access denied"})
    if not os.path.isfile(full_path):
        logger.warning(f"Preview file not found: {full_path}")
        return JSONResponse(status_code=404, content={"error": f"File not found: {file_path}"})
    
    ext = os.path.splitext(file_path)[1].lower()
    content_types = {
        '.html': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.ttf': 'font/ttf',
    }
    media_type = content_types.get(ext, 'application/octet-stream')
    
    return FileResponse(
        full_path,
        media_type=media_type,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@api.get("/api/preview-files")
async def list_preview_files():
    html_files = []
    all_files = []
    for root, dirs, fnames in os.walk(work_dir_path):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.cache')]
        for fname in fnames:
            rel = os.path.relpath(os.path.join(root, fname), work_dir_path)
            all_files.append(rel)
            if fname.endswith('.html'):
                html_files.append(rel)
    main_file = None
    if html_files:
        main_file = "index.html" if "index.html" in html_files else html_files[0]
    return JSONResponse(status_code=200, content={
        "files": html_files,
        "all_files": all_files,
        "total": len(html_files),
        "total_all": len(all_files),
        "main_file": main_file,
        "preview_url": f"/api/preview/{main_file}" if main_file else None
    })


@api.get("/api/download-zip")
async def download_project_zip():
    work_dir = work_dir_path
    if not os.path.isdir(work_dir):
        return JSONResponse(status_code=404, content={"error": "Belum ada project yang dibuat. Minta AI untuk membuat project terlebih dahulu."})
    
    files_found = False
    for root, dirs, files in os.walk(work_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.cache')]
        if files:
            files_found = True
            break
    
    if not files_found:
        return JSONResponse(status_code=404, content={"error": "Folder project kosong. Minta AI untuk membuat kode terlebih dahulu."})

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(work_dir):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.cache')]
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, work_dir)
                try:
                    zf.write(file_path, arcname)
                except Exception:
                    pass
    
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=agent-dzeck-project.zip"}
    )

@api.get("/api/project-files")
async def list_project_files():
    work_dir = work_dir_path
    if not os.path.isdir(work_dir):
        return JSONResponse(status_code=200, content={"files": [], "total": 0})
    
    files_list = []
    for root, dirs, files in os.walk(work_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git', '.cache')]
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, work_dir)
            try:
                size = os.path.getsize(file_path)
                files_list.append({"name": rel_path, "size": size})
            except Exception:
                pass
    
    return JSONResponse(status_code=200, content={"files": files_list, "total": len(files_list)})

@api.get("/api/file-content/{file_path:path}")
async def get_file_content(file_path: str):
    work_dir = work_dir_path
    full_path = os.path.join(work_dir, file_path)
    if not full_path.startswith(os.path.abspath(work_dir)):
        return JSONResponse(status_code=403, content={"error": "Access denied"})
    if not os.path.isfile(full_path):
        return JSONResponse(status_code=404, content={"error": "File not found"})
    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return JSONResponse(status_code=200, content={
            "file": file_path,
            "content": content[:100000],
            "size": os.path.getsize(full_path),
            "truncated": len(content) > 100000,
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@api.put("/api/file-content/{file_path:path}")
async def save_file_content(file_path: str, request: dict):
    work_dir = work_dir_path
    full_path = os.path.join(work_dir, file_path)
    if not full_path.startswith(os.path.abspath(work_dir)):
        return JSONResponse(status_code=403, content={"error": "Access denied"})
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    try:
        content = request.get("content", "")
        async with aiofiles.open(full_path, 'w', encoding='utf-8') as f:
            await f.write(content)
        await ws_manager.send_file_update("save", file_path)
        return JSONResponse(status_code=200, content={
            "status": "saved",
            "file": file_path,
            "size": os.path.getsize(full_path)
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@api.get("/api/workspace/stats")
async def workspace_stats():
    return JSONResponse(status_code=200, content=workspace_mgr.get_workspace_stats())

@api.get("/api/workspace/list")
async def workspace_list():
    return JSONResponse(status_code=200, content={"workspaces": workspace_mgr.list_workspaces()})

@api.get("/api/workspace/structure")
async def workspace_structure():
    return JSONResponse(status_code=200, content=workspace_mgr.get_project_structure())


@api.get("/api/sandbox/stats")
async def sandbox_stats():
    if interaction is None:
        return JSONResponse(status_code=503, content={"error": "System not initialized"})
    for agent in interaction.agents:
        if hasattr(agent, 'sandbox') and agent.sandbox:
            return JSONResponse(status_code=200, content=agent.sandbox.get_stats())
    return JSONResponse(status_code=200, content={"total_executions": 0})


@api.get("/api/scaffolder/templates")
async def scaffolder_templates():
    from sources.tools.project_scaffolder import ProjectScaffolder
    scaffolder = ProjectScaffolder(base_dir=work_dir_path)
    return JSONResponse(status_code=200, content={"templates": scaffolder.list_templates()})


@api.post("/api/scaffolder/create")
async def scaffolder_create(request: dict):
    from sources.tools.project_scaffolder import ProjectScaffolder
    scaffolder = ProjectScaffolder(base_dir=work_dir_path)
    project_name = request.get("name", "new-project")
    template = request.get("template", None)
    description = request.get("description", "")
    result = scaffolder.scaffold(project_name, template, description)
    return JSONResponse(status_code=200, content=result)


@api.get("/api/memory/stats")
async def memory_stats():
    if interaction is None:
        return JSONResponse(status_code=503, content={"error": "System not initialized"})
    pm = interaction.persistent_memory
    return JSONResponse(status_code=200, content={
        "facts_count": len(pm.facts),
        "skills_count": len(pm.skills),
        "preferences": pm.get_preferences(),
        "recent_projects": pm.get_recent_projects(5),
    })


@api.get("/api/config/models")
async def get_model_config():
    models_by_provider = {
        "groq": {
            "name": "Groq",
            "models": [
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant",
                "qwen/qwen3-32b",
                "meta-llama/llama-4-scout-17b-16e-instruct",
                "openai/gpt-oss-20b",
            ],
            "server": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY"
        },
        "huggingface": {
            "name": "HuggingFace",
            "models": [
                "Qwen/Qwen2.5-72B-Instruct",
                "Qwen/Qwen2.5-3B-Instruct",
                "meta-llama/Llama-3.3-70B-Instruct",
                "mistralai/Mixtral-8x7B-Instruct-v0.1",
            ],
            "server": "https://api-inference.huggingface.co",
            "api_key_env": "HUGGINGFACE_API_KEY",
            "note": "Membutuhkan kredit HuggingFace"
        }
    }

    current_provider = config["MAIN"]["provider_name"]
    current_model = config["MAIN"]["provider_model"]

    return JSONResponse(status_code=200, content={
        "current_provider": current_provider,
        "current_model": current_model,
        "providers": models_by_provider
    })

@api.post("/api/config/update")
async def update_model_config(request: ModelConfigUpdate):
    global interaction
    provider_name = request.provider_name
    model = request.model

    if not provider_name or not model:
        return JSONResponse(status_code=400, content={"error": "provider_name and model are required"})

    config["MAIN"]["provider_name"] = provider_name
    config["MAIN"]["provider_model"] = model

    with open('config.ini', 'w') as f:
        config.write(f)

    try:
        interaction = initialize_system()
        await ws_manager.send_status("system", f"Model diganti ke {model}", 1.0)
        return JSONResponse(status_code=200, content={
            "status": "updated",
            "provider": provider_name,
            "model": model
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": f"Failed to reinitialize with new config: {str(e)}"
        })

FRONTEND_BUILD_DIR = os.path.join(os.path.dirname(__file__), "frontend", "agentic-seek-front", "build")

if os.path.isdir(FRONTEND_BUILD_DIR):
    api.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_BUILD_DIR, "static")), name="frontend-static")

    @api.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(FRONTEND_BUILD_DIR, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_BUILD_DIR, "index.html"))

if __name__ == "__main__":
    try:
        import install_deps
        install_deps.install_requirements()
    except Exception as e:
        print(f"[Agent Dzeck AI] Auto-install deps skipped: {e}")

    if is_running_in_docker():
        print("[Agent Dzeck AI] Starting in Docker container...")
    else:
        print("[Agent Dzeck AI] Starting on host machine...")
    
    uvicorn.run(api, host="0.0.0.0", port=5000)
