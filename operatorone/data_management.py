from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import json
from pathlib import Path
from paths import Paths


class DataManager:
    """Manages knowledge base cleanup and optimization"""

    # Thresholds
    MAX_FILE_SIZE_MB = 5
    LOW_CONFIDENCE_THRESHOLD = 0.3
    ARCHIVE_AGE_DAYS = 30
    STALE_DAYS = 30           # Days before auto-demotion
    STALE_MIN_ACCESSES = 3    # Min accesses to avoid demotion
    MAX_ARCHIVE_FACTS = 2000  # Max Tier 4 facts before pruning
    MAX_FACTS = 5000
    MAX_SESSIONS = 20
    MAX_LTM = 50

    def __init__(self, learning_system):
        """
        Initialize data manager.

        Args:
            learning_system: LearningSystem instance
        """
        self.learning_system = learning_system

    def perform_maintenance(self) -> Dict[str, int]:
        """
        Perform full maintenance cycle.

        Returns:
            Dictionary with counts of actions taken
        """
        stats = {
            'facts_pruned': 0,
            'facts_merged': 0,
            'facts_demoted': 0,
            'archive_pruned': 0,
            'sessions_archived': 0,
            'ltm_pruned': 0
        }

        # 1. Prune low-confidence old facts
        stats['facts_pruned'] = self._prune_low_confidence_facts()

        # 2. Merge similar facts
        stats['facts_merged'] = self._merge_similar_facts()

        # 3. Auto-demote stale Tier 2 facts to Tier 4
        stats['facts_demoted'] = self._auto_demote_stale_facts()

        # 4. Prune archive if too large
        stats['archive_pruned'] = self._prune_archive()

        # 5. Archive old sessions
        stats['sessions_archived'] = self._archive_old_sessions()

        # 6. Prune long-term memories
        stats['ltm_pruned'] = self._prune_long_term_memories()

        # 7. Save changes
        self.learning_system._save_learnings()

        return stats

    def _prune_low_confidence_facts(self) -> int:
        """
        Remove facts with confidence < 0.3 that are older than 30 days.

        Returns:
            Number of facts pruned
        """
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        now = datetime.now()
        cutoff_date = now - timedelta(days=self.ARCHIVE_AGE_DAYS)

        original_count = len(facts)

        # Filter out low-confidence old facts
        filtered_facts = []
        for fact in facts:
            try:
                learned_at = datetime.fromisoformat(fact.get("learned_at", ""))
                confidence = fact.get("confidence", 0.5)

                # Keep if: high confidence OR recent
                if confidence >= self.LOW_CONFIDENCE_THRESHOLD or learned_at > cutoff_date:
                    filtered_facts.append(fact)
            except:
                # If parsing fails, keep the fact
                filtered_facts.append(fact)

        self.learning_system.learnings["knowledge_base"]["facts"] = filtered_facts
        pruned_count = original_count - len(filtered_facts)

        # Update metadata
        self.learning_system.learnings["metadata"]["total_facts"] = len(filtered_facts)

        return pruned_count

    def _merge_similar_facts(self) -> int:
        """
        Merge duplicate or very similar facts.

        Returns:
            Number of facts merged
        """
        facts = self.learning_system.learnings["knowledge_base"]["facts"]

        if len(facts) < 2:
            return 0

        # Group facts by similarity
        merged_count = 0
        seen_content = {}

        unique_facts = []
        for fact in facts:
            content = fact.get("content", "").lower().strip()

            # Check for exact duplicates
            if content in seen_content:
                # Merge: keep the one with higher confidence
                existing_fact = seen_content[content]
                new_confidence = fact.get("confidence", 0.5)
                existing_confidence = existing_fact.get("confidence", 0.5)

                if new_confidence > existing_confidence:
                    # Replace with higher confidence version
                    seen_content[content] = fact
                    # Update in unique_facts list
                    for i, f in enumerate(unique_facts):
                        if f.get("id") == existing_fact.get("id"):
                            unique_facts[i] = fact
                            break

                # Increment access count
                seen_content[content]["access_count"] = (
                    existing_fact.get("access_count", 0) +
                    fact.get("access_count", 0)
                )

                merged_count += 1
            else:
                seen_content[content] = fact
                unique_facts.append(fact)

        self.learning_system.learnings["knowledge_base"]["facts"] = unique_facts
        self.learning_system.learnings["metadata"]["total_facts"] = len(unique_facts)

        return merged_count

    def _auto_demote_stale_facts(self) -> int:
        """
        Demote Tier 2 facts not accessed in 30+ days with <3 accesses to Tier 4 (archive).

        Returns:
            Number of facts demoted
        """
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        now = datetime.now()
        cutoff = now - timedelta(days=self.STALE_DAYS)
        demoted = 0

        for fact in facts:
            if fact.get("tier", 2) != 2:
                continue
            access_count = fact.get("access_count", 0)
            if access_count >= self.STALE_MIN_ACCESSES:
                continue
            try:
                last_accessed = fact.get("last_accessed", fact.get("learned_at", ""))
                if last_accessed and datetime.fromisoformat(last_accessed) < cutoff:
                    fact["tier"] = 4
                    fact["curation_notes"] = fact.get("curation_notes", "") + " [auto-demoted: stale]"
                    demoted += 1
            except Exception:
                pass

        return demoted

    def _prune_archive(self) -> int:
        """
        If Tier 4 exceeds MAX_ARCHIVE_FACTS, remove lowest-value facts.

        Returns:
            Number of archive facts pruned
        """
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        archive_facts = [f for f in facts if f.get("tier", 2) == 4]

        if len(archive_facts) <= self.MAX_ARCHIVE_FACTS:
            return 0

        # Sort archive by value: confidence * (access_count + 1)
        archive_facts.sort(
            key=lambda f: f.get("confidence", 0) * (f.get("access_count", 0) + 1)
        )

        # Remove lowest-value ones
        to_remove = len(archive_facts) - self.MAX_ARCHIVE_FACTS
        remove_ids = {f.get("id") for f in archive_facts[:to_remove]}

        original_count = len(facts)
        self.learning_system.learnings["knowledge_base"]["facts"] = [
            f for f in facts if f.get("id") not in remove_ids
        ]
        pruned = original_count - len(self.learning_system.learnings["knowledge_base"]["facts"])
        self.learning_system.learnings["metadata"]["total_facts"] = len(
            self.learning_system.learnings["knowledge_base"]["facts"]
        )

        return pruned

    def _archive_old_sessions(self) -> int:
        """
        Archive sessions older than 30 days (keep only last 20 sessions).

        Returns:
            Number of sessions archived
        """
        sessions = self.learning_system.learnings["conversation_memory"]["sessions"]

        if len(sessions) <= self.MAX_SESSIONS:
            return 0

        # Keep only most recent sessions
        archived_count = len(sessions) - self.MAX_SESSIONS
        self.learning_system.learnings["conversation_memory"]["sessions"] = sessions[-self.MAX_SESSIONS:]

        return archived_count

    def _prune_long_term_memories(self) -> int:
        """
        Keep only the most important long-term memories (max 50).

        Returns:
            Number of memories pruned
        """
        ltm = self.learning_system.learnings["conversation_memory"]["long_term_memory"]

        if len(ltm) <= self.MAX_LTM:
            return 0

        # Sort by significance and date
        significance_order = {"high": 3, "medium": 2, "low": 1}

        sorted_ltm = sorted(
            ltm,
            key=lambda m: (
                significance_order.get(m.get("significance", "low"), 1),
                m.get("date", "")
            ),
            reverse=True
        )

        pruned_count = len(sorted_ltm) - self.MAX_LTM
        self.learning_system.learnings["conversation_memory"]["long_term_memory"] = sorted_ltm[:self.MAX_LTM]

        return pruned_count

    def get_file_size_mb(self) -> float:
        """Get current learning file size in MB"""
        try:
            file_path = Path(self.learning_system.learning_file)
            if file_path.exists():
                size_bytes = file_path.stat().st_size
                return size_bytes / (1024 * 1024)  # Convert to MB
        except:
            pass
        return 0.0

    def get_storage_stats(self) -> Dict:
        """Get storage statistics with tier breakdown"""
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for f in facts:
            tier = f.get("tier", 2)
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        return {
            'file_size_mb': round(self.get_file_size_mb(), 2),
            'total_facts': len(facts),
            'tier_1_core': tier_counts[1],
            'tier_2_active': tier_counts[2],
            'tier_3_episodic': tier_counts[3],
            'tier_4_archive': tier_counts[4],
            'total_sessions': len(self.learning_system.learnings["conversation_memory"]["sessions"]),
            'total_ltm': len(self.learning_system.learnings["conversation_memory"]["long_term_memory"]),
            'max_file_size_mb': self.MAX_FILE_SIZE_MB,
            'health': 'good' if self.get_file_size_mb() < self.MAX_FILE_SIZE_MB else 'needs_cleanup'
        }

    def should_run_maintenance(self) -> bool:
        """
        Determine if maintenance should run based on file size and fact count.

        Returns:
            True if maintenance is recommended
        """
        # Run maintenance if file is getting large
        if self.get_file_size_mb() > self.MAX_FILE_SIZE_MB * 0.8:  # 80% threshold
            return True

        # Run maintenance if too many facts
        facts = self.learning_system.learnings["knowledge_base"]["facts"]
        if len(facts) > self.MAX_FACTS * 0.9:  # 90% threshold
            return True

        # Run maintenance if too many sessions
        sessions = self.learning_system.learnings["conversation_memory"]["sessions"]
        if len(sessions) > self.MAX_SESSIONS:
            return True

        return False

    def create_backup(self) -> str:
        """
        Create a timestamped backup of the learning file.

        Returns:
            Path to backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Paths.get_backup_file(timestamp)

        with open(self.learning_system.learning_file, 'r', encoding='utf-8') as src:
            data = json.load(src)

        with open(backup_path, 'w', encoding='utf-8') as dst:
            json.dump(data, dst, indent=2, ensure_ascii=False)

        return backup_path
