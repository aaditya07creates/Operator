from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
import re
from collections import Counter


class ContextRetriever:
    """Smart context retrieval with relevance scoring"""

    # Common English stopwords to filter out
    STOPWORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'should', 'could', 'may', 'might', 'can', 'this', 'that',
        'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what',
        'which', 'who', 'when', 'where', 'why', 'how', 'my', 'your', 'his',
        'her', 'its', 'our', 'their', 'me', 'him', 'her', 'us', 'them'
    }

    def __init__(self, learning_system):
        """
        Initialize context retriever.

        Args:
            learning_system: LearningSystem instance to retrieve data from
        """
        self.learning_system = learning_system
        self._keyword_cache = {}

    def get_relevant_facts(
        self,
        query: str,
        limit: int = 10,
        category: Optional[str] = None,
        min_confidence: float = 0.3
    ) -> List[Dict]:
        """
        Get most relevant facts for a query.

        Args:
            query: User query or conversation context
            limit: Maximum number of facts to return (default 10)
            category: Optional category filter (personal|technical|general)
            min_confidence: Minimum confidence threshold (default 0.3)

        Returns:
            List of fact dictionaries, sorted by relevance score
        """
        # Get Tier 2 (active) facts only - Tier 1 is in system prompt, Tier 4 is archived
        all_facts = self.learning_system.learnings.get("knowledge_base", {}).get("facts", [])
        facts = [f for f in all_facts if f.get("tier", 2) == 2]

        if not facts:
            return []

        # Filter by category and confidence
        if category:
            facts = [f for f in facts if f.get("category") == category]
        facts = [f for f in facts if f.get("confidence", 0) >= min_confidence]

        # Extract keywords from query
        query_keywords = self._extract_keywords(query)

        if not query_keywords:
            # No keywords - return most recent high-confidence facts
            return sorted(
                facts,
                key=lambda f: (f.get("confidence", 0), f.get("learned_at", "")),
                reverse=True
            )[:limit]

        # Score each fact
        scored_facts = []
        for fact in facts:
            score = self._calculate_relevance(fact, query_keywords)
            scored_facts.append((score, fact))

        # Sort by score and return top N
        scored_facts.sort(key=lambda x: x[0], reverse=True)
        return [fact for score, fact in scored_facts[:limit]]

    def get_relevant_context_for_ai(
        self,
        query: str,
        limit: int = 10
    ) -> str:
        """
        Get formatted context for AI system prompt.

        Args:
            query: User query
            limit: Maximum facts to include

        Returns:
            Formatted string with user profile, relevant facts, and conversation context
        """
        lines = []

        # User profile
        profile = self.learning_system.learnings.get("user_profile", {})
        if profile.get("name"):
            lines.append(f"**User:** {profile['name']}")

        # Communication preferences
        comm_style = profile.get("communication_style", {})
        if comm_style:
            lines.append(f"**Communication:** {comm_style.get('formality', 'casual')}, {comm_style.get('verbosity', 'concise')}")

        # User interests
        interests = profile.get("interests", [])
        if interests:
            lines.append(f"**Interests:** {', '.join(interests[:5])}")

        # User preferences
        prefs = profile.get("preferences", {})
        if prefs:
            lines.append("\n**Preferences:**")
            for key, value in list(prefs.items())[:5]:
                lines.append(f"  • {key}: {value}")

        # Relevant facts
        facts = self.get_relevant_facts(query, limit=limit)
        if facts:
            lines.append("\n**Relevant Knowledge:**")
            for fact in facts:
                category_emoji = {
                    "personal": "👤",
                    "technical": "💻",
                    "general": "📝"
                }.get(fact.get("category", "general"), "📝")
                confidence = int(fact.get("confidence", 0.5) * 100)
                lines.append(f"  {category_emoji} {fact.get('content')} ({confidence}% confident)")

        # Current conversation context
        context = self.learning_system.learnings.get("conversation_memory", {}).get("current_context", {})
        if context.get("topic"):
            lines.append(f"\n**Current Topic:** {context['topic']}")
        if context.get("active_apps"):
            lines.append(f"**Active Apps:** {', '.join(context['active_apps'])}")

        # Recent long-term memories
        ltm = self.learning_system.learnings.get("conversation_memory", {}).get("long_term_memory", [])
        high_importance = [m for m in ltm if m.get("significance") == "high"]
        if high_importance:
            lines.append("\n**Important Memories:**")
            for memory in sorted(high_importance, key=lambda m: m.get("date", ""), reverse=True)[:3]:
                lines.append(f"  • {memory.get('summary')}")

        return "\n".join(lines) if lines else ""

    def _extract_keywords(self, text: str) -> Set[str]:
        """
        Extract meaningful keywords from text.

        Args:
            text: Input text

        Returns:
            Set of lowercase keywords
        """
        # Check cache
        cache_key = text.lower()[:100]  # Cache first 100 chars
        if cache_key in self._keyword_cache:
            return self._keyword_cache[cache_key]

        # Tokenize - split on non-alphanumeric, keep letters/numbers
        tokens = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())

        # Filter stopwords and short words
        keywords = {
            token for token in tokens
            if token not in self.STOPWORDS and len(token) > 2
        }

        # Cache result
        self._keyword_cache[cache_key] = keywords

        # Limit cache size
        if len(self._keyword_cache) > 100:
            # Remove oldest entries
            for key in list(self._keyword_cache.keys())[:50]:
                del self._keyword_cache[key]

        return keywords

    def _calculate_relevance(
        self,
        fact: Dict,
        query_keywords: Set[str]
    ) -> float:
        """
        Calculate relevance score for a fact.

        Score = keyword_match * 0.5 + recency * 0.3 + frequency * 0.2 + confidence * 0.1

        Args:
            fact: Fact dictionary
            query_keywords: Set of query keywords

        Returns:
            Relevance score (0.0 - 1.0)
        """
        # 1. Keyword matching score (0.0 - 1.0)
        fact_keywords = self._extract_keywords(fact.get("content", ""))
        if not fact_keywords:
            keyword_score = 0.0
        else:
            matching_keywords = fact_keywords & query_keywords
            keyword_score = len(matching_keywords) / max(len(query_keywords), 1)

        # 2. Recency score (0.0 - 1.0)
        recency_score = self._calculate_recency_score(fact)

        # 3. Access frequency score (0.0 - 1.0)
        frequency_score = self._calculate_frequency_score(fact)

        # 4. Confidence score (already 0.0 - 1.0)
        confidence_score = fact.get("confidence", 0.5)

        # Weighted combination
        total_score = (
            keyword_score * 0.5 +
            recency_score * 0.3 +
            frequency_score * 0.1 +
            confidence_score * 0.1
        )

        return min(1.0, max(0.0, total_score))

    def _calculate_recency_score(self, fact: Dict) -> float:
        """
        Calculate recency score based on last access time.

        Recently accessed facts score higher.
        Score decays over 30 days.
        """
        try:
            last_accessed = fact.get("last_accessed", fact.get("learned_at", ""))
            if not last_accessed:
                return 0.0

            last_time = datetime.fromisoformat(last_accessed)
            now = datetime.now()
            age_days = (now - last_time).total_seconds() / 86400  # Convert to days

            # Decay over 30 days
            if age_days <= 0:
                return 1.0
            elif age_days >= 30:
                return 0.1
            else:
                # Linear decay from 1.0 to 0.1
                return 1.0 - (age_days / 30) * 0.9

        except Exception:
            return 0.5  # Default to middle score if parsing fails

    def _calculate_frequency_score(self, fact: Dict) -> float:
        """
        Calculate frequency score based on access count.

        Frequently accessed facts score higher.
        Normalized to 0.0 - 1.0 range.
        """
        access_count = fact.get("access_count", 0)

        # Normalize using logarithmic scale
        # 0 accesses = 0.0
        # 1 access = 0.3
        # 5 accesses = 0.6
        # 10+ accesses = 1.0
        if access_count == 0:
            return 0.0
        elif access_count >= 10:
            return 1.0
        else:
            # Logarithmic scaling
            import math
            return min(1.0, math.log(access_count + 1) / math.log(11))

    def clear_cache(self):
        """Clear keyword extraction cache"""
        self._keyword_cache.clear()
