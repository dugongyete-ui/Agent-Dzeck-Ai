import os
import json
import time
import datetime
from typing import List, Dict, Optional
from sources.logger import Logger


class PersistentMemory:
    def __init__(self, storage_path: str = "memory_store"):
        self.storage_path = storage_path
        self.logger = Logger("persistent_memory.log")
        os.makedirs(storage_path, exist_ok=True)

        self.facts_file = os.path.join(storage_path, "learned_facts.json")
        self.skills_file = os.path.join(storage_path, "learned_skills.json")
        self.preferences_file = os.path.join(storage_path, "user_preferences.json")
        self.project_history_file = os.path.join(storage_path, "project_history.json")

        self.facts: List[Dict] = self._load_json(self.facts_file, [])
        self.skills: List[Dict] = self._load_json(self.skills_file, [])
        self.preferences: Dict = self._load_json(self.preferences_file, {})
        self.project_history: List[Dict] = self._load_json(self.project_history_file, [])

    def _load_json(self, filepath: str, default):
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load {filepath}: {e}")
        return default

    def _save_json(self, filepath: str, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save {filepath}: {e}")

    def store_fact(self, category: str, content: str, source: str = "conversation"):
        fact = {
            "category": category,
            "content": content,
            "source": source,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        self.facts.append(fact)
        if len(self.facts) > 500:
            self.facts = self.facts[-500:]
        self._save_json(self.facts_file, self.facts)
        self.logger.info(f"Stored fact: {category} - {content[:50]}")

    def store_skill(self, name: str, description: str, code_example: str = "", tags: List[str] = None):
        skill = {
            "name": name,
            "description": description,
            "code_example": code_example[:2000],
            "tags": tags or [],
            "timestamp": datetime.datetime.now().isoformat(),
        }
        existing = [s for s in self.skills if s["name"] != name]
        existing.append(skill)
        self.skills = existing
        self._save_json(self.skills_file, self.skills)
        self.logger.info(f"Stored skill: {name}")

    def store_preference(self, key: str, value: str):
        self.preferences[key] = {
            "value": value,
            "updated_at": datetime.datetime.now().isoformat(),
        }
        self._save_json(self.preferences_file, self.preferences)

    def store_project(self, name: str, project_type: str, path: str, description: str = "", status: str = "created"):
        project = {
            "name": name,
            "type": project_type,
            "path": path,
            "description": description,
            "status": status,
            "created_at": datetime.datetime.now().isoformat(),
        }
        self.project_history.append(project)
        if len(self.project_history) > 100:
            self.project_history = self.project_history[-100:]
        self._save_json(self.project_history_file, self.project_history)

    def search_facts(self, query: str, limit: int = 5) -> List[Dict]:
        query_lower = query.lower()
        scored = []
        for fact in self.facts:
            content_lower = fact["content"].lower()
            score = sum(1 for word in query_lower.split() if word in content_lower)
            if score > 0:
                scored.append((score, fact))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:limit]]

    def search_skills(self, query: str, limit: int = 3) -> List[Dict]:
        query_lower = query.lower()
        results = []
        for skill in self.skills:
            name_lower = skill["name"].lower()
            desc_lower = skill["description"].lower()
            tags_str = " ".join(skill.get("tags", [])).lower()
            if any(w in name_lower or w in desc_lower or w in tags_str for w in query_lower.split()):
                results.append(skill)
        return results[:limit]

    def get_preferences(self) -> Dict:
        return {k: v["value"] for k, v in self.preferences.items()}

    def get_recent_projects(self, limit: int = 5) -> List[Dict]:
        return self.project_history[-limit:]

    def get_context_for_prompt(self, query: str) -> str:
        context_parts = []

        prefs = self.get_preferences()
        if prefs:
            pref_lines = [f"  - {k}: {v}" for k, v in prefs.items()]
            context_parts.append("Preferensi user:\n" + "\n".join(pref_lines))

        relevant_facts = self.search_facts(query, limit=3)
        if relevant_facts:
            fact_lines = [f"  - [{f['category']}] {f['content']}" for f in relevant_facts]
            context_parts.append("Fakta relevan:\n" + "\n".join(fact_lines))

        relevant_skills = self.search_skills(query, limit=2)
        if relevant_skills:
            skill_lines = [f"  - {s['name']}: {s['description']}" for s in relevant_skills]
            context_parts.append("Skill yang dipelajari:\n" + "\n".join(skill_lines))

        recent_projects = self.get_recent_projects(3)
        if recent_projects:
            proj_lines = [f"  - {p['name']} ({p['type']}) di {p['path']}" for p in recent_projects]
            context_parts.append("Project terakhir:\n" + "\n".join(proj_lines))

        if context_parts:
            return "\n\n[LONG-TERM MEMORY]\n" + "\n\n".join(context_parts) + "\n[/LONG-TERM MEMORY]\n"
        return ""

    def extract_and_store_from_conversation(self, user_query: str, agent_response: str):
        query_lower = user_query.lower()

        if any(kw in query_lower for kw in ['suka', 'prefer', 'selalu', 'gunakan', 'pakai']):
            self.store_fact("preference", f"User: {user_query[:200]}", "conversation")

        code_keywords = ['buatkan', 'buat', 'create', 'build', 'website', 'app', 'program']
        if any(kw in query_lower for kw in code_keywords):
            self.store_fact("request", f"User meminta: {user_query[:200]}", "conversation")

        if 'berhasil' in agent_response.lower() or '[success]' in agent_response.lower():
            self.store_fact("success", f"Berhasil: {user_query[:100]}", "execution")
