import psutil
import subprocess
import os
from typing import Tuple, List, Dict
from dataclasses import dataclass


@dataclass
class ProcessInfo:
    """Information about a process"""
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    status: str


class ProcessOps:
    """Handle process management operations"""

    @classmethod
    def list_processes(cls) -> Tuple[bool, str, str]:
        """
        List all running processes.

        Returns:
            (success, output, error) tuple with process list
        """
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    info = proc.info
                    processes.append(f"• {info['name']} (PID: {info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if not processes:
                return True, "No processes found", ""

            # Limit to first 30 processes
            output = f"🔧 Running Processes ({len(processes)}):\n" + "\n".join(processes[:30])
            if len(processes) > 30:
                output += f"\n... and {len(processes) - 30} more"

            return True, output, ""

        except Exception as e:
            return False, "", f"Failed to list processes: {str(e)}"

    @classmethod
    def kill_process(cls, identifier: str) -> Tuple[bool, str, str]:
        """
        Kill a process by name or PID.

        Args:
            identifier: Process name or PID

        Returns:
            (success, output, error) tuple
        """
        try:
            # Check if identifier is a PID (numeric)
            if identifier.isdigit():
                pid = int(identifier)
                proc = psutil.Process(pid)
                name = proc.name()
                proc.terminate()
                proc.wait(timeout=5)
                return True, f"✓ Killed process: {name} (PID: {pid})", ""

            # Otherwise, treat as process name
            killed = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if identifier.lower() in proc.info['name'].lower():
                        proc.terminate()
                        killed.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if killed:
                proc_names = ", ".join(killed[:5])
                if len(killed) > 5:
                    proc_names += f" and {len(killed) - 5} more"
                return True, f"✓ Killed {len(killed)} process(es): {proc_names}", ""
            else:
                return False, "", f"No process found matching '{identifier}'"

        except psutil.NoSuchProcess:
            return False, "", f"Process not found: {identifier}"
        except psutil.AccessDenied:
            return False, "", f"Access denied. Process '{identifier}' may require admin privileges"
        except Exception as e:
            return False, "", f"Failed to kill process: {str(e)}"

    @classmethod
    def process_info(cls, identifier: str) -> Tuple[bool, str, str]:
        """
        Get detailed information about a process.

        Args:
            identifier: Process name or PID

        Returns:
            (success, output, error) tuple with process details
        """
        try:
            # Find process
            if identifier.isdigit():
                proc = psutil.Process(int(identifier))
            else:
                # Search by name
                matching = []
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        if identifier.lower() in p.info['name'].lower():
                            matching.append(p)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                if not matching:
                    return False, "", f"No process found matching '{identifier}'"

                proc = matching[0]  # Use first match

            # Get detailed info
            info = proc.as_dict(attrs=['pid', 'name', 'status', 'cpu_percent',
                                       'memory_info', 'num_threads', 'username'])

            memory_mb = info['memory_info'].rss / (1024 * 1024)

            output = f"""🔧 Process Information:
• Name: {info['name']}
• PID: {info['pid']}
• Status: {info['status']}
• CPU: {info['cpu_percent']}%
• Memory: {memory_mb:.1f} MB
• Threads: {info['num_threads']}
• User: {info.get('username', 'N/A')}"""

            return True, output, ""

        except psutil.NoSuchProcess:
            return False, "", f"Process not found: {identifier}"
        except psutil.AccessDenied:
            return False, "", f"Access denied. Process '{identifier}' requires admin privileges"
        except Exception as e:
            return False, "", f"Failed to get process info: {str(e)}"

    @classmethod
    def top_processes(cls, count: int = 5, sort_by: str = 'cpu') -> Tuple[bool, str, str]:
        """
        Get top processes by CPU or memory usage.

        Args:
            count: Number of top processes to show
            sort_by: 'cpu' or 'memory'

        Returns:
            (success, output, error) tuple
        """
        try:
            processes = []

            # Collect process info
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
                try:
                    info = proc.info
                    memory_mb = info['memory_info'].rss / (1024 * 1024)
                    processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'cpu': proc.cpu_percent(interval=0.1),
                        'memory': memory_mb
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort
            if sort_by == 'memory':
                processes.sort(key=lambda x: x['memory'], reverse=True)
                metric = 'Memory'
            else:
                processes.sort(key=lambda x: x['cpu'], reverse=True)
                metric = 'CPU'

            # Format output
            top = processes[:count]
            if not top:
                return True, "No processes found", ""

            output = f"🔧 Top {count} Processes by {metric}:\n"
            for p in top:
                output += f"• {p['name']} - CPU: {p['cpu']:.1f}%, Memory: {p['memory']:.1f} MB (PID: {p['pid']})\n"

            return True, output.strip(), ""

        except Exception as e:
            return False, "", f"Failed to get top processes: {str(e)}"

    @classmethod
    def start_process(cls, command: str) -> Tuple[bool, str, str]:
        """
        Start a new process.

        Args:
            command: Command to execute

        Returns:
            (success, output, error) tuple
        """
        try:
            # Use subprocess to start the process
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            return True, f"✓ Started process (PID: {proc.pid}): {command}", ""

        except Exception as e:
            return False, "", f"Failed to start process: {str(e)}"

    @classmethod
    def process_exists(cls, identifier: str) -> Tuple[bool, str, str]:
        """
        Check if a process exists.

        Args:
            identifier: Process name or PID

        Returns:
            (success, output, error) tuple with existence status
        """
        try:
            # Check by PID
            if identifier.isdigit():
                exists = psutil.pid_exists(int(identifier))
                if exists:
                    return True, f"✓ Process PID {identifier} exists", ""
                else:
                    return True, f"Process PID {identifier} does not exist", ""

            # Check by name
            found = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if identifier.lower() in proc.info['name'].lower():
                        found.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if found:
                return True, f"✓ Found {len(found)} process(es): {', '.join(found[:3])}", ""
            else:
                return True, f"Process '{identifier}' not found", ""

        except Exception as e:
            return False, "", f"Failed to check process: {str(e)}"

    @classmethod
    def set_priority(cls, identifier: str, priority: str) -> Tuple[bool, str, str]:
        """
        Set process priority (Windows).

        Args:
            identifier: Process name or PID
            priority: Priority level (low, normal, high, realtime)

        Returns:
            (success, output, error) tuple
        """
        try:
            # Map priority names to psutil constants
            priority_map = {
                'low': psutil.BELOW_NORMAL_PRIORITY_CLASS,
                'normal': psutil.NORMAL_PRIORITY_CLASS,
                'high': psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                'realtime': psutil.REALTIME_PRIORITY_CLASS
            }

            if priority.lower() not in priority_map:
                return False, "", f"Invalid priority. Use: low, normal, high, realtime"

            priority_class = priority_map[priority.lower()]

            # Find process
            if identifier.isdigit():
                proc = psutil.Process(int(identifier))
            else:
                matching = []
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        if identifier.lower() in p.info['name'].lower():
                            matching.append(p)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                if not matching:
                    return False, "", f"No process found matching '{identifier}'"

                proc = matching[0]

            # Set priority
            proc.nice(priority_class)
            return True, f"✓ Set priority to '{priority}' for: {proc.name()} (PID: {proc.pid})", ""

        except psutil.NoSuchProcess:
            return False, "", f"Process not found: {identifier}"
        except psutil.AccessDenied:
            return False, "", f"Access denied. Changing priority may require admin privileges"
        except Exception as e:
            return False, "", f"Failed to set priority: {str(e)}"

    @classmethod
    def system_stats(cls) -> Tuple[bool, str, str]:
        """
        Get overall system statistics.

        Returns:
            (success, output, error) tuple with system stats
        """
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            # Memory
            memory = psutil.virtual_memory()
            memory_used_gb = memory.used / (1024 ** 3)
            memory_total_gb = memory.total / (1024 ** 3)

            # Disk
            disk = psutil.disk_usage('/')
            disk_used_gb = disk.used / (1024 ** 3)
            disk_total_gb = disk.total / (1024 ** 3)

            # Process count
            process_count = len(psutil.pids())

            output = f"""💻 System Statistics:
• CPU: {cpu_percent}% ({cpu_count} cores)
• Memory: {memory_used_gb:.1f} / {memory_total_gb:.1f} GB ({memory.percent}%)
• Disk: {disk_used_gb:.1f} / {disk_total_gb:.1f} GB ({disk.percent}%)
• Processes: {process_count}"""

            return True, output, ""

        except Exception as e:
            return False, "", f"Failed to get system stats: {str(e)}"
