import atexit
import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

from utils import categorize_error
from logger_config import op_logger
from paths import Paths


class LearningSystem:
    """Manages persistent learnings with intelligent context generation.

    Thread safety: `self.lock` (an RLock) must be held for any read or
    mutation of `self.learnings`, which is shared across threads (e.g. the
    overlay's background asyncio loop). Mutators call `mark_dirty()`; the
    actual disk write happens in `flush()`, called once per interaction and
    at exit.
    """

    def __init__(self, learning_file: str = None):
        """
        Initialize learning system.

        Args:
            learning_file: Optional custom path. If None, uses user data directory.
                          For exe compatibility, always uses user data dir by default.
        """
        # Use user data directory for exe compatibility
        if learning_file is None:
            self.learning_file = Paths.get_learning_file()
            op_logger.logger.info(f"Using data directory: {Paths.get_user_data_dir()}")
        else:
            self.learning_file = learning_file

        self.lock = threading.RLock()
        self._dirty = False
        self.learnings = self._load_learnings()
        atexit.register(self.flush)

    def _get_default_structure(self) -> Dict:
        """Optimized learning structure v4.0 - Tiered Jarvis Memory"""
        return {
            "user_profile": {
                "name": "",
                "communication_style": {
                    "formality": "casual",  # casual | formal
                    "verbosity": "concise"   # concise | detailed
                },
                "preferences": {},
                "interests": [],
                "habits": {}
            },
            "core_memory": {
                "identity": {"name": "", "profession": "", "location": ""},
                "personality": {"tone": "casual", "humor": True, "verbosity": "concise"},
                "preferences": {},
                "active_projects": [],
                "important_facts": [],
                "last_curated": ""
            },
            "knowledge_base": {
                "facts": [
                    # {
                    #   "id": "fact_001",
                    #   "category": "personal|technical|general",
                    #   "content": "fact text",
                    #   "confidence": 0.0-1.0,
                    #   "source": "conversation|experience|explicit",
                    #   "tier": 1|2|3|4,  # core|active|episodic|archive
                    #   "tags": ["tag1", "tag2"],
                    #   "curation_notes": "",
                    #   "learned_at": "ISO timestamp",
                    #   "last_accessed": "ISO timestamp",
                    #   "access_count": 0
                    # }
                ]
            },
            "conversation_memory": {
                "sessions": [],
                "current_context": {
                    "topic": "",
                    "intent": "",
                    "active_apps": [],
                    "last_interaction": ""
                },
                "long_term_memory": []
            },
            "command_memory": {
                "apps": {},
                "patterns": {},
                "preferences": {
                    "default_browser": "opera"
                },
                "tasks": {},
                "fix_patterns": {}
            },
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_commands": 0,
                "successes": 0,
                "failures": 0,
                "success_rate": 0.0,
                "version": "4.0",
                "total_facts": 0
            }
        }

    def _load_learnings(self) -> Dict:
        """Load learnings from file, falling back to the backup on corruption."""
        for path, is_backup in ((self.learning_file, False), (f"{self.learning_file}.bak", True)):
            if not os.path.exists(path):
                continue
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    learnings = json.load(f)
            except Exception as e:
                op_logger.logger.error(f"Error loading {'backup' if is_backup else 'learnings'}: {e}")
                if not is_backup:
                    self._quarantine_corrupt_file()
                continue

            if is_backup:
                op_logger.logger.warning("Recovered memory from backup file")

            version = learnings.get("metadata", {}).get("version", "1.0")

            if version == "1.0":
                learnings = self._migrate_to_v2(learnings)
                version = "2.0"

            if version == "2.0":
                learnings = self._migrate_to_v3(learnings)
                version = "3.0"

            if version == "3.0":
                learnings = self._migrate_to_v4(learnings)
                version = "4.0"

            # Ensure all sections exist
            default = self._get_default_structure()
            for key in default:
                if key not in learnings:
                    learnings[key] = default[key]
            return learnings

        return self._get_default_structure()

    def _quarantine_corrupt_file(self):
        """Preserve a corrupt learnings file for manual recovery instead of overwriting it."""
        try:
            corrupt_path = f"{self.learning_file}.corrupt"
            if os.path.exists(corrupt_path):
                os.remove(corrupt_path)
            os.replace(self.learning_file, corrupt_path)
            op_logger.logger.warning(f"Corrupt memory file preserved at {corrupt_path}")
        except Exception as e:
            op_logger.logger.error(f"Could not quarantine corrupt file: {e}")

    def _migrate_to_v2(self, old_data: Dict) -> Dict:
        """Migrate v1 learning structure to v2"""
        new_data = self._get_default_structure()

        # Merge app_paths and launch_strategies
        if "app_paths" in old_data:
            for app, path in old_data["app_paths"].items():
                strategy = old_data.get("launch_strategies", {}).get(app, "unknown")
                new_data["apps"][app] = {
                    "path": path,
                    "strategy": strategy,
                    "last_used": datetime.now().isoformat()
                }

        # Copy patterns
        if "successful_patterns" in old_data:
            new_data["patterns"] = old_data["successful_patterns"]

        # Copy preferences
        if "user_preferences" in old_data:
            new_data["preferences"] = old_data["user_preferences"]

        # Copy tasks
        if "common_tasks" in old_data:
            new_data["tasks"] = old_data["common_tasks"]

        # Consolidate command fixes into patterns
        if "command_fixes" in old_data:
            self._consolidate_fixes(old_data["command_fixes"], new_data["fix_patterns"])

        # Copy metadata
        if "metadata" in old_data:
            new_data["metadata"].update(old_data["metadata"])
            new_data["metadata"]["version"] = "2.0"

        return new_data

    def _migrate_to_v3(self, old_data: Dict) -> Dict:
        """Migrate v2.0 learning structure to v3.0"""
        op_logger.logger.info("Migrating learning system from v2.0 to v3.0...")

        # Create backup before migration
        backup_file = Paths.get_backup_file('v2_migration')
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(old_data, f, indent=2, ensure_ascii=False)
            op_logger.logger.info(f"Created migration backup at {backup_file}")
        except Exception as e:
            op_logger.logger.warning(f"Could not create backup: {e}")

        # Create new v3.0 structure
        new_data = self._get_default_structure()

        # Move old data into command_memory section
        if "apps" in old_data:
            new_data["command_memory"]["apps"] = old_data["apps"]
        if "patterns" in old_data:
            new_data["command_memory"]["patterns"] = old_data["patterns"]
        if "preferences" in old_data:
            new_data["command_memory"]["preferences"] = old_data["preferences"]
            # Also migrate preferences to user_profile
            new_data["user_profile"]["preferences"] = old_data["preferences"].copy()
        if "tasks" in old_data:
            new_data["command_memory"]["tasks"] = old_data["tasks"]
        if "fix_patterns" in old_data:
            new_data["command_memory"]["fix_patterns"] = old_data["fix_patterns"]

        # Preserve metadata stats
        if "metadata" in old_data:
            old_meta = old_data["metadata"]
            new_data["metadata"].update({
                "created": old_meta.get("created", datetime.now().isoformat()),
                "last_updated": datetime.now().isoformat(),
                "total_commands": old_meta.get("total_commands", 0),
                "successes": old_meta.get("successes", 0),
                "failures": old_meta.get("failures", 0),
                "success_rate": old_meta.get("success_rate", 0.0),
                "version": "3.0"
            })

        op_logger.logger.info("Migration to v3.0 complete!")
        return new_data

    def _migrate_to_v4(self, old_data: Dict) -> Dict:
        """Migrate v3.0 learning structure to v4.0 (Tiered Jarvis Memory)"""
        op_logger.logger.info("Migrating learning system from v3.0 to v4.0...")

        # Create backup before migration
        backup_file = Paths.get_backup_file('v3_to_v4_migration')
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(old_data, f, indent=2, ensure_ascii=False)
            op_logger.logger.info(f"Created migration backup at {backup_file}")
        except Exception as e:
            op_logger.logger.warning(f"Could not create backup: {e}")

        # Add tier, tags, curation_notes to all existing facts (default Tier 2 = active)
        facts = old_data.get("knowledge_base", {}).get("facts", [])
        for fact in facts:
            if "tier" not in fact:
                fact["tier"] = 2
            if "tags" not in fact:
                fact["tags"] = []
            if "curation_notes" not in fact:
                fact["curation_notes"] = ""

        # Create core_memory section
        user_profile = old_data.get("user_profile", {})
        comm_style = user_profile.get("communication_style", {})

        core_memory = {
            "identity": {
                "name": user_profile.get("name", ""),
                "profession": "",
                "location": ""
            },
            "personality": {
                "tone": comm_style.get("formality", "casual"),
                "humor": True,
                "verbosity": comm_style.get("verbosity", "concise")
            },
            "preferences": user_profile.get("preferences", {}).copy(),
            "active_projects": [],
            "important_facts": [],
            "last_curated": ""
        }

        old_data["core_memory"] = core_memory

        # Update version
        if "metadata" not in old_data:
            old_data["metadata"] = {}
        old_data["metadata"]["version"] = "4.0"
        old_data["metadata"]["last_updated"] = datetime.now().isoformat()

        # Save migrated data
        self.learnings = old_data
        self._save_learnings()

        op_logger.logger.info("Migration to v4.0 complete!")
        return old_data

    def _consolidate_fixes(self, fixes: List[Dict], fix_patterns: Dict):
        """Consolidate similar fixes into patterns"""
        # Group by error keywords
        error_groups = defaultdict(list)
        for fix in fixes:
            # Extract key error terms
            error = fix.get("context", fix.get("original", "")).lower()
            key_terms = ["not recognized", "not found", "access denied", "timeout", "uwp"]

            for term in key_terms:
                if term in error:
                    error_groups[term].append({
                        "original": fix["original"][:50],
                        "fix": fix["fix"][:100],
                        "count": 1
                    })
                    break

        # Keep only most common fixes per category (max 3)
        for category, fixes_list in error_groups.items():
            if len(fixes_list) > 3:
                fixes_list = fixes_list[-3:]
            fix_patterns[category] = fixes_list

    def mark_dirty(self):
        """Record that in-memory state has changed; written to disk on next flush()."""
        with self.lock:
            self._dirty = True

    def flush(self):
        """Write to disk if there are unsaved changes."""
        with self.lock:
            if self._dirty:
                self._save_learnings()

    def _save_learnings(self):
        """Atomically save learnings: write temp file, rotate backup, replace.

        A crash mid-write can never corrupt the real file, and the previous
        version always survives as .bak.
        """
        with self.lock:
            tmp_file = f"{self.learning_file}.tmp"
            try:
                self.learnings["metadata"]["last_updated"] = datetime.now().isoformat()
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(self.learnings, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())

                if os.path.exists(self.learning_file):
                    backup = f"{self.learning_file}.bak"
                    try:
                        if os.path.exists(backup):
                            os.remove(backup)
                        os.replace(self.learning_file, backup)
                    except Exception as e:
                        op_logger.logger.warning(f"Could not rotate backup: {e}")

                os.replace(tmp_file, self.learning_file)
                self._dirty = False
                op_logger.logger.debug(f"Learnings saved to {self.learning_file}")
            except Exception as e:
                op_logger.logger.error(f"Error saving learnings: {e}")

    # ========================
    # Core Learning Operations
    # ========================

    def learn_app(self, app_name: str, path: str = None, strategy: str = None, process_name: str = None):
        """Learn app information (path, strategy, and/or process name for closing)"""
        app_name = app_name.lower()

        if app_name not in self.learnings["command_memory"]["apps"]:
            self.learnings["command_memory"]["apps"][app_name] = {}

        if path:
            self.learnings["command_memory"]["apps"][app_name]["path"] = path
        if strategy:
            self.learnings["command_memory"]["apps"][app_name]["strategy"] = strategy
        if process_name:
            self.learnings["command_memory"]["apps"][app_name]["process_name"] = process_name

        self.learnings["command_memory"]["apps"][app_name]["last_used"] = datetime.now().isoformat()
        self.mark_dirty()

    def learn_pattern(self, pattern_id: str, description: str):
        """Learn a successful pattern (max 100 chars)"""
        self.learnings["command_memory"]["patterns"][pattern_id] = description[:100]
        self.mark_dirty()

    def learn_preference(self, key: str, value: Any):
        """Learn user preference"""
        self.learnings["command_memory"]["preferences"][key] = value
        self.mark_dirty()

    def learn_task(self, task_name: str, commands: List[str]):
        """Learn multi-step task"""
        self.learnings["command_memory"]["tasks"][task_name.lower()] = commands
        self.mark_dirty()

    def record_command_fix(self, original: str, fix: str, error: str = ""):
        """Record a command fix, categorized by error type"""
        # Extract error category using shared utility
        category = categorize_error(error)

        # Add to category
        if category not in self.learnings["command_memory"]["fix_patterns"]:
            self.learnings["command_memory"]["fix_patterns"][category] = []

        # Check if similar fix exists
        existing = None
        for fix_entry in self.learnings["command_memory"]["fix_patterns"][category]:
            if fix_entry["fix"][:50] == fix[:50]:
                existing = fix_entry
                break

        if existing:
            existing["count"] += 1
        else:
            self.learnings["command_memory"]["fix_patterns"][category].append({
                "original": original[:50],
                "fix": fix[:100],
                "count": 1
            })

        # Keep only top 3 fixes per category
        self.learnings["command_memory"]["fix_patterns"][category] = sorted(
            self.learnings["command_memory"]["fix_patterns"][category],
            key=lambda x: x["count"],
            reverse=True
        )[:3]

        self.mark_dirty()

    # ========================
    # Retrieval Operations
    # ========================

    def get_app_info(self, app_name: str) -> Optional[Dict]:
        """Get app information"""
        return self.learnings["command_memory"]["apps"].get(app_name.lower())

    def get_pattern(self, pattern_id: str) -> Optional[str]:
        """Get a learned pattern"""
        return self.learnings["command_memory"]["patterns"].get(pattern_id)

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get user preference"""
        return self.learnings["command_memory"]["preferences"].get(key, default)

    def get_task(self, task_name: str) -> Optional[List[str]]:
        """Get learned task"""
        return self.learnings["command_memory"]["tasks"].get(task_name.lower())

    def get_relevant_fixes(self, error: str) -> List[Dict]:
        """Get fixes relevant to this error"""
        error_lower = error.lower()
        relevant = []

        for category, fixes in self.learnings["command_memory"]["fix_patterns"].items():
            if category in error_lower or any(keyword in error_lower for keyword in ["not found", "not recognized", "access", "timeout"]):
                relevant.extend(fixes)

        return relevant[:5]  # Max 5 most relevant

    # ========================
    # Statistics
    # ========================

    def update_stats(self, success: bool):
        """Update execution statistics"""
        self.learnings["metadata"]["total_commands"] += 1
        if success:
            self.learnings["metadata"]["successes"] += 1
        else:
            self.learnings["metadata"]["failures"] += 1

        total = self.learnings["metadata"]["total_commands"]
        successes = self.learnings["metadata"]["successes"]
        self.learnings["metadata"]["success_rate"] = round(successes / total, 3) if total > 0 else 0.0

        self.mark_dirty()

    # ========================
    # AI Integration (Simplified)
    # ========================

    def add_learning_from_ai(self, learning_data: Dict) -> bool:
        """AI adds learning in simple format"""
        try:
            learning_type = learning_data.get("type")
            data = learning_data.get("data", {})

            op_logger.logger.debug(f"Attempting to add learning: type={learning_type}, data={data}")

            if learning_type == "app":
                self.learn_app(
                    data.get("name"),
                    data.get("path"),
                    data.get("strategy"),
                    data.get("process_name")
                )
                op_logger.logger.info(f"Added app learning: {data.get('name')}")
            elif learning_type == "pattern":
                self.learn_pattern(data.get("id"), data.get("description"))
                op_logger.logger.info(f"Added pattern: {data.get('id')}")
            elif learning_type == "preference":
                self.learn_preference(data.get("key"), data.get("value"))
                op_logger.logger.info(f"Added preference: {data.get('key')}")
            elif learning_type == "task":
                self.learn_task(data.get("name"), data.get("commands", []))
                op_logger.logger.info(f"Added task: {data.get('name')}")
            else:
                op_logger.logger.warning(f"Unknown learning type: {learning_type}")
                return False

            return True
        except Exception as e:
            op_logger.logger.error(f"Error adding learning: {e}")
            import traceback
            traceback.print_exc()
            return False

    def remove_learning_from_ai(self, learning_data: Dict) -> bool:
        """AI removes outdated learning"""
        try:
            learning_type = learning_data.get("type")
            identifier = learning_data.get("identifier")

            if learning_type == "app" and identifier in self.learnings["command_memory"]["apps"]:
                del self.learnings["command_memory"]["apps"][identifier]
                self.mark_dirty()
                return True
            elif learning_type == "pattern" and identifier in self.learnings["command_memory"]["patterns"]:
                del self.learnings["command_memory"]["patterns"][identifier]
                self.mark_dirty()
                return True
            elif learning_type == "preference" and identifier in self.learnings["command_memory"]["preferences"]:
                del self.learnings["command_memory"]["preferences"][identifier]
                self.mark_dirty()
                return True
            elif learning_type == "task" and identifier in self.learnings["command_memory"]["tasks"]:
                del self.learnings["command_memory"]["tasks"][identifier]
                self.mark_dirty()
                return True

            return False
        except Exception as e:
            op_logger.logger.error(f"Error removing learning: {e}")
            return False

    def update_learning_from_ai(self, learning_data: Dict) -> bool:
        """AI updates existing learning"""
        try:
            learning_type = learning_data.get("type")
            identifier = learning_data.get("identifier")
            new_data = learning_data.get("new_data", {})

            if learning_type == "app" and identifier in self.learnings["command_memory"]["apps"]:
                if "path" in new_data:
                    self.learnings["command_memory"]["apps"][identifier]["path"] = new_data["path"]
                if "strategy" in new_data:
                    self.learnings["command_memory"]["apps"][identifier]["strategy"] = new_data["strategy"]
                self.mark_dirty()
                return True
            elif learning_type == "pattern" and identifier in self.learnings["command_memory"]["patterns"]:
                self.learnings["command_memory"]["patterns"][identifier] = new_data.get("description")
                self.mark_dirty()
                return True
            elif learning_type == "preference" and identifier in self.learnings["command_memory"]["preferences"]:
                self.learnings["command_memory"]["preferences"][identifier] = new_data.get("value")
                self.mark_dirty()
                return True
            elif learning_type == "task" and identifier in self.learnings["command_memory"]["tasks"]:
                self.learnings["command_memory"]["tasks"][identifier] = new_data.get("commands", [])
                self.mark_dirty()
                return True

            return False
        except Exception as e:
            op_logger.logger.error(f"Error updating learning: {e}")
            return False

    # ========================
    # Smart Context Generation
    # ========================

    def get_context_for_ai(self) -> str:
        """Generate concise, actionable context for AI"""
        lines = []

        # Recently used apps (last 7 days)
        recent_apps = self._get_recent_apps(days=7)
        if recent_apps:
            lines.append("**Recently Used Apps:**")
            for app, info in recent_apps.items():
                lines.append(f"  • {app}: {info['strategy']}")

        # Key patterns (max 5 most useful)
        if self.learnings["command_memory"]["patterns"]:
            lines.append("\n**Key Patterns:**")
            for pattern_id, desc in list(self.learnings["command_memory"]["patterns"].items())[:5]:
                lines.append(f"  • {pattern_id}: {desc}")

        # User preferences
        if self.learnings["command_memory"]["preferences"]:
            lines.append("\n**Preferences:**")
            for key, value in self.learnings["command_memory"]["preferences"].items():
                lines.append(f"  • {key}: {value}")

        # Common tasks
        if self.learnings["command_memory"]["tasks"]:
            lines.append("\n**Learned Tasks:**")
            for task_name in list(self.learnings["command_memory"]["tasks"].keys())[:3]:
                lines.append(f"  • {task_name}")

        # Stats summary
        meta = self.learnings["metadata"]
        lines.append(f"\n**Performance:** {meta['success_rate']*100:.0f}% success rate ({meta['total_commands']} commands)")

        return "\n".join(lines) if lines else "No learnings yet - start fresh!"

    def _get_recent_apps(self, days: int = 7) -> Dict:
        """Get apps used in last N days"""
        cutoff = datetime.now() - timedelta(days=days)
        recent = {}

        for app, info in self.learnings["command_memory"]["apps"].items():
            if "last_used" in info:
                try:
                    last_used = datetime.fromisoformat(info["last_used"])
                    if last_used > cutoff:
                        recent[app] = info
                except:
                    pass

        return recent

    def get_similar_fixes(self, error: str) -> List[Dict]:
        """Get similar command fixes (for retry logic)"""
        return self.get_relevant_fixes(error)

    def get_full_summary(self) -> str:
        """Get complete summary for /learnings command"""
        lines = ["=" * 60, "OPERATOR LEARNINGS DATABASE", "=" * 60, ""]

        # Apps
        if self.learnings["command_memory"]["apps"]:
            lines.append(f"📱 KNOWN APPS ({len(self.learnings['command_memory']['apps'])})")
            lines.append("-" * 60)
            for app, info in sorted(self.learnings["command_memory"]["apps"].items()):
                lines.append(f"  {app}:")
                lines.append(f"    Strategy: {info.get('strategy', 'unknown')}")
                if "path" in info:
                    lines.append(f"    Path: {info['path'][:60]}...")
                lines.append("")

        # Patterns
        if self.learnings["command_memory"]["patterns"]:
            lines.append(f"🧠 LEARNED PATTERNS ({len(self.learnings['command_memory']['patterns'])})")
            lines.append("-" * 60)
            for pattern_id, desc in self.learnings["command_memory"]["patterns"].items():
                lines.append(f"  • {pattern_id}: {desc}")
            lines.append("")

        # Preferences
        if self.learnings["command_memory"]["preferences"]:
            lines.append(f"⚙️ USER PREFERENCES")
            lines.append("-" * 60)
            for key, value in self.learnings["command_memory"]["preferences"].items():
                lines.append(f"  • {key}: {value}")
            lines.append("")

        # Tasks
        if self.learnings["command_memory"]["tasks"]:
            lines.append(f"🔄 COMMON TASKS ({len(self.learnings['command_memory']['tasks'])})")
            lines.append("-" * 60)
            for task_name, commands in self.learnings["command_memory"]["tasks"].items():
                lines.append(f"  {task_name}:")
                for cmd in commands:
                    lines.append(f"    → {cmd}")
            lines.append("")

        # Fix patterns
        if self.learnings["command_memory"]["fix_patterns"]:
            lines.append(f"🔧 FIX PATTERNS")
            lines.append("-" * 60)
            for category, fixes in self.learnings["command_memory"]["fix_patterns"].items():
                lines.append(f"  {category.upper()}:")
                for fix in fixes:
                    lines.append(f"    • Used {fix['count']}x: {fix['fix'][:60]}")
            lines.append("")

        # Stats
        meta = self.learnings["metadata"]
        lines.append("📊 STATISTICS")
        lines.append("-" * 60)
        lines.append(f"  Total Commands: {meta['total_commands']}")
        lines.append(f"  Successes: {meta['successes']}")
        lines.append(f"  Failures: {meta['failures']}")
        lines.append(f"  Success Rate: {meta['success_rate']*100:.1f}%")
        lines.append(f"  Last Updated: {meta['last_updated']}")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ========================
    # Maintenance
    # ========================

    def cleanup_old_data(self, days: int = 30):
        """Remove apps not used in N days"""
        cutoff = datetime.now() - timedelta(days=days)
        to_remove = []

        for app, info in self.learnings["command_memory"]["apps"].items():
            if "last_used" in info:
                try:
                    last_used = datetime.fromisoformat(info["last_used"])
                    if last_used < cutoff:
                        to_remove.append(app)
                except:
                    pass

        for app in to_remove:
            del self.learnings["command_memory"]["apps"][app]

        if to_remove:
            self.mark_dirty()

    def reset_learnings(self):
        """Reset all learnings"""
        self.learnings = self._get_default_structure()
        self._save_learnings()