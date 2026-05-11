from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

from learning_system import LearningSystem
from utils import categorize_error


@dataclass
class CommandFix:
    """Represents a successful command fix"""
    original_command: str
    fixed_command: str
    error_type: str
    context: str
    timestamp: str
    use_count: int = 1


class MemoryManager:
    """
    Clean interface to learning system.

    WHY THIS EXISTS:
    - LearningSystem stores JSON in files
    - MemoryManager provides typed Python objects
    - Makes it easier to work with memory in code
    - Separates storage (LearningSystem) from business logic (MemoryManager)
    """

    def __init__(self):
        self.learning_system = LearningSystem()
        self._fact_counter = 0
        self._rule_counter = 0
        self._rel_counter = 0
        self._ltm_counter = 0
        self._init_counters()

    def _init_counters(self):
        """Initialize counters from existing data to prevent ID collisions."""
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        max_fact = 0
        for f in facts:
            fid = f.get("id", "")
            if fid.startswith("fact_"):
                try:
                    num = int(fid.split("_")[1])
                    max_fact = max(max_fact, num)
                except (ValueError, IndexError):
                    pass
        self._fact_counter = max_fact

        ltm = self.learning_system.learnings.get("conversation_memory", {}).get("long_term_memory", [])
        max_ltm = 0
        for m in ltm:
            mid = m.get("id", "")
            if mid.startswith("ltm_"):
                try:
                    num = int(mid.split("_")[1])
                    max_ltm = max(max_ltm, num)
                except (ValueError, IndexError):
                    pass
        self._ltm_counter = max_ltm

    # ==================== App Memory ====================

    def remember_app(
        self,
        app_name: str,
        launch_path: Optional[str] = None,
        strategy: Optional[str] = None,
        process_name: Optional[str] = None
    ):
        """Remember how to launch and close an app"""
        self.learning_system.learn_app(
            app_name=app_name,
            path=launch_path,
            strategy=strategy,
            process_name=process_name
        )

    def get_app_info(self, app_name: str) -> Optional[Dict]:
        """Get remembered info about an app"""
        return self.learning_system.get_app_info(app_name)

    # ==================== Fix Memory ====================

    def record_fix(
        self,
        original_command: str,
        fixed_command: str,
        error: str,
        context: str = ""
    ):
        """Record a successful command fix"""
        self.learning_system.record_command_fix(
            original=original_command,
            fix=fixed_command,
            error=error
        )

    def find_similar_fixes(
        self,
        command: str,
        error: str
    ) -> List[CommandFix]:
        """
        Find fixes for similar errors.

        Returns:
            List of CommandFix objects, most relevant first
        """
        raw_fixes = self.learning_system.get_relevant_fixes(error)

        # Convert to CommandFix objects
        fixes = []
        for fix_dict in raw_fixes:
            fixes.append(CommandFix(
                original_command=fix_dict.get('original', ''),
                fixed_command=fix_dict.get('fix', ''),
                error_type=categorize_error(error),
                context="",
                timestamp=datetime.now().isoformat(),
                use_count=fix_dict.get('count', 1)
            ))

        return fixes

    # ==================== Pattern Memory ====================

    def remember_pattern(self, pattern_id: str, description: str):
        """Remember a successful pattern or strategy"""
        self.learning_system.learn_pattern(pattern_id, description)

    def get_pattern(self, pattern_id: str) -> Optional[str]:
        """Get a remembered pattern"""
        return self.learning_system.get_pattern(pattern_id)

    # ==================== Task Memory ====================

    def remember_task(self, task_name: str, commands: List[str]):
        """Remember a multi-step task"""
        self.learning_system.learn_task(task_name, commands)

    def get_task(self, task_name: str) -> Optional[List[str]]:
        """Get a remembered task"""
        return self.learning_system.get_task(task_name)

    # ==================== Success Patterns ====================

    def record_successful_pattern(self, intent: str, commands: List[str]):
        """
        Record a successful command pattern for future reference.

        This is useful for learning common workflows.
        """
        # For now, just update stats
        # In future, could analyze patterns and create tasks automatically
        pass

    # ==================== Statistics ====================

    def update_stats(self, success: bool):
        """Update execution statistics"""
        self.learning_system.update_stats(success)

    def get_statistics(self) -> Dict:
        """Get execution statistics"""
        meta = self.learning_system.learnings["metadata"]

        return {
            'total_executed': meta.get('total_commands', 0),
            'success_rate': meta.get('success_rate', 0.0),
            'patterns_learned': len(self.learning_system.learnings.get('patterns', {})),
            'fixes_recorded': sum(
                len(fixes)
                for fixes in self.learning_system.learnings.get('fix_patterns', {}).values()
            ),
            'apps_known': len(self.learning_system.learnings.get('apps', {})),
            'tasks_learned': len(self.learning_system.learnings.get('tasks', {}))
        }

    def get_memory_summary(self) -> str:
        """Get human-readable memory summary"""
        return self.learning_system.get_full_summary()

    # ==================== Maintenance ====================

    def cleanup_old_data(self, days: int = 30):
        """Remove old unused data"""
        self.learning_system.cleanup_old_data(days)

    def reset(self):
        """Reset all memory (use with caution!)"""
        self.learning_system.reset_learnings()

    # ==================== Context for AI ====================

    def get_ai_context(self) -> str:
        """Get formatted context for AI system prompt"""
        return self.learning_system.get_context_for_ai()

    def get_context_for_ai(self) -> str:
        """Alias for get_ai_context for backwards compatibility"""
        return self.get_ai_context()

    # ==================== Legacy Compatibility ====================

    def add_learning_from_ai(self, learning_data: Dict) -> bool:
        """Legacy method for AI learning blocks"""
        return self.learning_system.add_learning_from_ai(learning_data)

    def remove_learning_from_ai(self, learning_data: Dict) -> bool:
        """Legacy method for AI unlearn blocks"""
        return self.learning_system.remove_learning_from_ai(learning_data)

    def update_learning_from_ai(self, learning_data: Dict) -> bool:
        """Legacy method for AI update blocks"""
        return self.learning_system.update_learning_from_ai(learning_data)

    # ==================== Knowledge Base (v3.0) ====================

    def remember_fact(
        self,
        category: str,
        content: str,
        confidence: float = 0.8,
        source: str = "conversation",
        tier: int = 2,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Remember a new fact in the knowledge base.

        Args:
            category: 'personal', 'technical', or 'general'
            content: The fact to remember
            confidence: Confidence score 0.0-1.0
            source: 'conversation', 'experience', or 'explicit'
            tier: Memory tier (1=core, 2=active, 3=episodic, 4=archive)
            tags: Optional list of tags for better retrieval

        Returns:
            Fact ID (existing ID if deduplicated)
        """
        # Deduplication: check if a fact with same content already exists
        content_lower = content.lower().strip()
        for existing in self.learning_system.learnings["knowledge_base"]["facts"]:
            if existing.get("content", "").lower().strip() == content_lower:
                # Update existing fact instead of creating duplicate
                existing["confidence"] = max(existing.get("confidence", 0), confidence)
                existing["access_count"] = existing.get("access_count", 0) + 1
                existing["last_accessed"] = datetime.now().isoformat()
                if tags:
                    existing_tags = existing.get("tags", [])
                    for t in tags:
                        if t not in existing_tags:
                            existing_tags.append(t)
                    existing["tags"] = existing_tags
                self.learning_system._save_learnings()
                return existing.get("id", "fact_000")

        self._fact_counter += 1
        fact_id = f"fact_{self._fact_counter:03d}"

        fact = {
            "id": fact_id,
            "category": category,
            "content": content,
            "confidence": max(0.0, min(1.0, confidence)),
            "source": source,
            "tier": tier,
            "tags": tags or [],
            "curation_notes": "",
            "learned_at": datetime.now().isoformat(),
            "last_accessed": datetime.now().isoformat(),
            "access_count": 0
        }

        self.learning_system.learnings["knowledge_base"]["facts"].append(fact)
        self.learning_system.learnings["metadata"]["total_facts"] += 1
        self.learning_system._save_learnings()

        return fact_id

    def get_facts(
        self,
        category: Optional[str] = None,
        min_confidence: float = 0.0
    ) -> List[Dict]:
        """
        Get facts from knowledge base, optionally filtered by category.

        Args:
            category: Filter by category (personal|technical|general)
            min_confidence: Minimum confidence threshold

        Returns:
            List of fact dictionaries
        """
        facts = self.learning_system.learnings["knowledge_base"]["facts"]

        if category:
            facts = [f for f in facts if f.get("category") == category]

        if min_confidence > 0:
            facts = [f for f in facts if f.get("confidence", 0) >= min_confidence]

        return facts

    def get_facts_by_tier(self, tier: int) -> List[Dict]:
        """Get all facts at a specific tier level."""
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        return [f for f in facts if f.get("tier", 2) == tier]

    def get_active_facts(self) -> List[Dict]:
        """Get all Tier 2 (active) facts - convenience method."""
        return self.get_facts_by_tier(2)

    def update_fact_access(self, fact_id: str):
        """Update access count and timestamp for a fact"""
        for fact in self.learning_system.learnings["knowledge_base"]["facts"]:
            if fact.get("id") == fact_id:
                fact["last_accessed"] = datetime.now().isoformat()
                fact["access_count"] = fact.get("access_count", 0) + 1
                self.learning_system._save_learnings()
                break

    def update_fact(self, fact_id: str, updates: dict) -> bool:
        """Update a fact's fields in-place."""
        ALLOWED = {'content', 'category', 'confidence', 'tier', 'tags', 'curation_notes'}
        for fact in self.learning_system.learnings["knowledge_base"]["facts"]:
            if fact.get("id") == fact_id:
                for key, val in updates.items():
                    if key in ALLOWED:
                        fact[key] = val
                fact["last_accessed"] = datetime.now().isoformat()
                self.learning_system._save_learnings()
                return True
        return False

    def forget_fact(self, fact_id: str) -> bool:
        """Remove a fact from knowledge base"""
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        for i, fact in enumerate(facts):
            if fact.get("id") == fact_id:
                facts.pop(i)
                self.learning_system.learnings["metadata"]["total_facts"] -= 1
                self.learning_system._save_learnings()
                return True
        return False

    # ==================== User Profile (v3.0) ====================

    def get_user_profile(self) -> Dict:
        """Get complete user profile"""
        return self.learning_system.learnings.get("user_profile", {})

    def update_profile(self, key: str, value: any):
        """
        Update a user profile field.

        Supported keys: name, communication_style, preferences, interests, habits
        """
        profile = self.learning_system.learnings["user_profile"]

        if key == "name":
            profile["name"] = value
        elif key == "communication_style":
            if isinstance(value, dict):
                profile["communication_style"].update(value)
            else:
                # Assume it's formality or verbosity
                profile["communication_style"]["formality"] = value
        elif key == "preferences":
            if isinstance(value, dict):
                profile["preferences"].update(value)
        elif key == "interests":
            if isinstance(value, list):
                profile["interests"] = value
            else:
                # Add single interest
                if value not in profile["interests"]:
                    profile["interests"].append(value)
        elif key == "habits":
            if isinstance(value, dict):
                profile["habits"].update(value)
        else:
            # Generic key
            profile[key] = value

        self.learning_system._save_learnings()

    def add_preference(self, key: str, value: str):
        """Add a user preference"""
        self.learning_system.learnings["user_profile"]["preferences"][key] = value
        self.learning_system._save_learnings()

    def get_preference(self, key: str, default: any = None) -> any:
        """Get a user preference"""
        return self.learning_system.learnings["user_profile"]["preferences"].get(key, default)

    # ==================== Conversation Context (v3.0) ====================

    def get_conversation_context(self) -> Dict:
        """Get current conversation context"""
        return self.learning_system.learnings.get("conversation_memory", {}).get("current_context", {})

    def update_conversation_context(
        self,
        topic: Optional[str] = None,
        intent: Optional[str] = None,
        active_apps: Optional[List[str]] = None
    ):
        """Update current conversation context"""
        context = self.learning_system.learnings["conversation_memory"]["current_context"]

        if topic is not None:
            context["topic"] = topic
        if intent is not None:
            context["intent"] = intent
        if active_apps is not None:
            context["active_apps"] = active_apps

        context["last_interaction"] = datetime.now().isoformat()
        self.learning_system._save_learnings()

    def add_long_term_memory(
        self,
        memory_type: str,
        summary: str,
        significance: str = "medium"
    ) -> str:
        """
        Add an important memory to long-term storage.

        Args:
            memory_type: 'important_conversation' or 'key_decision'
            summary: Brief description of what happened
            significance: 'high', 'medium', or 'low'

        Returns:
            Memory ID
        """
        self._ltm_counter += 1
        ltm_id = f"ltm_{self._ltm_counter:03d}"

        memory = {
            "id": ltm_id,
            "type": memory_type,
            "summary": summary,
            "date": datetime.now().isoformat(),
            "significance": significance
        }

        self.learning_system.learnings["conversation_memory"]["long_term_memory"].append(memory)
        self.learning_system._save_learnings()

        return ltm_id

    def get_long_term_memories(
        self,
        significance: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Get long-term memories, optionally filtered by significance"""
        memories = self.learning_system.learnings["conversation_memory"]["long_term_memory"]

        if significance:
            memories = [m for m in memories if m.get("significance") == significance]

        # Return most recent first
        return sorted(memories, key=lambda m: m.get("date", ""), reverse=True)[:limit]