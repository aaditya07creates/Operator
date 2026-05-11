
import json
import re
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from logger_config import op_logger


class MemoryCurator:
    """AI-powered memory curation running in background."""

    BATCH_SIZE = 6          # Curate after this many interactions (5-7 range)
    COOLDOWN_SECONDS = 60   # Minimum time between curation runs

    def __init__(self, learning_system, core_memory):
        self.learning_system = learning_system
        self.core_memory = core_memory
        self._pending_interactions: List[Dict] = []
        self._last_curation: Optional[float] = None
        self._lock = threading.Lock()
        self._curation_provider = None  # Lazy cached LLM provider

    def queue_interaction(self, user_message: str, ai_response: str,
                          commands: List[str], success: bool):
        """Queue an interaction for batch curation. Non-blocking."""
        interaction = {
            "user": user_message[:200],  # Truncate for prompt size
            "ai": (ai_response or "")[:200],
            "commands": commands[:5],
            "success": success,
            "timestamp": datetime.now().isoformat()
        }

        with self._lock:
            self._pending_interactions.append(interaction)
            pending_count = len(self._pending_interactions)

        # Check if we should curate
        if pending_count >= self.BATCH_SIZE:
            now = time.time()
            if self._last_curation is None or (now - self._last_curation) >= self.COOLDOWN_SECONDS:
                # Launch background curation
                thread = threading.Thread(target=self._run_curation, daemon=True)
                thread.start()

    def force_curate(self) -> str:
        """Immediate curation run (for /curate command). Returns summary."""
        return self._run_curation(force=True)

    def _run_curation(self, force: bool = False) -> str:
        """Background curation cycle."""
        with self._lock:
            if not self._pending_interactions and not force:
                return "No pending interactions to curate."
            interactions = self._pending_interactions.copy()
            self._pending_interactions.clear()

        if not interactions and not force:
            return "No interactions to curate."

        self._last_curation = time.time()

        try:
            op_logger.logger.info(f"Starting memory curation ({len(interactions)} interactions)...")

            # 1. Build curation prompt
            prompt = self._build_curation_prompt(interactions)

            # 2. Call LLM
            response = self._call_curation_llm(prompt)
            if not response:
                op_logger.logger.warning("Curation LLM returned no response")
                return "Curation failed: no LLM response."

            # 3. Parse response
            decisions = self._parse_curation_response(response)
            if not decisions:
                op_logger.logger.warning("Could not parse curation response")
                return "Curation failed: could not parse response."

            # 4. Execute decisions
            summary = self._execute_decisions(decisions)

            # 5. Update last curated timestamp
            core = self.learning_system.learnings.setdefault("core_memory", {})
            core["last_curated"] = datetime.now().isoformat()
            self.learning_system._save_learnings()

            op_logger.logger.info(f"Curation complete: {summary}")
            return summary

        except Exception as e:
            op_logger.logger.error(f"Curation error: {e}")
            import traceback
            traceback.print_exc()
            return f"Curation error: {e}"

    def _build_curation_prompt(self, interactions: List[Dict]) -> str:
        """Build the prompt that asks the AI what to remember."""
        # Core memory summary
        core_summary = self.core_memory.get_core_prompt_section() or "(empty)"

        # Interaction summaries
        interaction_lines = []
        for i, inter in enumerate(interactions, 1):
            cmds = ", ".join(inter["commands"][:3]) if inter["commands"] else "none"
            status = "OK" if inter["success"] else "FAILED"
            interaction_lines.append(
                f"{i}. User: {inter['user'][:100]}\n"
                f"   AI: {inter['ai'][:100]}\n"
                f"   Commands: {cmds} [{status}]"
            )
        interactions_text = "\n".join(interaction_lines) if interaction_lines else "(no recent interactions)"

        # Active knowledge count
        facts = self.learning_system.learnings.get("knowledge_base", {}).get("facts", [])
        tier2_facts = [f for f in facts if f.get("tier", 2) == 2]
        tier2_sample = ""
        if tier2_facts:
            sample = tier2_facts[:5]
            tier2_sample = "\nSample active facts:\n" + "\n".join(
                f"  - [{f.get('id')}] {f.get('content', '')[:80]} (conf:{f.get('confidence', 0):.1f})"
                for f in sample
            )

        return f"""You are a memory curator for an AI assistant. Evaluate these recent interactions and decide what to remember.

CURRENT CORE MEMORY:
{core_summary}

RECENT INTERACTIONS:
{interactions_text}

ACTIVE KNOWLEDGE: {len(tier2_facts)} facts stored{tier2_sample}

Respond with JSON only (no markdown fences):
{{
  "new_facts": [{{"content": "...", "category": "personal|technical|general", "tier": 2, "confidence": 0.8, "tags": ["..."]}}],
  "core_updates": {{
    "identity": {{"field": "value"}},
    "preferences": {{"key": "value"}},
    "projects_add": ["..."],
    "facts_add": ["important fact to always remember"]
  }},
  "promotions": [{{"fact_id": "...", "reason": "..."}}],
  "demotions": [{{"fact_id": "...", "reason": "..."}}],
  "deletions": ["fact_XXX"],
  "reasoning": "Brief explanation"
}}

RULES:
- Only store genuinely useful information, not trivial interaction details
- Core memory = things AI should ALWAYS know. Active = useful per-query.
- Promote to core only facts that are critical or repeatedly referenced
- If nothing needs to change, return {{"reasoning": "No memory updates needed"}}
- Keep response concise. Omit empty arrays/objects."""

    def _call_curation_llm(self, prompt: str) -> Optional[str]:
        """Call LLM for curation. Uses cached provider instance."""
        try:
            if self._curation_provider is None:
                from llm_providers import AIProviderFactory
                self._curation_provider = AIProviderFactory.create_provider()
                self._curation_provider.add_system_message(
                    "You are a memory curation assistant. Respond ONLY with valid JSON. No markdown, no explanation outside the JSON."
                )
            else:
                # Reset history but reuse provider connection
                self._curation_provider.add_system_message(
                    "You are a memory curation assistant. Respond ONLY with valid JSON. No markdown, no explanation outside the JSON."
                )

            response = self._curation_provider.send_message(prompt)
            return response

        except Exception as e:
            op_logger.logger.error(f"Curation LLM call failed: {e}")
            return None

    def _parse_curation_response(self, response: str) -> Optional[Dict]:
        """Parse JSON response, handle markdown code fences."""
        # Strip markdown code fences if present
        cleaned = response.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            op_logger.logger.warning(f"Failed to parse curation JSON: {cleaned[:200]}")
            return None

    def _execute_decisions(self, decisions: Dict) -> str:
        """Execute add/promote/demote/delete decisions. Returns summary string."""
        actions = []

        # 1. Add new facts
        new_facts = decisions.get("new_facts", [])
        from memory import MemoryManager
        # We can't import MemoryManager here without circular dependency,
        # so we add facts directly to the learning system
        for nf in new_facts:
            content = nf.get("content", "").strip()
            if not content:
                continue
            # Dedup check
            existing = self.learning_system.learnings["knowledge_base"]["facts"]
            if any(f.get("content", "").lower().strip() == content.lower().strip() for f in existing):
                continue

            # Find max fact ID
            max_id = 0
            for f in existing:
                fid = f.get("id", "")
                if fid.startswith("fact_"):
                    try:
                        num = int(fid.split("_")[1])
                        max_id = max(max_id, num)
                    except (ValueError, IndexError):
                        pass

            new_id = f"fact_{max_id + 1:03d}"
            fact = {
                "id": new_id,
                "category": nf.get("category", "general"),
                "content": content,
                "confidence": nf.get("confidence", 0.8),
                "source": "curation",
                "tier": nf.get("tier", 2),
                "tags": nf.get("tags", []),
                "curation_notes": "Added by AI curator",
                "learned_at": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
                "access_count": 0
            }
            existing.append(fact)
            self.learning_system.learnings["metadata"]["total_facts"] = len(existing)
            actions.append(f"Added fact: {content[:50]}")

        # 2. Core memory updates
        core_updates = decisions.get("core_updates", {})
        if core_updates:
            # Identity updates
            identity = core_updates.get("identity", {})
            for field, value in identity.items():
                if value and field in ("name", "profession", "location"):
                    self.core_memory.set_identity(field, value)
                    actions.append(f"Set identity.{field}={value}")

            # Preference updates
            preferences = core_updates.get("preferences", {})
            for key, value in preferences.items():
                if value:
                    self.core_memory.add_preference(key, value)
                    actions.append(f"Set preference {key}={value}")

            # Project additions
            for proj in core_updates.get("projects_add", []):
                if proj:
                    self.core_memory.add_project(proj)
                    actions.append(f"Added project: {proj}")

            # Important fact additions
            for fact in core_updates.get("facts_add", []):
                if fact:
                    self.core_memory.add_custom_fact(fact)
                    actions.append(f"Added core fact: {fact[:50]}")

        # 3. Promotions (Tier 2 -> Tier 1)
        for promo in decisions.get("promotions", []):
            fact_id = promo.get("fact_id", "")
            for fact in self.learning_system.learnings["knowledge_base"]["facts"]:
                if fact.get("id") == fact_id:
                    fact["tier"] = 1
                    fact["curation_notes"] = f"Promoted: {promo.get('reason', '')}"
                    # Also add to core important_facts
                    self.core_memory.add_custom_fact(fact.get("content", ""))
                    actions.append(f"Promoted {fact_id} to core")
                    break

        # 4. Demotions (Tier 2 -> Tier 4)
        for demo in decisions.get("demotions", []):
            fact_id = demo.get("fact_id", "")
            for fact in self.learning_system.learnings["knowledge_base"]["facts"]:
                if fact.get("id") == fact_id:
                    fact["tier"] = 4
                    fact["curation_notes"] = f"Demoted: {demo.get('reason', '')}"
                    actions.append(f"Demoted {fact_id} to archive")
                    break

        # 5. Deletions
        for fact_id in decisions.get("deletions", []):
            facts = self.learning_system.learnings["knowledge_base"]["facts"]
            original_len = len(facts)
            self.learning_system.learnings["knowledge_base"]["facts"] = [
                f for f in facts if f.get("id") != fact_id
            ]
            if len(self.learning_system.learnings["knowledge_base"]["facts"]) < original_len:
                self.learning_system.learnings["metadata"]["total_facts"] -= 1
                actions.append(f"Deleted {fact_id}")

        # Save all changes
        self.learning_system._save_learnings()

        reasoning = decisions.get("reasoning", "")
        if not actions:
            return f"No changes made. Reason: {reasoning}"

        summary = f"Curation complete ({len(actions)} actions): " + "; ".join(actions)
        if reasoning:
            summary += f"\nReasoning: {reasoning}"
        return summary
