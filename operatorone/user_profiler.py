import re
from typing import Dict, List, Optional
from datetime import datetime, time
from collections import Counter, defaultdict
from memory import MemoryManager


class UserProfileBuilder:
    """Builds user profile from interaction patterns"""

    # Formal language indicators
    FORMAL_INDICATORS = [
        'please', 'kindly', 'would you', 'could you', 'may i',
        'thank you', 'thanks', 'appreciate', 'regards'
    ]

    # Casual language indicators
    CASUAL_INDICATORS = [
        'hey', 'yo', 'sup', 'gonna', 'wanna', 'lemme', 'yeah', 'yep',
        'nope', 'cool', 'awesome', 'lol', 'lmao', 'btw', 'tbh'
    ]

    # Topic keywords (for interest detection)
    TOPIC_KEYWORDS = {
        'programming': ['code', 'python', 'java', 'javascript', 'programming', 'debug', 'function', 'class'],
        'web_development': ['website', 'html', 'css', 'react', 'vue', 'angular', 'frontend', 'backend'],
        'data_science': ['data', 'analysis', 'pandas', 'numpy', 'machine learning', 'ai', 'model'],
        'gaming': ['game', 'gaming', 'steam', 'epic', 'xbox', 'playstation', 'fortnite'],
        'productivity': ['notion', 'obsidian', 'evernote', 'calendar', 'todo', 'task'],
        'media': ['spotify', 'netflix', 'youtube', 'music', 'video', 'movie', 'show'],
        'design': ['photoshop', 'illustrator', 'figma', 'design', 'graphics', 'ui', 'ux'],
        'system_admin': ['docker', 'kubernetes', 'server', 'deploy', 'database', 'sql', 'api']
    }

    def __init__(self, memory: MemoryManager):
        """
        Initialize user profiler.

        Args:
            memory: MemoryManager instance
        """
        self.memory = memory
        self._interaction_count = 0
        self._message_lengths = []
        self._command_times = defaultdict(list)  # app -> [timestamps]

    def update_profile(self, interaction_data: Dict):
        """
        Update user profile based on interaction.

        Args:
            interaction_data: {
                'user_message': str,
                'commands': List[str],
                'timestamp': str (ISO format),
                'success': bool
            }
        """
        self._interaction_count += 1
        user_msg = interaction_data.get('user_message', '')
        commands = interaction_data.get('commands', [])
        timestamp = interaction_data.get('timestamp', datetime.now().isoformat())

        # Update communication style every 5 interactions
        if self._interaction_count % 5 == 0:
            self._update_communication_style(user_msg)

        # Update interests every 3 interactions
        if self._interaction_count % 3 == 0:
            self._update_interests(user_msg, commands)

        # Track habits
        if commands and interaction_data.get('success'):
            self._track_habits(commands, timestamp)

    def _update_communication_style(self, message: str):
        """Analyze and update communication style"""
        if not message or len(message.strip()) < 10:
            return

        msg_lower = message.lower()

        # Detect formality
        formal_count = sum(1 for indicator in self.FORMAL_INDICATORS if indicator in msg_lower)
        casual_count = sum(1 for indicator in self.CASUAL_INDICATORS if indicator in msg_lower)

        if formal_count > casual_count:
            formality = "formal"
        elif casual_count > formal_count:
            formality = "casual"
        else:
            formality = "casual"  # Default to casual

        # Detect verbosity based on message length
        self._message_lengths.append(len(message))
        if len(self._message_lengths) > 10:
            self._message_lengths = self._message_lengths[-10:]  # Keep last 10

        avg_length = sum(self._message_lengths) / len(self._message_lengths)
        if avg_length > 100:
            verbosity = "detailed"
        else:
            verbosity = "concise"

        # Update profile
        self.memory.update_profile('communication_style', {
            'formality': formality,
            'verbosity': verbosity
        })

    def _update_interests(self, message: str, commands: List[str]):
        """Detect and update user interests"""
        if not message:
            return

        msg_lower = message.lower()
        detected_topics = []

        # Check each topic category
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            # Count keyword matches
            matches = sum(1 for keyword in keywords if keyword in msg_lower)
            if matches > 0:
                detected_topics.append((topic, matches))

        # Also detect from commands
        for cmd in commands:
            cmd_lower = cmd.lower()
            for topic, keywords in self.TOPIC_KEYWORDS.items():
                if any(keyword in cmd_lower for keyword in keywords):
                    detected_topics.append((topic, 1))

        # Get current interests
        profile = self.memory.get_user_profile()
        current_interests = profile.get('interests', [])

        # Add new high-confidence topics (2+ matches)
        for topic, matches in detected_topics:
            if matches >= 2 and topic not in current_interests:
                current_interests.append(topic)

        # Keep only top 10 interests
        if len(current_interests) > 10:
            current_interests = current_interests[:10]

        # Update profile
        self.memory.update_profile('interests', current_interests)

    def _track_habits(self, commands: List[str], timestamp_str: str):
        """Track usage habits and patterns"""
        try:
            dt = datetime.fromisoformat(timestamp_str)
        except:
            return

        # Extract apps from commands
        apps = []
        for cmd in commands:
            # Look for app names in common patterns
            matches = re.findall(r'(?:start|open)\s+([a-zA-Z0-9]+)', cmd, re.IGNORECASE)
            apps.extend(matches)

        # Track command times for each app
        for app in apps:
            self._command_times[app].append(dt)

        # Detect time-based habits (every 20 interactions)
        if self._interaction_count % 20 == 0:
            self._detect_time_habits()

    def _detect_time_habits(self):
        """Detect time-based usage patterns"""
        profile = self.memory.get_user_profile()
        habits = profile.get('habits', {})

        for app, timestamps in self._command_times.items():
            if len(timestamps) < 3:
                continue

            # Group by hour
            hours = Counter(dt.hour for dt in timestamps)
            most_common_hour = hours.most_common(1)[0] if hours else None

            if most_common_hour and most_common_hour[1] >= 3:
                hour = most_common_hour[0]
                habit_key = f"opens_{app}_at_{hour:02d}00"
                habits[habit_key] = f"Often opens {app} around {hour:02d}:00"

        # Update profile
        self.memory.update_profile('habits', habits)

    def get_profile_summary(self) -> str:
        """Get human-readable profile summary"""
        profile = self.memory.get_user_profile()

        lines = ["=" * 60, "USER PROFILE", "=" * 60, ""]

        # Name
        if profile.get('name'):
            lines.append(f"Name: {profile['name']}")
            lines.append("")

        # Communication style
        comm = profile.get('communication_style', {})
        if comm:
            lines.append("Communication Style:")
            lines.append(f"  Formality: {comm.get('formality', 'unknown')}")
            lines.append(f"  Verbosity: {comm.get('verbosity', 'unknown')}")
            lines.append("")

        # Preferences
        prefs = profile.get('preferences', {})
        if prefs:
            lines.append("Preferences:")
            for key, value in prefs.items():
                lines.append(f"  • {key}: {value}")
            lines.append("")

        # Interests
        interests = profile.get('interests', [])
        if interests:
            lines.append(f"Interests ({len(interests)}):")
            for interest in interests:
                lines.append(f"  • {interest.replace('_', ' ').title()}")
            lines.append("")

        # Habits
        habits = profile.get('habits', {})
        if habits:
            lines.append(f"Habits ({len(habits)}):")
            for habit_desc in habits.values():
                lines.append(f"  • {habit_desc}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def detect_name_from_message(self, message: str) -> Optional[str]:
        """
        Try to detect user's name from message.

        Looks for patterns like:
        - "My name is X"
        - "I'm X"
        - "Call me X"
        """
        patterns = [
            r'my name is ([A-Z][a-z]+)',
            r"i'm ([A-Z][a-z]+)",
            r'call me ([A-Z][a-z]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                name = match.group(1).strip()
                if 2 <= len(name) <= 20:  # Sanity check
                    return name

        return None
