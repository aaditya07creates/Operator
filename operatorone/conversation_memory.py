from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import Counter
import uuid


class ConversationMemory:
    """Manages three-tier conversation memory"""

    def __init__(self, learning_system):
        """
        Initialize conversation memory.

        Args:
            learning_system: LearningSystem instance for persistence
        """
        self.learning_system = learning_system
        self.current_session_id = None
        self.session_start_time = None
        self.session_messages = []  # Working memory (current session)
        self.session_commands = []  # Commands in current session

    def start_session(self) -> str:
        """
        Start a new conversation session.

        Returns:
            Session ID
        """
        # End previous session if exists
        if self.current_session_id:
            self.end_session()

        # Create new session
        self.current_session_id = f"sess_{uuid.uuid4().hex[:8]}"
        self.session_start_time = datetime.now()
        self.session_messages = []
        self.session_commands = []

        return self.current_session_id

    def end_session(self):
        """End current session and save summary"""
        if not self.current_session_id:
            return

        # Create session summary
        summary = self._create_session_summary()

        # Save to learning system
        sessions = self.learning_system.learnings["conversation_memory"]["sessions"]
        sessions.append(summary)

        # Keep only last 20 sessions
        if len(sessions) > 20:
            self.learning_system.learnings["conversation_memory"]["sessions"] = sessions[-20:]

        self.learning_system._save_learnings()

        # Reset session
        self.current_session_id = None
        self.session_start_time = None
        self.session_messages = []
        self.session_commands = []

    def add_interaction(
        self,
        user_message: str,
        ai_response: str,
        commands: List[str],
        success: bool
    ):
        """
        Add an interaction to current session.

        Args:
            user_message: User's input
            ai_response: AI's response
            commands: Commands executed
            success: Whether execution succeeded
        """
        # Start session if not started
        if not self.current_session_id:
            self.start_session()

        # Add to working memory
        self.session_messages.append({
            'user': user_message,
            'ai': ai_response[:200],  # Truncate to 200 chars
            'timestamp': datetime.now().isoformat(),
            'success': success
        })

        # Track commands
        self.session_commands.extend(commands)

        # Limit working memory to last 15 interactions
        if len(self.session_messages) > 15:
            self.session_messages = self.session_messages[-15:]

    def get_conversation_context(self, query: Optional[str] = None) -> str:
        """
        Get formatted conversation context for AI.

        Combines:
        - Recent session summaries (last 3 sessions)
        - Current session messages (working memory)
        - Relevant long-term memories

        Args:
            query: Optional query to find relevant context

        Returns:
            Formatted context string
        """
        lines = []

        # Recent sessions
        sessions = self.learning_system.learnings["conversation_memory"]["sessions"]
        if sessions:
            recent_sessions = sessions[-3:]  # Last 3 sessions
            if recent_sessions:
                lines.append("**Recent Sessions:**")
                for session in recent_sessions:
                    summary = session.get("summary", "")
                    if summary:
                        lines.append(f"  • {summary}")
                lines.append("")

        # Current session context
        if self.session_messages:
            lines.append("**Current Session:**")
            # Show last 3 interactions
            for msg in self.session_messages[-3:]:
                user_msg = msg['user'][:60]
                lines.append(f"  User: {user_msg}...")
            lines.append("")

        # Long-term important memories
        ltm = self.learning_system.learnings["conversation_memory"]["long_term_memory"]
        high_importance = [m for m in ltm if m.get("significance") == "high"]
        if high_importance:
            lines.append("**Important Past Conversations:**")
            for memory in high_importance[-3:]:  # Last 3 important memories
                lines.append(f"  • {memory.get('summary')}")
            lines.append("")

        return "\n".join(lines) if lines else ""

    def _create_session_summary(self) -> Dict:
        """Create summary of current session"""
        if not self.session_messages:
            return {
                "session_id": self.current_session_id,
                "start_time": self.session_start_time.isoformat() if self.session_start_time else "",
                "end_time": datetime.now().isoformat(),
                "summary": "Empty session",
                "key_topics": [],
                "commands_executed": 0,
                "success_rate": 0.0
            }

        # Extract key topics from user messages
        key_topics = self._extract_key_topics()

        # Calculate success rate
        successful = sum(1 for msg in self.session_messages if msg.get('success', False))
        total = len(self.session_messages)
        success_rate = successful / total if total > 0 else 0.0

        # Create concise summary
        summary = self._create_concise_summary(key_topics)

        return {
            "session_id": self.current_session_id,
            "start_time": self.session_start_time.isoformat() if self.session_start_time else "",
            "end_time": datetime.now().isoformat(),
            "summary": summary,
            "key_topics": key_topics[:5],  # Top 5 topics
            "commands_executed": len(self.session_commands),
            "success_rate": success_rate
        }

    def _extract_key_topics(self) -> List[str]:
        """Extract key topics from session messages"""
        # Common stopwords
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'open', 'close', 'start', 'run', 'show', 'me', 'my', 'i', 'you', 'please'
        }

        # Collect all words from user messages
        all_words = []
        for msg in self.session_messages:
            words = msg['user'].lower().split()
            # Filter stopwords and short words
            filtered = [w.strip('.,!?') for w in words if len(w) > 3 and w.lower() not in stopwords]
            all_words.extend(filtered)

        # Count frequency
        word_counts = Counter(all_words)

        # Return most common topics
        return [word for word, count in word_counts.most_common(10)]

    def _create_concise_summary(self, key_topics: List[str]) -> str:
        """Create a concise summary of the session"""
        if not key_topics:
            return f"Session with {len(self.session_messages)} interactions"

        # Build summary from topics
        topics_str = ", ".join(key_topics[:3])
        return f"Discussed {topics_str} ({len(self.session_messages)} interactions)"

    def is_significant_interaction(
        self,
        user_message: str,
        commands: List[str],
        success: bool
    ) -> bool:
        """
        Determine if an interaction is significant enough for long-term memory.

        Significant interactions:
        - User teaches explicit preferences
        - User provides important personal information
        - Complex multi-step tasks completed successfully
        - User corrects the AI multiple times
        """
        msg_lower = user_message.lower()

        # Explicit teaching
        if any(phrase in msg_lower for phrase in ["i prefer", "always", "never", "important to me"]):
            return True

        # Personal information
        if any(phrase in msg_lower for phrase in ["my name", "i'm a", "i work", "my project"]):
            return True

        # Complex tasks (3+ commands)
        if len(commands) >= 3 and success:
            return True

        return False

    def add_significant_interaction(
        self,
        user_message: str,
        ai_response: str,
        significance: str = "medium"
    ):
        """
        Add a significant interaction to long-term memory.

        Args:
            user_message: User's message
            ai_response: AI's response
            significance: 'high', 'medium', or 'low'
        """
        ltm_id = f"ltm_{uuid.uuid4().hex[:8]}"

        memory = {
            "id": ltm_id,
            "type": "important_conversation",
            "summary": f"User: {user_message[:100]}",
            "date": datetime.now().isoformat(),
            "significance": significance
        }

        self.learning_system.learnings["conversation_memory"]["long_term_memory"].append(memory)

        # Keep only last 50 long-term memories
        ltm_list = self.learning_system.learnings["conversation_memory"]["long_term_memory"]
        if len(ltm_list) > 50:
            self.learning_system.learnings["conversation_memory"]["long_term_memory"] = ltm_list[-50:]

        self.learning_system._save_learnings()

    def get_session_count(self) -> int:
        """Get total number of sessions"""
        return len(self.learning_system.learnings["conversation_memory"]["sessions"])

    def get_current_session_info(self) -> Optional[Dict]:
        """Get information about current session"""
        if not self.current_session_id:
            return None

        return {
            "session_id": self.current_session_id,
            "start_time": self.session_start_time.isoformat() if self.session_start_time else "",
            "message_count": len(self.session_messages),
            "commands_executed": len(self.session_commands)
        }
