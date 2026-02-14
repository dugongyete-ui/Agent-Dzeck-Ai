import platform, os
import asyncio

from sources.utility import pretty_print, animate_thinking
from sources.agents.agent import Agent, executorResult
from sources.tools.C_Interpreter import CInterpreter
from sources.tools.GoInterpreter import GoInterpreter
from sources.tools.PyInterpreter import PyInterpreter
from sources.tools.BashInterpreter import BashInterpreter
from sources.tools.JavaInterpreter import JavaInterpreter
from sources.tools.fileFinder import FileFinder
from sources.tools.SaveTool import HTMLSaveTool, CSSSaveTool, JSSaveTool, TypeScriptSaveTool, SQLSaveTool
from sources.tools.terminal import PersistentTerminal
from sources.tools.web_viewer import WebViewer
from sources.tools.project_scaffolder import ProjectScaffolder
from sources.logger import Logger
from sources.memory import Memory
from sources.sandbox import Sandbox

class CoderAgent(Agent):
    def __init__(self, name, prompt_path, provider, verbose=False, use_sandbox=True):
        super().__init__(name, prompt_path, provider, verbose, None)
        self.tools = {
            "bash": BashInterpreter(),
            "python": PyInterpreter(),
            "c": CInterpreter(),
            "go": GoInterpreter(),
            "java": JavaInterpreter(),
            "html": HTMLSaveTool(),
            "css": CSSSaveTool(),
            "javascript": JSSaveTool(),
            "typescript": TypeScriptSaveTool(),
            "sql": SQLSaveTool(),
            "file_finder": FileFinder()
        }
        self.work_dir = self.tools["file_finder"].get_work_dir()
        self.use_sandbox = use_sandbox
        if self.use_sandbox:
            self.sandbox = Sandbox(work_dir=self.work_dir)
        else:
            self.sandbox = None
        self.terminal = PersistentTerminal(work_dir=self.work_dir)
        self.web_viewer = WebViewer()
        self.scaffolder = ProjectScaffolder(base_dir=self.work_dir)
        self.role = "code"
        self.type = "code_agent"
        self.logger = Logger("code_agent.log")
        self.memory = Memory(self.load_prompt(prompt_path),
                        recover_last_session=False,
                        memory_compression=False,
                        model_provider=provider.get_model_name())
        self.installed_packages = set()

    def add_sys_info_prompt(self, prompt):
        templates_info = ", ".join([f"{t['key']} ({t['name']})" for t in self.scaffolder.list_templates()])
        info = (
            f"System Info:\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Python Version: {platform.python_version()}\n"
            f"Environment: Server headless (tanpa display/GUI)\n"
            f"Direktori kerja: {self.work_dir}\n"
            f"Library tersedia: flask, requests, beautifulsoup4, numpy, sqlite3, json, csv, dan library standar Python\n"
            f"Package manager: pip install, npm install, yarn add (SEMUA DIIZINKAN)\n"
            f"\nMODE AUTONOMOUS FULL-STACK AKTIF:\n"
            f"- Kamu adalah AI Agent Autonomous Full-Stack Developer. LANGSUNG kerjakan tanpa bertanya.\n"
            f"- Kamu BISA install package: pip install, npm install, yarn add - semua diizinkan dan berjalan.\n"
            f"- Kamu BISA menjalankan: npx, npm init, git, curl, wget, dan command bash lainnya.\n"
            f"- Simpan file dengan format ```bahasa:namafile\n"
            f"- JANGAN tulis app.run(), uvicorn.run(), atau menjalankan server\n"
            f"- Port 5000 SUDAH DIGUNAKAN. JANGAN bind ke port 5000\n"
            f"- JANGAN gunakan Tkinter/GUI desktop (headless)\n"
            f"- Untuk website: buat HTML statis lengkap (HTML+CSS+JS) atau full-stack (Flask/FastAPI + Frontend)\n"
            f"- Untuk backend: simpan file tanpa app.run()\n"
            f"- SELALU buat kode LENGKAP, FUNGSIONAL, dan SIAP PAKAI\n"
            f"- JANGAN jelaskan, LANGSUNG tulis kode\n"
            f"- Template project tersedia: {templates_info}\n"
            f"- Untuk full-stack: buat backend (Flask/FastAPI) + frontend (HTML/CSS/JS) + database (SQLite)"
        )
        return f"{prompt}\n\n{info}"

    def sandbox_execute(self, code: str, language: str) -> tuple:
        if self.sandbox is None:
            return None, None
        if language not in ('python', 'bash'):
            return None, None
        result = self.sandbox.run(code, language)
        feedback = self.sandbox.format_result(result)
        return result.success, feedback

    def _is_save_only_language(self, name: str) -> bool:
        return name in ('c', 'go', 'java', 'html', 'css', 'javascript', 'typescript', 'sql')

    def _auto_install_from_error(self, error_text: str) -> bool:
        import re
        module_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_text)
        if not module_match:
            return False
        module_name = module_match.group(1).split('.')[0]
        if module_name in self.installed_packages:
            return False

        pkg_map = {
            'bs4': 'beautifulsoup4',
            'cv2': 'opencv-python',
            'PIL': 'Pillow',
            'sklearn': 'scikit-learn',
            'yaml': 'pyyaml',
            'dotenv': 'python-dotenv',
            'gi': 'PyGObject',
            'lxml': 'lxml',
            'matplotlib': 'matplotlib',
            'pandas': 'pandas',
            'scipy': 'scipy',
            'seaborn': 'seaborn',
        }
        pkg_name = pkg_map.get(module_name, module_name)

        self.logger.info(f"Auto-installing: {pkg_name}")
        pretty_print(f"📦 Auto-installing: {pkg_name}...", color="status")
        result = self.terminal.install_package(pkg_name)
        if result['success']:
            self.installed_packages.add(module_name)
            pretty_print(f"✅ Installed: {pkg_name}", color="success")
            return True
        else:
            pretty_print(f"❌ Failed to install {pkg_name}: {result.get('stderr', '')}", color="failure")
            return False

    def _verify_saved_files(self, answer: str) -> str:
        import re
        file_pattern = r'```\w+:([^\n]+)'
        saved_files = re.findall(file_pattern, answer)
        if not saved_files:
            return ""

        verification_lines = []
        for fname in saved_files:
            fpath = os.path.join(self.work_dir, fname)
            if os.path.exists(fpath):
                size = os.path.getsize(fpath)
                if fname.endswith('.html'):
                    check = self.web_viewer.verify_html_file(fpath)
                    if check['success']:
                        verification_lines.append(f"✅ {fname} ({size}B) - HTML valid")
                    else:
                        verification_lines.append(f"⚠️ {fname} ({size}B) - {check['message']}")
                else:
                    verification_lines.append(f"✅ {fname} ({size}B)")
            else:
                verification_lines.append(f"❌ {fname} - tidak ditemukan")

        if verification_lines:
            return "\n📁 Verifikasi file:\n" + "\n".join(verification_lines)
        return ""

    def execute_modules_with_sandbox(self, answer: str):
        feedback = ""
        success = True
        if answer.startswith("```"):
            answer = "I will execute:\n" + answer

        self.success = True
        saved_files = []

        for name, tool in self.tools.items():
            feedback = ""
            blocks, save_path = tool.load_exec_block(answer)

            if blocks is not None:
                if save_path is not None:
                    tool.save_block(blocks, save_path)
                    saved_files.append(save_path)
                    pretty_print(f"📄 File saved: {save_path}", color="status")

                if save_path is not None and self._is_save_only_language(name):
                    feedback = f"[success] File {save_path} berhasil disimpan."
                    self.blocks_result.append(executorResult(blocks[0] if blocks else "", feedback, True, name, save_path))
                    self.memory.push('user', feedback)
                    continue

                pretty_print(f"⚡ Executing {len(blocks)} {name} blocks...", color="status")
                for block in blocks:
                    self.show_block(block)
                    if name in ('python', 'bash'):
                        sb_success, sb_feedback = self.sandbox_execute(block, name)
                        if sb_success is not None:
                            if not sb_success and 'No module named' in sb_feedback:
                                if self._auto_install_from_error(sb_feedback):
                                    sb_success, sb_feedback = self.sandbox_execute(block, name)

                            success = sb_success
                            feedback = sb_feedback
                            self.blocks_result.append(executorResult(block, feedback, success, name, save_path))
                            if not success:
                                self.success = False
                                self.memory.push('user', feedback)
                                return False, feedback
                            continue
                    output = tool.execute([block])
                    feedback = tool.interpreter_feedback(output)
                    success = not tool.execution_failure_check(output)
                    self.blocks_result.append(executorResult(block, feedback, success, name, save_path))
                    if not success:
                        self.success = False
                        self.memory.push('user', feedback)
                        return False, feedback
                self.memory.push('user', feedback)

        if saved_files:
            verification = self._verify_saved_files(answer)
            if verification:
                pretty_print(verification, color="info")
                feedback += verification

        return True, feedback

    def _build_debug_prompt(self, feedback, attempt, max_attempts):
        hints = ""
        feedback_lower = feedback.lower()
        if 'port' in feedback_lower and ('in use' in feedback_lower or 'already' in feedback_lower):
            hints = (
                "\n⛔ HINT: Error 'port in use' karena kamu menjalankan server.\n"
                "SOLUSI: HAPUS app.run() dan semua kode server. Simpan file saja.\n"
                "Untuk website: buat HTML statis lengkap (HTML+CSS+JS dalam satu file).\n"
            )
        elif 'no module named' in feedback_lower or 'modulenotfounderror' in feedback_lower:
            hints = (
                "\n📦 HINT: Module otomatis diinstall. Jika masih gagal:\n"
                "SOLUSI: Gunakan library standar Python atau alternatif yang tersedia.\n"
                "Tersedia: flask, requests, bs4, numpy, sqlite3, json, csv, math, random, datetime, os, sys.\n"
            )
        elif 'tkinter' in feedback_lower or 'display' in feedback_lower or 'no display' in feedback_lower:
            hints = (
                "\n🖥️ HINT: Lingkungan headless tanpa GUI.\n"
                "SOLUSI: JANGAN gunakan Tkinter/PyQt/GUI. Buat sebagai website HTML statis.\n"
            )
        elif 'address already in use' in feedback_lower:
            hints = (
                "\n🔌 HINT: Port sudah digunakan.\n"
                "SOLUSI: JANGAN jalankan server. Buat file HTML statis.\n"
            )
        elif 'permission denied' in feedback_lower:
            hints = (
                "\n🔒 HINT: Permission denied.\n"
                "SOLUSI: Pastikan menulis file di direktori kerja, bukan system directories.\n"
            )
        elif 'syntax' in feedback_lower:
            hints = (
                "\n📝 HINT: Syntax error ditemukan.\n"
                "SOLUSI: Periksa indentasi, tanda kurung, kutip, dan titik koma.\n"
            )

        return (
            f"🔧 AUTONOMOUS DEBUG MODE (percobaan {attempt}/{max_attempts})\n"
            f"Error yang terjadi:\n{feedback}\n\n"
            f"{hints}"
            f"INSTRUKSI MANDIRI:\n"
            f"1. BACA error message - identifikasi AKAR masalah\n"
            f"2. TULIS ULANG kode yang SUDAH DIPERBAIKI secara LENGKAP\n"
            f"3. Pastikan semua import dan syntax benar\n"
            f"4. Jika error berulang, GANTI PENDEKATAN sepenuhnya\n"
            f"5. JANGAN jelaskan, LANGSUNG tulis kode yang diperbaiki\n"
            f"6. INGAT: TANPA app.run(), TANPA Tkinter, TANPA server start"
        )

    async def process(self, prompt, speech_module) -> str:
        answer = ""
        attempt = 0
        max_attempts = 7
        prompt = self.add_sys_info_prompt(prompt)
        self.memory.push('user', prompt)
        clarify_trigger = "REQUEST_CLARIFICATION"
        original_prompt = prompt
        no_code_retries = 0

        while attempt < max_attempts and not self.stop:
            self.logger.info(f"Attempt {attempt + 1}/{max_attempts}")
            animate_thinking("Thinking...", color="status")
            self.status_message = f"🤖 Berpikir... (percobaan {attempt + 1}/{max_attempts})"
            await self.wait_message(speech_module)
            answer, reasoning = await self.llm_request()
            self.last_reasoning = reasoning
            if clarify_trigger in answer:
                self.last_answer = answer
                await asyncio.sleep(0)
                return answer, reasoning
            if "```" not in answer:
                if no_code_retries < 3 and any(kw in original_prompt.lower() for kw in [
                    'buatkan', 'buat ', 'create', 'make', 'write', 'build', 'coding',
                    'website', 'aplikasi', 'program', 'script', 'game', 'kalkulator',
                    'deploy', 'full stack', 'fullstack', 'api', 'server', 'debug',
                    'perbaiki', 'fix', 'error', 'todo', 'landing', 'page', 'dashboard',
                    'form', 'login', 'register', 'portfolio', 'blog', 'toko', 'shop',
                    'e-commerce', 'chat', 'bot'
                ]):
                    self.memory.push('user',
                        'PERINTAH: Kamu BELUM menulis kode. Sebagai AI Autonomous, kamu WAJIB langsung menulis kode LENGKAP sekarang.\n'
                        'Format: ```bahasa:namafile.ext\n'
                        'Contoh: ```python:app.py atau ```html:index.html\n'
                        'JANGAN jelaskan. JANGAN bertanya. LANGSUNG tulis seluruh kode yang dibutuhkan.'
                    )
                    no_code_retries += 1
                    attempt += 1
                    continue
                self.last_answer = answer
                await asyncio.sleep(0)
                break
            no_code_retries = 0
            self.show_answer()
            animate_thinking("Executing code...", color="status")
            self.status_message = f"⚡ Menjalankan kode... (percobaan {attempt + 1}/{max_attempts})"
            self.logger.info(f"Attempt {attempt + 1}:\n{answer}")
            exec_success, feedback = self.execute_modules_with_sandbox(answer) if self.use_sandbox else self.execute_modules(answer)
            self.logger.info(f"Execution result: {exec_success}")
            verification = self._verify_saved_files(answer) if exec_success else ""
            answer = self.remove_blocks(answer)
            if verification:
                answer = answer + "\n" + verification
            self.last_answer = answer
            await asyncio.sleep(0)
            if exec_success:
                self.status_message = "✅ Selesai"
                break
            pretty_print(f"❌ Execution failure:\n{feedback}", color="failure")
            pretty_print("🔧 Auto-debugging...", color="status")
            self.status_message = f"🔧 Auto-debugging... (percobaan {attempt + 1}/{max_attempts})"
            debug_prompt = self._build_debug_prompt(feedback, attempt + 1, max_attempts)
            self.memory.push('user', debug_prompt)
            self.logger.info(f"Debug prompt sent for attempt {attempt + 1}")
            attempt += 1
        self.status_message = "Siap"
        if attempt == max_attempts:
            return "Saya sudah mencoba beberapa kali tapi masih ada kendala. Coba berikan detail lebih lanjut agar saya bisa memperbaikinya.", reasoning
        self.last_answer = answer
        return answer, reasoning

if __name__ == "__main__":
    pass
