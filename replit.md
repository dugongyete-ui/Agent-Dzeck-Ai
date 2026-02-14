# Agent Dzeck AI

## Overview
Agent Dzeck AI adalah sistem AI agent otonom dengan kemampuan browsing web, eksekusi kode, dan manipulasi file. Menggunakan backend FastAPI yang melayani frontend React, didukung oleh model Groq dan HuggingFace. Fitur meliputi eksekusi kode sandbox, routing agent berbasis ML (AdaptiveClassifier), arsitektur multi-agent, dan pemulihan error yang robust.

## Architecture
- **Backend**: Python FastAPI (api.py) on port 5000
- **Frontend**: React app pre-built at `frontend/agentic-seek-front/build/`, served as static files by FastAPI
- **AI Providers**: Hanya 2 provider yang didukung:
  - **Groq** - llama-3.3-70b-versatile (utama)
  - **HuggingFace** - Qwen/Qwen2.5-72B-Instruct (gratis)
- **Agent System**: ML-based router (AdaptiveClassifier + keyword override) selects from 5 agents:
  - CasualAgent (Dzeck) - general conversation
  - CoderAgent (Coder) - Full-Stack Autonomous Developer with sandbox safety
  - FileAgent (File) - file manipulation
  - BrowserAgent (Browser) - web browsing via Selenium/Chromium headless
  - PlannerAgent (Planner) - multi-step task planning
- **Router**: Keyword-based override untuk tugas koding (mendeteksi "buatkan website", "buat program", dll) + ML classifier sebagai fallback
- **Memory**: Conversation memory with compression
- **Language**: LanguageUtility with MarianMT translation models
- **Browser**: Selenium with headless Chromium
- **Sandbox**: Safe code execution with whitelist mode, workspace isolation per session, path restriction
- **Workspace Manager**: Dynamic multi-project workspace with session isolation, project type detection
- **Real-time**: WebSocket for live status updates, execution progress, file notifications
- **Live Preview**: Iframe-based preview for generated websites, file selector, project file viewer

## Key Files
- `api.py` - FastAPI server, serves frontend + API endpoints
- `config.ini` - Configuration (provider, model, browser settings, work_dir)
- `sources/llm_provider.py` - LLM provider (hanya Groq dan HuggingFace)
- `sources/interaction.py` - Main interaction loop
- `sources/router.py` - Agent routing (keyword override + AdaptiveClassifier)
- `sources/browser.py` - Browser automation via Selenium
- `sources/memory.py` - Conversation memory
- `sources/language.py` - Language detection + translation
- `sources/sandbox.py` - Safe code execution sandbox
- `sources/agents/` - Agent implementations
  - `code_agent.py` - CoderAgent with sandbox (max 7 attempts, auto-fix)
  - `planner_agent.py` - PlannerAgent
  - `casual_agent.py` - CasualAgent
  - `browser_agent.py` - BrowserAgent
  - `file_agent.py` - FileAgent
- `setup_dependencies.sh` - Auto-install all dependencies (dengan --break-system-packages)

## Configuration
- Provider: huggingface atau groq (set in config.ini)
- HUGGINGFACE_API_KEY: stored as secret
- GROQ_API_KEY: stored as secret
- agent_name: Dzeck
- Browser: headless mode
- work_dir: /home/runner/workspace/work
- languages: id (Indonesian)

## User Preferences
- Language: Indonesian (Bahasa Indonesia)
- Hanya gunakan 2 provider: Groq dan HuggingFace
- Provider lain (OpenAI, DeepSeek, Together, Google, OpenRouter, Ollama, Anthropic, LM-Studio) sudah dihapus
- Project name: Agent Dzeck AI

## Recent Changes
- 2026-02-15: FIX - Browser tab tidak muncul di mobile + screenshot tidak auto-refresh
  - Mobile bottom nav sekarang menampilkan semua 5 tab (Chat, Preview, Editor, Files, Browser)
  - CSS responsive: padding/font-size diperkecil untuk 5 tab di mobile
  - Screenshot auto-refresh setiap 3 detik saat Browser tab aktif atau BrowserAgent sedang bekerja
  - Tambah state activeAgentType untuk melacak agent yang sedang aktif
  - handleSubmit tidak lagi force switch ke Chat tab - user tetap di tab aktif
  - activeAgentType di-reset otomatis 10 detik setelah proses selesai
  - WebSocket agent_switch langsung fetch screenshot saat BrowserAgent aktif
  - GROQ_API_KEY berhasil di-set sebagai secret
- 2026-02-14: FIX - Routing pencarian web + auto-switch tab
  - Router sekarang mengenali keyword Indonesia: carikan, cari, temukan + target kata (website, drama, film, dll)
  - Web search query diprioritaskan sebelum code task check
  - Tambah 18 few-shot examples pencarian web Bahasa Indonesia
  - WebSocket send_agent_switch: frontend auto-switch ke Browser tab saat BrowserAgent aktif
  - Frontend auto-switch ke Preview tab saat preview_ready atau CoderAgent aktif
- 2026-02-14: BUG FIX - New Project tidak membersihkan file lama
  - Tambah endpoint POST /new_project yang menghapus semua file di work_dir + reset chat + reset agent memory
  - Frontend handleNewChat sekarang memanggil /new_project bukan /new_chat
  - Frontend me-reset semua state: previewFiles, projectFiles, editorContent, selectedPreviewFile dll
  - File project lama sekarang benar-benar terhapus saat membuat project baru
- 2026-02-14: CRITICAL FIX - pip install gagal di Replit Nix environment
  - Removed `--break-system-packages` flag dari sandbox.py, terminal.py, BashInterpreter.py
  - Replit pip bekerja tanpa flag khusus, flag tersebut malah menyebabkan "externally-managed-environment" error
  - Environment variables (PATH, PYTHONDONTWRITEBYTECODE) sekarang di-pass ke subprocess
- 2026-02-14: FIX - BashInterpreter false positive error detection
  - Patterns terlalu agresif (e.g., "not found" triggered pada output sukses)
  - Diganti dengan pattern yang lebih spesifik (Traceback, SyntaxError, dll)
- 2026-02-14: FIX - File saving reliability
  - save_block() sekarang menggunakan encoding UTF-8 dan verifikasi setelah save
  - os.makedirs() menggunakan exist_ok=True untuk mencegah race condition
- 2026-02-14: FIX - Preview & file serving
  - Mounted work_dir sebagai /workspace static files untuk akses langsung
  - preview-files endpoint sekarang mengembalikan main_file dan preview_url
  - Path resolution di serve_preview menggunakan os.path.abspath untuk keamanan
  - _check_and_notify_preview mengirim file_update WebSocket untuk SEMUA file, bukan hanya HTML
- 2026-02-14: CRITICAL FIX - Tag matching collision: `\`\`\`c` matched `\`\`\`css`, `\`\`\`java` matched `\`\`\`javascript`
  - Added `_is_exact_tag_match()` in tools.py - checks next char after tag is non-alphabetical
  - CSS/JS files were being "executed" as C/Java instead of saved - now properly saved to disk
  - Preview/Editor/Files tabs were empty because files were never saved correctly
- 2026-02-14: FIX - Duplicate responses in chat: `/latest_answer` polling + `/query` POST both adding messages
  - `/latest_answer` now only returns status updates during processing, not answer content
  - Only `/query` POST returns the final answer, preventing duplicates
- 2026-02-14: CRITICAL FIX - Fixed "block:0, block:1" placeholder text in AI responses
  - Added `get_formatted_answer()` method to Agent base class - replaces block markers with meaningful file/execution summaries
  - Updated `executorResult` schema to include `save_path` for filename tracking
  - Fixed API `/query` and `/latest_answer` endpoints to return formatted answers
  - Fixed `_verify_saved_files()` called after `remove_blocks()` - now verification runs before blocks are stripped
  - Updated `execute_modules()` and `execute_modules_with_sandbox()` to pass save_path to executorResult
- 2026-02-14: MAJOR UPGRADE - Frontend rebuilt: Editor tab sekarang bisa edit file project dengan save (Ctrl+S), file tree, line numbers
- 2026-02-14: FEATURE - PUT /api/file-content/{path} endpoint untuk save file yang diedit dari Editor
- 2026-02-14: UPGRADE - Preview tab: iframe preview dengan file selector, refresh, empty state dengan action button
- 2026-02-14: UPGRADE - Files tab: split layout file tree + viewer, tombol download individual dan "Edit di Editor"
- 2026-02-14: UPGRADE - Chat tab: progress bar real-time dengan shimmer animation, quick actions (4 template)
- 2026-02-14: UPGRADE - Semua tab (Chat, Preview, Editor, Files, Browser) sudah berfungsi sempurna
- 2026-02-14: MAJOR FEATURE - Autonomous Orchestrator: Plan→Execute→Observe→Reflect loop di PlannerAgent
- 2026-02-14: FEATURE - sources/orchestrator.py: AutonomousOrchestrator dengan WebSocket status updates, auto-retry, recovery plan
- 2026-02-14: CRITICAL FIX - Sandbox: auto-strip server start code, Port 5000 conflict resolved
- 2026-02-14: FEATURE - Auto-install dependencies, Workspace Manager, Sandbox whitelist mode
- 2026-02-14: UPGRADE - CoderAgent: Full-Stack Autonomous Developer mode (max 7 attempts, auto-fix)
- 2026-02-14: CLEANUP - Hapus semua provider kecuali Groq dan HuggingFace

## Running
- Workflow "Start application" runs `python api.py`
- Server binds to 0.0.0.0:5000
- Frontend served from same port
- First startup downloads ML models (~500MB)
