import asyncio
import re
import time
import json
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from sources.logger import Logger
from sources.utility import pretty_print, animate_thinking
from sources.persistent_memory import PersistentMemory


@dataclass
class TaskStep:
    id: int
    description: str
    agent_type: str
    status: str = "pending"
    result: str = ""
    error: str = ""
    attempts: int = 0
    max_attempts: int = 3
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    goal: str
    steps: List[TaskStep] = field(default_factory=list)
    current_step: int = 0
    completed: bool = False
    reflection_log: List[str] = field(default_factory=list)
    start_time: float = 0.0

    def get_next_step(self) -> Optional[TaskStep]:
        for step in self.steps:
            if step.status == "pending":
                deps_met = True
                for dep_id in step.dependencies:
                    dep_step = next((s for s in self.steps if str(s.id) == str(dep_id)), None)
                    if dep_step and dep_step.status != "completed":
                        deps_met = False
                        break
                if deps_met:
                    return step
        return None

    def mark_step_done(self, step_id: int, result: str):
        for step in self.steps:
            if step.id == step_id:
                step.status = "completed"
                step.result = result
                return

    def mark_step_failed(self, step_id: int, error: str):
        for step in self.steps:
            if step.id == step_id:
                step.attempts += 1
                if step.attempts >= step.max_attempts:
                    step.status = "failed"
                else:
                    step.status = "pending"
                step.error = error
                return

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "failed") for s in self.steps)

    def get_progress_text(self) -> str:
        lines = [f"**Rencana: {self.goal}**\n"]
        for step in self.steps:
            icon = {"pending": "...", "completed": "[OK]", "failed": "[X]", "running": "[~]"}.get(step.status, "...")
            lines.append(f"{icon} Langkah {step.id}: [{step.agent_type.upper()}] {step.description} ({step.status})")
        elapsed = time.time() - self.start_time if self.start_time else 0
        if elapsed > 0:
            lines.append(f"\nWaktu: {elapsed:.1f}s")
        return "\n".join(lines)

    def get_progress_data(self) -> List[Dict]:
        return [
            {
                "id": step.id,
                "description": step.description,
                "agent_type": step.agent_type,
                "status": step.status,
                "attempts": step.attempts,
            }
            for step in self.steps
        ]

    def get_success_rate(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == "completed")
        return completed / len(self.steps)


class AutonomousOrchestrator:
    def __init__(self, agents: dict, provider, ws_manager=None):
        self.agents = agents
        self.provider = provider
        self.logger = Logger("orchestrator.log")
        self.plan: Optional[ExecutionPlan] = None
        self.execution_memory: List[Dict] = []
        self.status_message = "Idle"
        self.last_answer = ""
        self.ws_manager = ws_manager
        self.persistent_memory = PersistentMemory()
        self._setup_multi_tool()

    def _setup_multi_tool(self):
        if "coder" in self.agents and "web" in self.agents:
            coder = self.agents["coder"]
            browser = self.agents["web"]
            if hasattr(coder, 'set_browser_agent'):
                coder.set_browser_agent(browser)
                self.logger.info("Multi-tool: CoderAgent linked to BrowserAgent")
            if hasattr(coder, 'ws_manager') and self.ws_manager:
                coder.ws_manager = self.ws_manager

    async def _notify_status(self, agent_name: str, status: str, progress: float = 0.0, details: str = ""):
        if self.ws_manager:
            try:
                await self.ws_manager.send_status(agent_name, status, progress, details)
            except Exception:
                pass

    async def _notify_plan(self, current_step: int = 0):
        if self.ws_manager and self.plan:
            try:
                await self.ws_manager.send_plan_update(self.plan.get_progress_data(), current_step)
            except Exception:
                pass

    async def _send_peor(self, phase: str, step_id: int = 0, details: str = ""):
        if self.ws_manager:
            try:
                await self.ws_manager.send_peor_update(phase, step_id, details)
            except Exception:
                pass

    async def _send_progress(self, current_step_id: int = 0, current_step_description: str = ""):
        if self.ws_manager and self.plan:
            try:
                elapsed = time.time() - self.plan.start_time if self.plan.start_time else 0.0
                completed = sum(1 for s in self.plan.steps if s.status == "completed")
                failed = sum(1 for s in self.plan.steps if s.status == "failed")
                total = len(self.plan.steps)
                success_rate = self.plan.get_success_rate()
                estimated_remaining = 0.0
                if completed > 0 and elapsed > 0:
                    avg_per_step = elapsed / completed
                    remaining_steps = total - completed - failed
                    estimated_remaining = avg_per_step * remaining_steps
                await self.ws_manager.send_plan_progress(
                    total_steps=total,
                    completed_steps=completed,
                    failed_steps=failed,
                    current_step_id=current_step_id,
                    current_step_description=current_step_description,
                    elapsed_time=elapsed,
                    estimated_remaining=estimated_remaining,
                    success_rate=success_rate,
                )
            except Exception:
                pass

    def create_plan_from_tasks(self, goal: str, agent_tasks: list) -> ExecutionPlan:
        plan = ExecutionPlan(goal=goal, start_time=time.time())
        for i, (task_name, task_info) in enumerate(agent_tasks):
            deps = task_info.get('need', [])
            if isinstance(deps, str):
                deps = [deps] if deps else []
            step = TaskStep(
                id=i + 1,
                description=task_info.get('task', task_name),
                agent_type=task_info.get('agent', 'coder'),
                dependencies=deps,
            )
            plan.steps.append(step)
        self.plan = plan
        self.logger.info(f"Plan created with {len(plan.steps)} steps for: {goal}")
        return plan

    async def _coder_browse_for_install(self, package_name: str, error_text: str) -> str:
        if "web" not in self.agents:
            return ""
        browser_agent = self.agents["web"]
        try:
            self.logger.info(f"Multi-tool: Browsing install guide for '{package_name}'")
            pretty_print(f"🌐 Multi-Tool: Browsing cara install '{package_name}'...", color="status")

            if self.ws_manager:
                try:
                    await self.ws_manager.broadcast({
                        "type": "multi_tool",
                        "action": "auto_browse_install",
                        "details": f"CoderAgent gagal install '{package_name}', BrowserAgent mencari solusi...",
                        "agent": "orchestrator",
                    })
                except Exception:
                    pass

            search_query = f"install {package_name} python pip Linux Ubuntu error fix"
            answer, _ = await browser_agent.process(search_query, None)

            if answer:
                self.logger.info(f"Browser found install solution: {answer[:200]}")
                return answer[:1500]
        except Exception as e:
            self.logger.error(f"Browse for install failed: {str(e)}")
        return ""

    async def _handle_install_failure_with_browsing(self, step: TaskStep, error_text: str) -> Optional[str]:
        error_lower = error_text.lower()
        if "no module named" not in error_lower and "pip install" not in error_lower and "modulenotfounderror" not in error_lower:
            return None

        module_match = re.search(r"No module named ['\"]?(\w+)", error_text, re.IGNORECASE)
        if not module_match:
            module_match = re.search(r"pip install (\w[\w\-]*)", error_text, re.IGNORECASE)
        if not module_match:
            return None

        package_name = module_match.group(1)
        self.logger.info(f"Detected install failure for: {package_name}")

        browse_result = await self._coder_browse_for_install(package_name, error_text)
        if not browse_result:
            return None

        install_commands = []
        pip_patterns = re.findall(r'pip3?\s+install\s+[\w\-\.\[\]>=<]+(?:\s+[\w\-\.\[\]>=<]+)*', browse_result)
        apt_patterns = re.findall(r'(?:sudo\s+)?apt(?:-get)?\s+install\s+[\w\-]+(?:\s+[\w\-]+)*', browse_result)
        install_commands.extend(pip_patterns)
        install_commands.extend(apt_patterns)

        if install_commands:
            retry_prompt = (
                f"Berdasarkan pencarian web, berikut cara install '{package_name}':\n"
                f"Perintah yang ditemukan:\n"
            )
            for cmd in install_commands[:5]:
                retry_prompt += f"  - {cmd}\n"
            retry_prompt += (
                f"\nInfo lengkap dari web:\n{browse_result[:800]}\n\n"
                f"Coba install menggunakan perintah di atas, lalu ulangi tugas asli:\n"
                f"{step.description}"
            )
            return retry_prompt

        return (
            f"Info dari web tentang '{package_name}':\n{browse_result[:800]}\n\n"
            f"Gunakan informasi ini untuk memperbaiki instalasi, lalu ulangi tugas:\n"
            f"{step.description}"
        )

    async def execute_step(self, step: TaskStep, required_infos: dict = None) -> Tuple[str, bool]:
        step.status = "running"
        agent_key = step.agent_type.lower()
        if agent_key not in self.agents:
            for key in self.agents:
                if key.startswith(agent_key[:3]):
                    agent_key = key
                    break
            else:
                agent_key = "coder"

        agent = self.agents[agent_key]
        prompt = step.description

        rich_context = self._gather_rich_context()

        if required_infos:
            context_parts = []
            for k, v in required_infos.items():
                context_parts.append(f"- Hasil langkah {k}: {v}")
            prompt = (
                f"Konteks dari langkah sebelumnya:\n"
                f"{''.join(context_parts)}\n\n"
                f"Tugas kamu sekarang:\n{step.description}\n\n"
                f"INSTRUKSI: Langsung kerjakan tanpa bertanya. Gunakan informasi dari langkah sebelumnya."
            )

        if rich_context:
            prompt = f"{rich_context}\n\n{prompt}"

        if step.error and step.attempts > 0:
            prompt += (
                f"\n\nPERINGATAN: Percobaan sebelumnya GAGAL dengan error:\n{step.error[:500]}\n"
                f"Gunakan PENDEKATAN BERBEDA kali ini. Jangan ulangi cara yang sama."
            )

        memory_context = self.persistent_memory.get_context_for_prompt(step.description)
        if memory_context:
            prompt += f"\n{memory_context}"

        self.logger.info(f"Executing step {step.id}: {step.description} with agent {agent_key}")
        self.status_message = f"Langkah {step.id}: {step.description}"

        if self.ws_manager:
            try:
                await self.ws_manager.send_agent_thinking(agent_key, f"Processing step {step.id}: {step.description[:100]}")
            except Exception:
                pass

        total_steps = len(self.plan.steps) if self.plan else 1
        await self._notify_status("orchestrator", f"Langkah {step.id}/{total_steps}",
                                   step.id / total_steps, step.description[:100])

        try:
            answer, reasoning = await agent.process(prompt, None)
            success = agent.get_success

            self.execution_memory.append({
                "step_id": step.id,
                "agent": agent_key,
                "success": success,
                "answer_preview": (answer or "")[:200],
                "timestamp": time.time(),
            })

            if not success and agent_key == "coder":
                browse_fix = await self._handle_install_failure_with_browsing(step, answer or "")
                if browse_fix:
                    self.logger.info("Retrying step with browser-assisted install info")
                    pretty_print("🔄 Mencoba ulang dengan info dari browser...", color="status")

                    if self.ws_manager:
                        try:
                            await self.ws_manager.broadcast({
                                "type": "multi_tool",
                                "action": "retry_with_browser_info",
                                "details": f"Langkah {step.id} dicoba ulang dengan info instalasi dari web",
                                "agent": "orchestrator",
                            })
                        except Exception:
                            pass

                    answer, reasoning = await agent.process(browse_fix, None)
                    success = agent.get_success

                    self.execution_memory.append({
                        "step_id": step.id,
                        "agent": agent_key,
                        "success": success,
                        "answer_preview": (answer or "")[:200],
                        "timestamp": time.time(),
                        "retry_with_browse": True,
                    })

            if success:
                self.persistent_memory.store_fact(
                    "execution_success",
                    f"Langkah '{step.description[:100]}' berhasil dengan agent {agent_key}",
                    "orchestrator"
                )

            return answer, success
        except Exception as e:
            self.logger.error(f"Step {step.id} error: {str(e)}")
            return f"Error: {str(e)}", False

    def reflect(self, step: TaskStep, result: str, success: bool) -> str:
        reflection = ""
        if success:
            reflection = f"Langkah {step.id} berhasil: {step.description}"
            step.status = "completed"
            step.result = result
        else:
            step.attempts += 1
            if step.attempts >= step.max_attempts:
                reflection = f"Langkah {step.id} gagal setelah {step.max_attempts} percobaan: {step.description}"
                step.status = "failed"
                step.error = result
            else:
                reflection = f"Langkah {step.id} gagal (percobaan {step.attempts}/{step.max_attempts}), akan dicoba lagi"
                step.status = "pending"
                step.error = result

        if self.plan:
            self.plan.reflection_log.append(reflection)
        self.logger.info(f"Reflection: {reflection}")

        if self.ws_manager:
            try:
                log_level = "success" if success else "error"
                asyncio.get_event_loop().create_task(
                    self.ws_manager.send_execution_log(log_level, reflection, step.agent_type)
                )
            except Exception:
                pass

        return reflection

    def revise_plan(self, failed_step: TaskStep) -> None:
        if not self.plan:
            return

        error_lower = (failed_step.error or "").lower()
        recovery_agent = failed_step.agent_type.lower()
        recovery_description = ""

        if "no module named" in error_lower or "import" in error_lower:
            module_match = re.search(r"no module named ['\"]?(\w+)", error_lower)
            module_name = module_match.group(1) if module_match else "yang dibutuhkan"

            recovery_agent = "web"
            browse_step = TaskStep(
                id=len(self.plan.steps) + 1,
                description=(
                    f"[MULTI-TOOL BROWSE] Cari cara install library '{module_name}' di Linux/Ubuntu. "
                    f"Cari di web: 'how to install {module_name} python pip Linux'. "
                    f"Catat perintah install yang benar."
                ),
                agent_type="web",
                max_attempts=2,
                dependencies=failed_step.dependencies,
            )
            self.plan.steps.append(browse_step)
            self.logger.info(f"Multi-tool: Added browse step {browse_step.id} to find install for '{module_name}'")

            recovery_agent = "coder"
            recovery_description = (
                f"[RECOVERY - INSTALL DEPENDENCY WITH BROWSER INFO] "
                f"Gunakan informasi dari langkah browsing sebelumnya untuk install '{module_name}'. "
                f"Lalu ulangi tugas asli: {failed_step.description}"
            )

            retry_step = TaskStep(
                id=len(self.plan.steps) + 1,
                description=recovery_description,
                agent_type=recovery_agent,
                max_attempts=2,
                dependencies=[str(browse_step.id)],
            )

            retry_step.id = len(self.plan.steps) + 1

            recovery_description += (
                f"\n\nERROR SEBELUMNYA:\n{(failed_step.error or 'Unknown error')[:500]}\n"
                f"INSTRUKSI: Gunakan pendekatan BERBEDA. Jangan ulangi cara yang sama. "
                f"Kamu dilarang meminta klarifikasi, langsung eksekusi."
            )
            retry_step.description = recovery_description
            self.plan.steps.append(retry_step)
            self.logger.info(f"Plan revised: browse step {browse_step.id} + retry step {retry_step.id} for failed step {failed_step.id}")
            return

        elif "permission" in error_lower or "access denied" in error_lower:
            recovery_agent = "file"
            recovery_description = (
                f"[RECOVERY - FIX PERMISSIONS] "
                f"Perbaiki permission/akses file yang bermasalah, "
                f"lalu ulangi tugas: {failed_step.description}"
            )
        elif "syntax" in error_lower or "syntaxerror" in error_lower:
            recovery_agent = "coder"
            recovery_description = (
                f"[RECOVERY - FIX SYNTAX] "
                f"Perbaiki syntax error dalam kode. "
                f"Baca file yang bermasalah, identifikasi error syntax, dan perbaiki. "
                f"Tugas asli: {failed_step.description}"
            )
        elif "timeout" in error_lower or "connection" in error_lower:
            recovery_agent = "web"
            recovery_description = (
                f"[RECOVERY - RETRY CONNECTION] "
                f"Coba lagi dengan query pencarian berbeda atau URL alternatif. "
                f"Tugas asli: {failed_step.description}"
            )
        else:
            alternative_agents = {
                "coder": "file",
                "file": "coder",
                "web": "casual",
                "casual": "coder",
            }
            recovery_agent = alternative_agents.get(failed_step.agent_type.lower(), failed_step.agent_type)
            recovery_description = (
                f"[RECOVERY] Coba lagi dengan pendekatan berbeda: {failed_step.description}"
            )

        recovery_description += (
            f"\n\nERROR SEBELUMNYA:\n{(failed_step.error or 'Unknown error')[:500]}\n"
            f"INSTRUKSI: Gunakan pendekatan BERBEDA. Jangan ulangi cara yang sama. "
            f"Kamu dilarang meminta klarifikasi, langsung eksekusi."
        )

        retry_step = TaskStep(
            id=len(self.plan.steps) + 1,
            description=recovery_description,
            agent_type=recovery_agent,
            max_attempts=2,
            dependencies=failed_step.dependencies,
        )
        self.plan.steps.append(retry_step)
        self.logger.info(f"Plan revised: recovery step {retry_step.id} (agent: {recovery_agent}) for failed step {failed_step.id}")

    def _gather_rich_context(self) -> str:
        if not self.plan:
            return ""

        context_parts = []
        files_created = []
        urls_found = []

        for step in self.plan.steps:
            if step.status != "completed" or not step.result:
                continue

            context_parts.append(
                f"- Langkah {step.id} [{step.agent_type.upper()}]: {step.description[:100]}\n"
                f"  Hasil: {step.result[:300]}"
            )

            file_patterns = re.findall(
                r'(?:/home/runner/workspace/[^\s\'"]+|\.\/[^\s\'"]+|work(?:_dir)?/[^\s\'"]+)',
                step.result
            )
            files_created.extend(file_patterns)

            url_patterns = re.findall(r'https?://[^\s\'"<>]+', step.result)
            urls_found.extend(url_patterns)

        if not context_parts:
            return ""

        rich_context = "=== KONTEKS PROYEK ===\n"
        rich_context += "\n".join(context_parts)

        if files_created:
            unique_files = list(dict.fromkeys(files_created))
            rich_context += "\n\n--- File yang sudah dibuat ---\n"
            rich_context += "\n".join(f"  • {f}" for f in unique_files[:20])

        if urls_found:
            unique_urls = list(dict.fromkeys(urls_found))
            rich_context += "\n\n--- URL/Resource yang ditemukan ---\n"
            rich_context += "\n".join(f"  • {u}" for u in unique_urls[:10])

        rich_context += "\n=== END KONTEKS ===\n"
        return rich_context

    def get_execution_summary(self) -> Dict:
        if not self.plan:
            return {}

        completed = sum(1 for s in self.plan.steps if s.status == "completed")
        failed = sum(1 for s in self.plan.steps if s.status == "failed")
        skipped = sum(1 for s in self.plan.steps if s.status == "pending")
        total = len(self.plan.steps)
        elapsed = time.time() - self.plan.start_time if self.plan.start_time else 0.0

        files_created = []
        for step in self.plan.steps:
            if step.status == "completed" and step.result:
                file_patterns = re.findall(
                    r'(?:/home/runner/workspace/[^\s\'"]+|\.\/[^\s\'"]+|work(?:_dir)?/[^\s\'"]+)',
                    step.result
                )
                files_created.extend(file_patterns)

        return {
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "elapsed_time": round(elapsed, 2),
            "success_rate": round(completed / total, 2) if total > 0 else 0.0,
            "reflection_log": list(self.plan.reflection_log[-10:]),
            "files_created": list(dict.fromkeys(files_created)),
        }

    async def _visual_verification(self, goal: str, work_results: dict) -> Optional[str]:
        goal_lower = goal.lower()
        is_website_task = any(kw in goal_lower for kw in [
            'website', 'web', 'html', 'landing', 'page', 'dashboard',
            'portfolio', 'blog', 'toko', 'shop', 'e-commerce', 'frontend',
            'halaman', 'situs', 'tampilan',
        ])
        if not is_website_task:
            return None

        if "web" not in self.agents:
            self.logger.info("Visual verification skipped: no browser agent available")
            return None

        html_files = []
        work_dir = "/home/runner/workspace/work"
        if os.path.exists(work_dir):
            for root, dirs, files in os.walk(work_dir):
                for f in files:
                    if f.endswith('.html'):
                        html_files.append(os.path.join(root, f))

        if not html_files:
            self.logger.info("Visual verification skipped: no HTML files found")
            return None

        main_html = None
        for f in html_files:
            fname = os.path.basename(f).lower()
            if fname == 'index.html':
                main_html = f
                break
        if not main_html:
            main_html = html_files[0]

        self.logger.info(f"Visual verification: checking {main_html}")
        pretty_print(f"🔍 Visual Verification: memeriksa {os.path.basename(main_html)}...", color="status")

        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "visual_verification",
                    "phase": "starting",
                    "file": main_html,
                    "details": "Memulai verifikasi visual website...",
                })
            except Exception:
                pass

        screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        screenshot_taken = False
        screenshot_path = os.path.join(screenshots_dir, f"visual_check_{int(time.time())}.png")

        browser_agent = self.agents["web"]
        if hasattr(browser_agent, 'browser') and browser_agent.browser:
            try:
                preview_url = f"file://{main_html}"
                browser_agent.browser.go_to(preview_url)
                await asyncio.sleep(2)
                screenshot_taken = browser_agent.browser.screenshot(
                    filename=os.path.basename(screenshot_path)
                )
                if screenshot_taken:
                    src = os.path.join(browser_agent.browser.screenshot_folder if hasattr(browser_agent.browser, 'screenshot_folder') else '.', os.path.basename(screenshot_path))
                    if os.path.exists(src) and src != screenshot_path:
                        import shutil
                        shutil.move(src, screenshot_path)
                    self.logger.info(f"Screenshot saved: {screenshot_path}")
            except Exception as e:
                self.logger.error(f"Screenshot failed: {str(e)}")
                screenshot_taken = False

        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "visual_verification",
                    "phase": "screenshot_taken" if screenshot_taken else "screenshot_failed",
                    "file": screenshot_path if screenshot_taken else "",
                    "details": "Screenshot berhasil diambil" if screenshot_taken else "Gagal mengambil screenshot",
                })
            except Exception:
                pass

        with open(main_html, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()

        visual_issues = []

        if '<meta name="viewport"' not in html_content:
            visual_issues.append("Tidak ada meta viewport (tidak responsive)")
        if 'style' not in html_content and '<link' not in html_content:
            visual_issues.append("Tidak ada CSS styling")
        if 'position: absolute' in html_content or 'position:absolute' in html_content:
            abs_count = html_content.count('position: absolute') + html_content.count('position:absolute')
            if abs_count > 5:
                visual_issues.append(f"Terlalu banyak position:absolute ({abs_count}x) - risiko elemen tumpang tindih")
        if 'z-index' in html_content:
            import re as _re
            z_indices = _re.findall(r'z-index:\s*(\d+)', html_content)
            if z_indices:
                max_z = max(int(z) for z in z_indices)
                if max_z > 100:
                    visual_issues.append(f"z-index sangat tinggi ({max_z}) - risiko layering bermasalah")
        if len(html_content) < 500:
            visual_issues.append("File HTML sangat pendek - mungkin belum lengkap")
        if '</html>' not in html_content:
            visual_issues.append("Tag </html> penutup tidak ditemukan")
        if '</body>' not in html_content:
            visual_issues.append("Tag </body> penutup tidak ditemukan")

        has_modern = any(kw in html_content.lower() for kw in [
            'flexbox', 'flex', 'grid', 'gradient', 'border-radius',
            'box-shadow', 'transition', 'transform', 'animation',
            'rgba', 'var(--', 'media', '@keyframes',
        ])
        if not has_modern:
            visual_issues.append("Tidak terdeteksi CSS modern (flexbox/grid/shadow/gradient)")

        vision_analysis = ""
        if screenshot_taken and os.path.exists(screenshot_path):
            try:
                vision_prompt = (
                    "Analisis screenshot website ini:\n"
                    "1. Apakah desainnya modern dan profesional?\n"
                    "2. Apakah ada elemen yang tumpang tindih atau tidak rapi?\n"
                    "3. Apakah tata letak (layout) sudah baik?\n"
                    "4. Apakah ada masalah visual yang perlu diperbaiki?\n"
                    "Berikan jawaban singkat dalam bahasa Indonesia."
                )
                if hasattr(self.provider, 'respond_with_image'):
                    vision_analysis = self.provider.respond_with_image(
                        vision_prompt, screenshot_path
                    )
                elif hasattr(self.provider, 'respond'):
                    vision_analysis = (
                        "Model vision tidak tersedia. Analisis berdasarkan kode HTML saja."
                    )
            except Exception as e:
                self.logger.error(f"Vision analysis failed: {str(e)}")
                vision_analysis = f"Analisis vision gagal: {str(e)}"

        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "visual_verification",
                    "phase": "analysis_complete",
                    "issues": visual_issues,
                    "vision_analysis": vision_analysis[:500] if vision_analysis else "",
                    "screenshot": screenshot_path if screenshot_taken else "",
                    "has_modern_css": has_modern,
                })
            except Exception:
                pass

        if visual_issues:
            fix_prompt = (
                f"🔍 VISUAL VERIFICATION - PERBAIKAN DIPERLUKAN\n\n"
                f"File yang diperiksa: {main_html}\n\n"
                f"Masalah visual yang ditemukan:\n"
            )
            for i, issue in enumerate(visual_issues, 1):
                fix_prompt += f"  {i}. {issue}\n"

            if vision_analysis:
                fix_prompt += f"\nAnalisis visual AI:\n{vision_analysis[:500]}\n"

            fix_prompt += (
                f"\nINSTRUKSI:\n"
                f"1. Perbaiki SEMUA masalah visual di atas\n"
                f"2. Pastikan desain MODERN (gunakan flexbox/grid, shadow, gradient, border-radius)\n"
                f"3. Pastikan RESPONSIVE (meta viewport + media queries)\n"
                f"4. Pastikan TIDAK ADA elemen yang tumpang tindih\n"
                f"5. Tulis ulang file HTML yang sudah diperbaiki secara LENGKAP"
            )

            self.logger.info(f"Visual verification found {len(visual_issues)} issues, requesting fix")
            return fix_prompt

        self.logger.info("Visual verification passed - no issues found")
        pretty_print("✅ Visual Verification: desain terlihat baik!", color="success")

        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "visual_verification",
                    "phase": "passed",
                    "details": "Verifikasi visual berhasil - tidak ada masalah ditemukan",
                })
            except Exception:
                pass

        return None

    async def run_loop(self, goal: str, agent_tasks: list, speech_module=None) -> str:
        plan = self.create_plan_from_tasks(goal, agent_tasks)
        work_results = {}
        final_answer = ""

        pretty_print(f"\n>> AUTONOMOUS MODE: {len(plan.steps)} langkah", color="status")
        pretty_print(plan.get_progress_text(), color="info")

        await self._notify_status("orchestrator", "Memulai eksekusi otonom", 0.0, f"{len(plan.steps)} langkah")
        await self._notify_plan(0)
        await self._send_peor("plan", 0, f"Planning {len(plan.steps)} steps for: {goal}")

        max_iterations = len(plan.steps) * 4
        iteration = 0
        consecutive_failures = 0

        while not plan.is_complete() and iteration < max_iterations:
            step = plan.get_next_step()
            if step is None:
                has_pending = any(s.status == "pending" for s in plan.steps)
                if has_pending:
                    self.logger.warning("Dependency deadlock detected - marking blocked steps as failed")
                    for s in plan.steps:
                        if s.status == "pending":
                            s.status = "failed"
                            s.error = "Dependency deadlock: langkah yang dibutuhkan gagal"
                break

            iteration += 1
            pretty_print(f"\n>> Langkah {step.id}/{len(plan.steps)}: {step.description}", color="status")
            self.last_answer = plan.get_progress_text()
            await self._notify_plan(step.id)

            required_infos = {}
            for prev_step in plan.steps:
                if str(prev_step.id) in step.dependencies and prev_step.status == "completed":
                    required_infos[str(prev_step.id)] = prev_step.result[:500] if prev_step.result else ""

            if not required_infos:
                for prev_step in plan.steps:
                    if prev_step.id < step.id and prev_step.status == "completed":
                        required_infos[str(prev_step.id)] = prev_step.result[:300] if prev_step.result else ""

            await self._send_peor("execute", step.id, step.description)
            result, success = await self.execute_step(step, required_infos if required_infos else None)

            await self._send_peor("observe", step.id, f"Success: {success}")
            await self._send_peor("reflect", step.id, "Analyzing result")
            reflection = self.reflect(step, result, success)
            pretty_print(f">> {reflection}", color="info" if success else "warning")

            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1

            if not success and step.status == "failed":
                if consecutive_failures < 3:
                    await self._send_peor("revise", step.id, "Revising plan after failure")
                    self.revise_plan(step)
                else:
                    self.logger.warning(f"Too many consecutive failures ({consecutive_failures}), skipping recovery")

            work_results[str(step.id)] = result
            if success:
                final_answer = result

            self.last_answer = plan.get_progress_text()
            await self._notify_plan(step.id)
            await self._send_progress(step.id, step.description)

        visual_fix_prompt = await self._visual_verification(goal, work_results)
        if visual_fix_prompt and "coder" in self.agents:
            pretty_print("🎨 Memperbaiki masalah visual...", color="status")

            if self.ws_manager:
                try:
                    await self.ws_manager.broadcast({
                        "type": "visual_verification",
                        "phase": "fixing",
                        "details": "CoderAgent memperbaiki masalah visual...",
                    })
                except Exception:
                    pass

            coder = self.agents["coder"]
            fix_answer, _ = await coder.process(visual_fix_prompt, None)
            if coder.get_success:
                pretty_print("✅ Perbaikan visual berhasil!", color="success")
                final_answer = fix_answer
            else:
                pretty_print("⚠️ Perbaikan visual gagal, menggunakan hasil sebelumnya", color="warning")

        completed = sum(1 for s in plan.steps if s.status == "completed")
        total = len(plan.steps)
        elapsed = time.time() - plan.start_time

        pretty_print(f"\n>> Selesai: {completed}/{total} langkah berhasil ({elapsed:.1f}s)", color="success" if completed == total else "warning")

        await self._notify_status("orchestrator", f"Selesai: {completed}/{total}", 1.0,
                                   f"Waktu: {elapsed:.1f}s")

        self.persistent_memory.store_project(
            name=goal[:100],
            project_type="autonomous",
            path="",
            description=f"{completed}/{total} langkah berhasil",
            status="completed" if completed == total else "partial"
        )

        summary_lines = [plan.get_progress_text(), "\n---\n"]
        summary_lines.append(f"**Hasil:** {completed}/{total} langkah selesai dalam {elapsed:.1f} detik")

        if plan.reflection_log:
            summary_lines.append("\n**Log refleksi:**")
            for log_entry in plan.reflection_log[-5:]:
                summary_lines.append(f"  - {log_entry}")

        if final_answer:
            summary_lines.append(f"\n\n**Hasil akhir:**\n{final_answer}")

        self.last_answer = "\n".join(summary_lines)
        return self.last_answer
