from typing import Dict, List, Optional


class CoreMemory:
    """Reads/writes the core_memory section of the learning JSON."""

    MAX_CORE_ITEMS = 30

    def __init__(self, learning_system):
        self.learning_system = learning_system

    def _core(self) -> Dict:
        """Get reference to core_memory section."""
        return self.learning_system.learnings.setdefault("core_memory", {
            "identity": {"name": "", "profession": "", "location": ""},
            "personality": {"tone": "casual", "humor": True, "verbosity": "concise"},
            "preferences": {},
            "active_projects": [],
            "important_facts": [],
            "last_curated": ""
        })

    def _save(self):
        self.learning_system._save_learnings()

    # ==================== Identity ====================

    def set_identity(self, field: str, value: str):
        """Set identity field (name, profession, location)."""
        self._core()["identity"][field] = value
        self._save()

    def get_identity(self) -> Dict:
        return self._core().get("identity", {})

    # ==================== Personality ====================

    def set_personality(self, field: str, value):
        """Set personality field (tone, humor, verbosity, etc.)."""
        self._core()["personality"][field] = value
        self._save()

    def get_personality(self) -> Dict:
        return self._core().get("personality", {})

    # ==================== Preferences ====================

    def add_preference(self, key: str, value: str):
        self._core()["preferences"][key] = value
        self._save()

    def remove_preference(self, key: str):
        self._core()["preferences"].pop(key, None)
        self._save()

    def get_preferences(self) -> Dict:
        return self._core().get("preferences", {})

    # ==================== Active Projects ====================

    def add_project(self, project_desc: str):
        projects = self._core()["active_projects"]
        if project_desc not in projects:
            projects.append(project_desc)
            self._save()

    def remove_project(self, project_desc: str):
        projects = self._core()["active_projects"]
        if project_desc in projects:
            projects.remove(project_desc)
            self._save()

    def get_projects(self) -> List[str]:
        return self._core().get("active_projects", [])

    # ==================== Important Facts (AI-curated) ====================

    def add_custom_fact(self, fact_text: str):
        facts = self._core()["important_facts"]
        if fact_text not in facts:
            facts.append(fact_text)
            self._save()

    def remove_custom_fact(self, fact_text: str):
        facts = self._core()["important_facts"]
        if fact_text in facts:
            facts.remove(fact_text)
            self._save()

    def get_custom_facts(self) -> List[str]:
        return self._core().get("important_facts", [])

    # ==================== Core Prompt Assembly ====================

    def get_total_core_items(self) -> int:
        """Count total items across all core sections."""
        core = self._core()
        count = 0
        identity = core.get("identity", {})
        for v in identity.values():
            if v:
                count += 1
        personality = core.get("personality", {})
        count += len(personality)
        count += len(core.get("preferences", {}))
        count += len(core.get("active_projects", []))
        count += len(core.get("important_facts", []))
        return count

    def get_core_prompt_section(self) -> str:
        """Build the formatted text block injected into every system prompt."""
        core = self._core()
        lines = []

        identity = core.get("identity", {})
        personality = core.get("personality", {})
        preferences = core.get("preferences", {})
        projects = core.get("active_projects", [])
        facts = core.get("important_facts", [])

        # Check if there's anything to show
        has_content = (
            any(identity.values()) or
            preferences or
            projects or
            facts
        )

        if not has_content:
            return ""

        lines.append("=== YOUR CORE MEMORY (Always Available) ===")
        lines.append("")

        # User identity line
        id_parts = []
        if identity.get("name"):
            id_parts.append(identity["name"])
        if identity.get("profession"):
            id_parts.append(identity["profession"])
        if identity.get("location"):
            id_parts.append(f"based in {identity['location']}")
        if id_parts:
            lines.append(f"**User:** {' | '.join(id_parts)}")

        # Personality line
        pers_parts = []
        if personality.get("tone"):
            pers_parts.append(f"{personality['tone']} tone")
        if personality.get("verbosity"):
            pers_parts.append(f"{personality['verbosity']} responses")
        if personality.get("humor"):
            pers_parts.append("enjoys humor")
        if pers_parts:
            lines.append(f"**Personality:** {', '.join(pers_parts)}")

        # Preferences
        if preferences:
            lines.append("**Preferences:**")
            for key, value in preferences.items():
                lines.append(f"  - {key}: {value}")

        # Active projects
        if projects:
            lines.append("**Active Projects:**")
            for proj in projects:
                lines.append(f"  - {proj}")

        # Important facts
        if facts:
            lines.append("**Important:**")
            for fact in facts:
                lines.append(f"  - {fact}")

        return "\n".join(lines)
