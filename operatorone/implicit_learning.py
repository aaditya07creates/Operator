import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from memory import MemoryManager


class ImplicitLearner:
    """Automatically extracts knowledge from conversations"""

    # Preference patterns
    PREFERENCE_PATTERNS = [
        (r'\b(?:I|i)\s+prefer\s+([A-Za-z0-9\s]+?)(?:\s+(?:over|to|than)\s+([A-Za-z0-9\s]+))?(?:\.|,|$)', 0.9),
        (r'\b(?:I|i)\s+like\s+(?:using\s+)?([A-Za-z0-9\s]+?)(?:\s+(?:better|more))?(?:\.|,|$)', 0.8),
        (r'\b(?:I|i)\s+always\s+use\s+([A-Za-z0-9\s]+?)(?:\.|,|$)', 0.9),
        (r'\b(?:I|i)\s+usually\s+(?:use|open)\s+([A-Za-z0-9\s]+?)(?:\.|,|$)', 0.7),
        (r'\bmy\s+(?:favorite|preferred)\s+(.+?)\s+is\s+([A-Za-z0-9\s]+?)(?:\.|,|$)', 0.85),
    ]

    # Personal fact patterns
    PERSONAL_FACT_PATTERNS = [
        (r'\b(?:I|i)\'?m\s+working\s+on\s+(.+?)(?:\.|,|$)', 0.8, "currently_working_on"),
        (r'\bmy\s+project\s+(?:is\s+)?(?:called\s+)?([A-Za-z0-9\s]+?)(?:\.|,|$)', 0.85, "project_name"),
        (r'\b(?:I|i)\'?m\s+a\s+(.+?)\s+(?:developer|engineer|programmer)(?:\.|,|$)', 0.9, "profession"),
        (r'\b(?:I|i)\s+(?:live|am)\s+in\s+([A-Za-z\s]+?)(?:\.|,|$)', 0.7, "location"),
        (r'\bmy\s+(?:company|employer|job)\s+(?:is\s+)?([A-Za-z0-9\s]+?)(?:\.|,|$)', 0.8, "company"),
    ]

    # Technical knowledge patterns
    TECHNICAL_PATTERNS = [
        (r'(?:using|with)\s+([A-Za-z0-9.]+)\s+(?:version\s+)?(\d+\.?\d*\.?\d*)', 0.7, "version"),
        (r'(?:installed|have)\s+([A-Za-z0-9\s]+?)\s+(?:on my|in my)(?:\.|,|$)', 0.6, "installed_software"),
    ]

    def __init__(self, memory: MemoryManager):
        """
        Initialize implicit learner.

        Args:
            memory: MemoryManager instance for storing learned knowledge
        """
        self.memory = memory

    def analyze_message(
        self,
        user_msg: str,
        ai_response: Optional[str] = None,
        result: Optional[Dict] = None
    ) -> Dict:
        """
        Analyze a conversation turn and extract knowledge.

        Args:
            user_msg: User's message
            ai_response: AI's response
            result: Execution result (success/failure, commands, etc.)

        Returns:
            Dictionary with learned items: {
                'preferences': [...],
                'personal_facts': [...],
                'technical_facts': [...],
                'total_learned': 0
            }
        """
        learned = {
            'preferences': [],
            'personal_facts': [],
            'technical_facts': [],
            'total_learned': 0
        }

        # Extract preferences
        preferences = self._extract_preferences(user_msg)
        for pref_type, value, confidence in preferences:
            fact_id = self.memory.remember_fact(
                category="personal",
                content=f"User prefers {value} for {pref_type}" if pref_type else f"User prefers {value}",
                confidence=confidence,
                source="conversation",
                tier=2,
                tags=["preference", pref_type or "general"]
            )
            learned['preferences'].append({
                'type': pref_type or 'general',
                'value': value,
                'fact_id': fact_id
            })

        # Extract personal facts
        personal_facts = self._extract_personal_facts(user_msg)
        for fact_type, content, confidence in personal_facts:
            fact_id = self.memory.remember_fact(
                category="personal",
                content=content,
                confidence=confidence,
                source="conversation",
                tier=2,
                tags=["personal", fact_type]
            )
            learned['personal_facts'].append({
                'type': fact_type,
                'content': content,
                'fact_id': fact_id
            })

        # Extract technical knowledge from successful executions
        if result and result.get('success'):
            tech_facts = self._extract_technical_knowledge(user_msg, ai_response, result)
            for content, confidence in tech_facts:
                fact_id = self.memory.remember_fact(
                    category="technical",
                    content=content,
                    confidence=confidence,
                    source="experience",
                    tier=2,
                    tags=["technical", "learned"]
                )
                learned['technical_facts'].append({
                    'content': content,
                    'fact_id': fact_id
                })

        learned['total_learned'] = (
            len(learned['preferences']) +
            len(learned['personal_facts']) +
            len(learned['technical_facts'])
        )

        return learned

    def _extract_preferences(self, text: str) -> List[Tuple[Optional[str], str, float]]:
        """
        Extract user preferences from text.

        Returns:
            List of (preference_type, value, confidence) tuples
        """
        preferences = []

        for pattern, confidence in self.PREFERENCE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 1:
                    value = match.group(1).strip()
                    pref_type = match.group(2).strip() if len(match.groups()) >= 2 and match.group(2) else None

                    # Clean up value
                    value = self._clean_extracted_text(value)

                    if value and len(value) > 2:
                        preferences.append((pref_type, value, confidence))

        return preferences

    def _extract_personal_facts(self, text: str) -> List[Tuple[str, str, float]]:
        """
        Extract personal facts from text.

        Returns:
            List of (fact_type, content, confidence) tuples
        """
        facts = []

        for pattern, confidence, fact_type in self.PERSONAL_FACT_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                value = match.group(1).strip()
                value = self._clean_extracted_text(value)

                if value and len(value) > 2:
                    # Format as natural sentence
                    if fact_type == "currently_working_on":
                        content = f"User is working on {value}"
                    elif fact_type == "project_name":
                        content = f"User's project is called {value}"
                    elif fact_type == "profession":
                        content = f"User is a {value} developer"
                    elif fact_type == "location":
                        content = f"User lives in {value}"
                    elif fact_type == "company":
                        content = f"User works at {value}"
                    else:
                        content = value

                    facts.append((fact_type, content, confidence))

        return facts

    def _extract_technical_knowledge(
        self,
        user_msg: str,
        ai_response: Optional[str],
        result: Dict
    ) -> List[Tuple[str, float]]:
        """
        Extract technical knowledge from successful command executions.

        Returns:
            List of (content, confidence) tuples
        """
        facts = []

        # If successful, learn what worked
        if result.get('success'):
            commands = result.get('commands', [])

            # Learn about app launches
            for cmd in commands:
                # Detect app launches
                app_match = re.search(r'(?:start|open)\s+([a-zA-Z0-9]+)', cmd, re.IGNORECASE)
                if app_match:
                    app_name = app_match.group(1)
                    facts.append((
                        f"App '{app_name}' can be launched with command: {cmd[:60]}",
                        0.7
                    ))

                # Detect PowerShell patterns
                if cmd.startswith('powershell'):
                    if 'Get-AppxPackage' in cmd:
                        facts.append((
                            "UWP apps can be launched using PowerShell Get-AppxPackage",
                            0.8
                        ))

        # Extract technical patterns from user message
        for pattern, confidence, fact_type in self.TECHNICAL_PATTERNS:
            matches = re.finditer(pattern, user_msg, re.IGNORECASE)
            for match in matches:
                if fact_type == "version":
                    software = match.group(1).strip()
                    version = match.group(2).strip()
                    facts.append((
                        f"User has {software} version {version}",
                        confidence
                    ))
                elif fact_type == "installed_software":
                    software = match.group(1).strip()
                    facts.append((
                        f"User has {software} installed",
                        confidence
                    ))

        return facts

    def _clean_extracted_text(self, text: str) -> str:
        """Clean up extracted text"""
        # Remove extra whitespace
        text = ' '.join(text.split())

        # Remove trailing punctuation
        text = text.rstrip('.,!?;:')

        # Limit length
        if len(text) > 100:
            text = text[:100]

        return text.strip()

    def should_learn_from_interaction(
        self,
        user_msg: str,
        result: Optional[Dict] = None
    ) -> bool:
        """
        Determine if we should try to learn from this interaction.

        Returns:
            True if interaction contains learnable information
        """
        msg_lower = user_msg.lower().strip()

        # Don't learn from very short messages
        if len(msg_lower) < 5:
            return False

        # Don't learn from simple action requests
        action_words = ['open', 'close', 'start', 'run', 'launch', 'search', 'find', 'delete',
                       'move', 'copy', 'create', 'show', 'list', 'get', 'set', 'play',
                       'i wanna', 'i want to', 'can you', 'could you', 'please']
        if any(msg_lower.startswith(word) or f' {word} ' in f' {msg_lower} ' for word in action_words):
            # This is likely just an action request, not something to learn
            return False

        # Learn from EXPLICIT preference statements (not just "like")
        if any(phrase in msg_lower for phrase in ['i prefer', 'i always use', 'my favorite',
                                                    'i usually use', 'prefer using']):
            return True

        # Learn from personal/project information (but not casual mentions)
        if any(phrase in msg_lower for phrase in ["i'm working on", "my project is",
                                                    "i'm a developer", "i work at",
                                                    "my company is"]):
            return True

        # Don't learn from everything else - be conservative
        return False
