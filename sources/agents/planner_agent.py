import json
import re
from typing import List, Tuple, Type, Dict
from sources.utility import pretty_print, animate_thinking
from sources.agents.agent import Agent
from sources.agents.code_agent import CoderAgent
from sources.agents.file_agent import FileAgent
from sources.agents.browser_agent import BrowserAgent
from sources.agents.casual_agent import CasualAgent
from sources.orchestrator import AutonomousOrchestrator
try:
    from sources.text_to_speech import Speech
except ImportError:
    Speech = None
from sources.tools.tools import Tools
from sources.logger import Logger
from sources.memory import Memory

class PlannerAgent(Agent):
    def __init__(self, name, prompt_path, provider, verbose=False, browser=None, ws_manager=None):
        """
        The planner agent is a special agent that divides and conquers the task.
        """
        super().__init__(name, prompt_path, provider, verbose, None)
        self.tools = {
            "json": Tools()
        }
        self.tools['json'].tag = "json"
        self.browser = browser
        self.agents = {
            "coder": CoderAgent(name, "prompts/base/coder_agent.txt", provider, verbose=False),
            "file": FileAgent(name, "prompts/base/file_agent.txt", provider, verbose=False),
            "web": BrowserAgent(name, "prompts/base/browser_agent.txt", provider, verbose=False, browser=browser),
            "casual": CasualAgent(name, "prompts/base/casual_agent.txt", provider, verbose=False)
        }
        self.role = "planification"
        self.type = "planner_agent"
        self.memory = Memory(self.load_prompt(prompt_path),
                                recover_last_session=False,
                                memory_compression=False,
                                model_provider=provider.get_model_name())
        self.logger = Logger("planner_agent.log")
        self.current_plan = []
        self.plan_progress = {}
        self.orchestrator = AutonomousOrchestrator(
            agents=self.agents,
            provider=provider,
            ws_manager=ws_manager
        )
    
    def sanitize_json_text(self, text: str) -> str:
        """
        Clean and sanitize JSON text before parsing.
        Removes trailing commas, fixes common JSON formatting errors.
        Args:
            text (str): Raw JSON text that may contain errors.
        Returns:
            str: Cleaned JSON text.
        """
        text = text.strip()
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        text = re.sub(r'}\s*{', '},{', text)
        text = text.replace("'", '"')
        text = re.sub(r'//[^\n]*', '', text)
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        return text

    def extract_json_from_text(self, text: str) -> str:
        """
        Extract JSON from LLM response text using multiple fallback methods.
        Args:
            text (str): The LLM response text.
        Returns:
            str: Extracted JSON string, or None if no valid JSON found.
        """
        normalized_text = re.sub(r'```json\s*\n', '```json\n', text)
        normalized_text = re.sub(r'```json[ \t]+', '```json\n', normalized_text)
        blocks, _ = self.tools["json"].load_exec_block(normalized_text)
        if blocks:
            for block in blocks:
                sanitized = self.sanitize_json_text(block)
                try:
                    json.loads(sanitized)
                    return sanitized
                except json.JSONDecodeError:
                    pass

        json_marker_pattern = r'```json\s*([\s\S]*?)```'
        matches = re.findall(json_marker_pattern, text, re.IGNORECASE)
        for match in matches:
            sanitized = self.sanitize_json_text(match)
            try:
                json.loads(sanitized)
                return sanitized
            except json.JSONDecodeError:
                pass

        generic_block_pattern = r'```\s*([\s\S]*?)```'
        matches = re.findall(generic_block_pattern, text)
        for match in matches:
            sanitized = self.sanitize_json_text(match)
            try:
                parsed = json.loads(sanitized)
                if isinstance(parsed, dict):
                    return sanitized
            except json.JSONDecodeError:
                pass

        brace_pattern = r'\{[\s\S]*\}'
        matches = re.findall(brace_pattern, text)
        for match in matches:
            sanitized = self.sanitize_json_text(match)
            try:
                parsed = json.loads(sanitized)
                if isinstance(parsed, dict) and 'plan' in parsed:
                    return sanitized
            except json.JSONDecodeError:
                pass

        for match in matches:
            sanitized = self.sanitize_json_text(match)
            try:
                parsed = json.loads(sanitized)
                if isinstance(parsed, dict):
                    return sanitized
            except json.JSONDecodeError:
                pass

        plan_pattern = r'(\{"plan"[\s\S]*\})'
        plan_matches = re.findall(plan_pattern, text)
        for match in plan_matches:
            sanitized = self.sanitize_json_text(match)
            try:
                parsed = json.loads(sanitized)
                if isinstance(parsed, dict) and 'plan' in parsed:
                    return sanitized
            except json.JSONDecodeError:
                pass

        return None

    def get_task_names(self, text: str) -> List[str]:
        """
        Extracts task names from the given text.
        This method processes a multi-line string, where each line may represent a task name.
        containing '##' or starting with a digit. The valid task names are collected and returned.
        Args:
            text (str): A string containing potential task titles (eg: Task 1: I will...).
        Returns:
            List[str]: A list of extracted task names that meet the specified criteria.
        """
        tasks_names = []
        lines = text.strip().split('\n')
        for line in lines:
            if line is None:
                continue
            line = line.strip()
            if len(line) == 0:
                continue
            if '##' in line or line[0].isdigit():
                tasks_names.append(line)
                continue
        self.logger.info(f"Found {len(tasks_names)} tasks names.")
        return tasks_names

    def normalize_agent_name(self, agent_name: str) -> str:
        """
        Normalize agent name by matching it case-insensitively to available agents.
        Also handles common aliases and partial matches.
        """
        name_lower = agent_name.lower().strip()
        agent_aliases = {
            "coder": "coder", "code": "coder", "coding": "coder", "programmer": "coder", "developer": "coder",
            "file": "file", "files": "file", "file agent": "file", "filesystem": "file",
            "web": "web", "browser": "web", "browsing": "web", "search": "web", "internet": "web",
            "casual": "casual", "chat": "casual", "talk": "casual", "conversation": "casual",
        }
        if name_lower in agent_aliases:
            return agent_aliases[name_lower]
        for ag_name in self.agents.keys():
            if ag_name.lower() == name_lower:
                return ag_name
        for ag_name in self.agents.keys():
            if name_lower in ag_name.lower() or ag_name.lower() in name_lower:
                return ag_name
        return None

    def parse_agent_tasks(self, text: str) -> List[Tuple[str, str]]:
        """
        Parses agent tasks from the given LLM text.
        This method extracts task information from a JSON. It identifies task names and their details.
        Args:
            text (str): The input text containing task information in a JSON-like format.
        Returns:
            List[Tuple[str, str]]: A list of tuples containing task names and their details.
        """
        tasks = []
        tasks_names = self.get_task_names(text)

        json_text = self.extract_json_from_text(text)
        if json_text is None:
            return []
        try:
            line_json = json.loads(json_text)
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse extracted JSON.")
            return []

        if 'plan' not in line_json:
            for key in line_json:
                if isinstance(line_json[key], list) and len(line_json[key]) > 0:
                    if isinstance(line_json[key][0], dict) and ('agent' in line_json[key][0] or 'task' in line_json[key][0]):
                        line_json['plan'] = line_json[key]
                        break
            if 'plan' not in line_json:
                return []

        for task in line_json['plan']:
            if not isinstance(task, dict):
                continue
            agent_name = task.get('agent', '')
            normalized_name = self.normalize_agent_name(agent_name)
            if normalized_name is None:
                self.logger.warning(f"Agent {agent_name} does not exist, trying fallback.")
                pretty_print(f"Agent {agent_name} does not exist, using 'coder' as fallback.", color="warning")
                normalized_name = "coder"
            try:
                task_id = task.get('id', '')
                if isinstance(task_id, (int, float)):
                    task_id = str(int(task_id))
                else:
                    task_id = str(task_id)

                agent = {
                    'agent': normalized_name,
                    'id': task_id,
                    'task': task.get('task', task.get('description', ''))
                }
            except Exception:
                self.logger.warning("Missing field in json plan.")
                continue
            self.logger.info(f"Created agent {normalized_name} with task: {agent['task']}")
            if 'need' in task:
                self.logger.info(f"Agent {normalized_name} was given info:\n {task['need']}")
                need = task['need']
                if isinstance(need, list):
                    need = [str(n) for n in need]
                elif not isinstance(need, list):
                    need = [str(need)]
                agent['need'] = need
            else:
                agent['need'] = []
            tasks.append(agent)
        if len(tasks) == 0:
            return []
        names = [task['task'] for task in tasks]
        return list(map(list, zip(names, tasks)))
    
    def make_prompt(self, task: str, agent_infos_dict: dict) -> str:
        """
        Generates a prompt for the agent based on the task and previous agents work information.
        Args:
            task (str): The task to be performed.
            agent_infos_dict (dict): A dictionary containing information from other agents.
        Returns:
            str: The formatted prompt for the agent.
        """
        infos = ""
        if agent_infos_dict is None or len(agent_infos_dict) == 0:
            infos = "No needed informations."
        else:
            for agent_id, info in agent_infos_dict.items():
                infos += f"\t- According to agent {agent_id}:\n{info}\n\n"
        prompt = f"""
        You are given informations from your AI friends work:
        {infos}
        Your task is:
        {task}
        """
        self.logger.info(f"Prompt for agent:\n{prompt}")
        return prompt
    
    def format_plan_text(self, agents_tasks: List[dict]) -> str:
        """
        Format the plan as readable text for display in the chat.
        """
        if not agents_tasks:
            return ""
        lines = ["**Rencana Tugas:**\n"]
        for i, (task_name, task) in enumerate(agents_tasks):
            agent_label = task['agent'].upper()
            lines.append(f"**Langkah {i+1}** [{agent_label}]: {task['task']}")
        return "\n\n".join(lines)

    def show_plan(self, agents_tasks: List[dict], answer: str) -> None:
        """
        Displays the plan made by the agent.
        Args:
            agents_tasks (dict): The tasks assigned to each agent.
            answer (str): The answer from the LLM.
        """
        if agents_tasks == []:
            pretty_print(answer, color="warning")
            pretty_print("Failed to make a plan. This can happen with (too) small LLM. Clarify your request and insist on it making a plan within ```json.", color="failure")
            return
        pretty_print("\n▂▘ P L A N ▝▂", color="status")
        for task_name, task in agents_tasks:
            pretty_print(f"{task['agent']} -> {task['task']}", color="info")
        pretty_print("▔▗ E N D ▖▔", color="status")
        self.current_plan = agents_tasks
        plan_text = self.format_plan_text(agents_tasks)
        self.last_answer = plan_text
        self.last_reasoning = "Tugas kompleks terdeteksi. Membuat rencana multi-langkah."

    def build_planning_prompt(self, user_goal: str) -> str:
        return f"""Tugas pengguna: {user_goal}

PENTING: Kamu HARUS menjawab dengan rencana dalam format JSON yang valid di dalam blok ```json.
Gunakan format PERSIS seperti ini:

```json
{{"plan": [{{"agent": "Coder", "id": "1", "need": [], "task": "deskripsi tugas"}}]}}
```

Agent yang tersedia: "Web", "File", "Coder", "Casual"
Jangan bertanya. Langsung buat rencana sekarang."""

    def try_build_fallback_plan(self, answer: str, original_goal: str) -> list:
        lines = answer.strip().split('\n')
        tasks = []
        step_id = 1
        for line in lines:
            line = line.strip()
            if not line:
                continue
            agent_type = "coder"
            line_lower = line.lower()
            if any(w in line_lower for w in ['cari', 'search', 'browse', 'web', 'internet', 'online']):
                agent_type = "web"
            elif any(w in line_lower for w in ['file', 'buat folder', 'simpan', 'tulis file', 'save']):
                agent_type = "file"
            elif any(w in line_lower for w in ['rangkum', 'simpulkan', 'jelaskan', 'summary', 'casual']):
                agent_type = "casual"
            elif any(w in line_lower for w in ['code', 'kode', 'program', 'script', 'coding', 'buat', 'develop']):
                agent_type = "coder"
            else:
                continue
            if line[0].isdigit() or line.startswith('-') or line.startswith('*') or '##' in line:
                task_text = re.sub(r'^[\d\.\-\*\#\s]+', '', line).strip()
                if len(task_text) > 5:
                    tasks.append([task_text, {
                        'agent': agent_type,
                        'id': str(step_id),
                        'task': task_text,
                        'need': [str(step_id - 1)] if step_id > 1 else []
                    }])
                    step_id += 1
        if not tasks and original_goal:
            tasks = [[original_goal, {
                'agent': 'coder',
                'id': '1',
                'task': original_goal,
                'need': []
            }]]
        return tasks

    async def make_plan(self, prompt: str) -> str:
        max_retries = 5
        retries = 0
        answer = None
        original_goal = prompt
        retry_prompts = [
            'Gagal memparse tugas. Kamu HARUS menjawab dengan JSON plan di dalam blok ```json. Agent tersedia: "Web", "File", "Coder", "Casual". Contoh:\n```json\n{"plan": [{"agent": "Coder", "id": "1", "need": [], "task": "Buat script Python"}]}\n```\nJangan bertanya. Buat rencana sekarang.',
            'Responmu bukan JSON valid. Jawab HANYA dengan format ini:\n```json\n{"plan": [{"agent": "NAMA_AGENT", "id": "NOMOR", "need": [], "task": "DESKRIPSI"}]}\n```\nNama agent harus salah satu dari: Web, File, Coder, Casual.',
            'Saya butuh rencana JSON valid. Jawab HANYA dengan blok ```json berisi {"plan": [...]}. Tanpa teks lain.',
            'Percobaan terakhir. Tulis HANYA JSON valid:\n```json\n{"plan":[{"agent":"Coder","id":"1","need":[],"task":"tugas di sini"}]}\n```',
        ]
        planning_prompt = self.build_planning_prompt(prompt)
        while retries < max_retries:
            animate_thinking("Thinking...", color="status")
            self.memory.push('user', planning_prompt if retries == 0 else retry_prompts[min(retries - 1, len(retry_prompts) - 1)])
            answer, reasoning = await self.llm_request()
            if "NO_UPDATE" in answer:
                return []
            agents_tasks = self.parse_agent_tasks(answer)
            if agents_tasks == []:
                if retries >= 2:
                    fallback = self.try_build_fallback_plan(answer, original_goal)
                    if fallback:
                        pretty_print("Using fallback plan from LLM text.", color="info")
                        self.show_plan(fallback, answer)
                        self.logger.info(f"Fallback plan made:\n{answer}")
                        return fallback
                self.show_plan(agents_tasks, answer)
                pretty_print(f"Failed to make plan. Retrying ({retries + 1}/{max_retries})...", color="warning")
                self.last_answer = f"Membuat rencana... (percobaan {retries + 2}/{max_retries})"
                retries += 1
                continue
            self.show_plan(agents_tasks, answer)
            self.logger.info(f"Plan made:\n{answer}")
            return agents_tasks
        fallback = self.try_build_fallback_plan(answer or "", original_goal)
        if fallback:
            pretty_print("Using final fallback plan.", color="info")
            self.show_plan(fallback, answer or "")
            return fallback
        self.logger.warning(f"Failed to make plan after {max_retries} retries.")
        self.last_answer = "Gagal membuat rencana. Coba perjelas permintaan Anda."
        return []
    
    async def update_plan(self, goal: str, agents_tasks: List[dict], agents_work_result: dict, id: str, success: bool) -> dict:
        """
        Updates the plan with the results of the agents work.
        Args:
            goal (str): The goal to be achieved.
            agents_tasks (list): The tasks assigned to each agent.
            agents_work_result (dict): The results of the agents work.
        Returns:
            dict: The updated plan.
        """
        self.status_message = "Updating plan..."
        last_agent_work = agents_work_result[id]
        tool_success_str = "success" if success else "failure"
        pretty_print(f"Agent {id} work {tool_success_str}.", color="success" if success else "failure")
        try:
            id_int = int(id)
        except Exception as e:
            return agents_tasks
        if id_int == len(agents_tasks):
            next_task = "No task follow, this was the last step. If it failed add a task to recover."
        else:
            next_task = f"Next task is: {agents_tasks[int(id)][0]}."
        update_prompt = f"""
        Your goal is : {goal}
        You previously made a plan, agents are currently working on it.
        The last agent working on task: {id}, did the following work:
        {last_agent_work}
        Agent {id} work was a {tool_success_str} according to system interpreter.
        {next_task}
        Is the work done for task {id} leading to success or failure ? Did an agent fail with a task?
        If agent work was good: answer "NO_UPDATE"
        If agent work is leading to failure: update the plan.
        If a task failed add a task to try again or recover from failure. You might have near identical task twice.
        plan should be within ```json like before.
        You need to rewrite the whole plan, but only change the tasks after task {id}.
        Make the plan the same length as the original one or with only one additional step.
        Do not change past tasks. Change next tasks.
        """
        pretty_print("Updating plan...", color="status")
        plan = await self.make_plan(update_prompt)
        if plan == []:
            pretty_print("No plan update required.", color="info")
            return agents_tasks
        self.logger.info(f"Plan updated:\n{plan}")
        return plan
    
    async def start_agent_process(self, task: dict, required_infos: dict | None) -> str:
        """
        Starts the agent process for a given task.
        Args:
            task (dict): The task to be performed.
            required_infos (dict | None): The required information for the task.
        Returns:
            str: The result of the agent process.
        """
        self.status_message = f"Starting task {task['task']}..."
        agent_prompt = self.make_prompt(task['task'], required_infos)
        pretty_print(f"Agent {task['agent']} started working...", color="status")
        self.logger.info(f"Agent {task['agent']} started working on {task['task']}.")
        answer, reasoning = await self.agents[task['agent'].lower()].process(agent_prompt, None)
        self.last_answer = answer
        self.last_reasoning = reasoning
        self.blocks_result = self.agents[task['agent'].lower()].blocks_result
        agent_answer = self.agents[task['agent'].lower()].raw_answer_blocks(answer)
        success = self.agents[task['agent'].lower()].get_success
        self.agents[task['agent'].lower()].show_answer()
        pretty_print(f"Agent {task['agent']} completed task.", color="status")
        self.logger.info(f"Agent {task['agent']} finished working on {task['task']}. Success: {success}")
        agent_answer += "\nAgent succeeded with task." if success else "\nAgent failed with task (Error detected)."
        return agent_answer, success
    
    def get_work_result_agent(self, task_needs, agents_work_result):
        if task_needs is None:
            return {}
        if isinstance(task_needs, str):
            task_needs = [task_needs]
        task_needs_str = [str(k) for k in task_needs]
        res = {}
        for k in task_needs_str:
            if k in agents_work_result:
                res[k] = agents_work_result[k]
            elif k.isdigit() and int(k) in agents_work_result:
                res[k] = agents_work_result[int(k)]
        self.logger.info(f"Next agent needs: {task_needs}.\n Match previous agent result: {res}")
        return res

    async def process(self, goal: str, speech_module) -> Tuple[str, str]:
        """
        Process the goal using the autonomous orchestrator loop.
        Plan -> Execute -> Observe -> Reflect cycle for full autonomy.
        """
        self.status_message = "Membuat rencana..."
        self.last_answer = "Sedang menganalisis permintaan dan membuat rencana..."
        agents_tasks = await self.make_plan(goal)

        if agents_tasks == []:
            return "Gagal membuat rencana. Coba perjelas permintaan Anda dengan lebih detail.", ""

        plan_text = self.format_plan_text(agents_tasks)
        self.current_plan = agents_tasks
        self.plan_progress = {}

        self.logger.info(f"Starting autonomous orchestrator for: {goal}")
        self.status_message = "Mode otonom aktif..."

        try:
            result = await self.orchestrator.run_loop(goal, agents_tasks, speech_module)
            self.last_answer = result

            if self.orchestrator.plan:
                for step in self.orchestrator.plan.steps:
                    self.plan_progress[str(step.id)] = {
                        "success": step.status == "completed",
                        "answer": step.result or step.error
                    }
                    if hasattr(self.agents.get(step.agent_type.lower(), None), 'blocks_result'):
                        agent = self.agents.get(step.agent_type.lower())
                        if agent and agent.blocks_result:
                            self.blocks_result = agent.blocks_result

            self.status_message = "Selesai"
            return result, "Autonomous orchestrator completed"
        except Exception as e:
            self.logger.error(f"Orchestrator error: {str(e)}")
            self.status_message = f"Error: {str(e)[:100]}"

            pretty_print(f"Orchestrator error, falling back to sequential: {str(e)}", color="warning")
            return await self._fallback_sequential_process(goal, agents_tasks, speech_module)

    async def _fallback_sequential_process(self, goal: str, agents_tasks: list, speech_module) -> Tuple[str, str]:
        """Fallback to sequential execution if orchestrator fails."""
        required_infos = None
        agents_work_result = dict()
        plan_text = self.format_plan_text(agents_tasks)

        i = 0
        steps = len(agents_tasks)
        answer = ""
        while i < steps and not self.stop:
            task_name, task = agents_tasks[i][0], agents_tasks[i][1]
            self.status_message = f"Langkah {i+1}/{steps}: {task['agent']}"
            pretty_print(f"I will {task_name}.", color="info")

            progress_lines = [plan_text, "\n\n---\n"]
            progress_lines.append(f"**Progres:** Mengerjakan langkah {i+1} dari {steps}")
            progress_lines.append(f"\n**Saat ini:** [{task['agent'].upper()}] {task['task']}")
            self.last_answer = "\n".join(progress_lines)

            if agents_work_result is not None:
                required_infos = self.get_work_result_agent(task.get('need', []), agents_work_result)
            try:
                answer, success = await self.start_agent_process(task, required_infos)
            except Exception as e:
                raise e

            self.plan_progress[task['id']] = {"success": success, "answer": answer}
            if self.stop:
                pretty_print(f"Requested stop.", color="failure")
            agents_work_result[task['id']] = answer
            agents_tasks = await self.update_plan(goal, agents_tasks, agents_work_result, task['id'], success)
            steps = len(agents_tasks)
            i += 1

        final_lines = [plan_text, "\n\n---\n"]
        final_lines.append(f"**Semua {steps} langkah selesai.**")
        if answer:
            final_lines.append(f"\n\n**Hasil:**\n{answer}")
        self.last_answer = "\n".join(final_lines)
        return self.last_answer, ""
