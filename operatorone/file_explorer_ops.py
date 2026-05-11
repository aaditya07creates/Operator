
import os
import shutil
import pathlib
import time
from typing import Tuple, List, Dict, Optional
from datetime import datetime
from logger_config import op_logger


class FileExplorerOps:
    """File explorer operations with smart search and management"""

    @classmethod
    def search_files(cls, pattern: str, search_path: str = None, recursive: bool = True) -> Tuple[bool, str, str]:
        """
        Smart file search with pattern matching.

        Args:
            pattern: Search pattern (e.g., "*.py", "document*", "test*.txt")
            search_path: Path to search in (defaults to user home)
            recursive: Search subdirectories

        Returns:
            (success, message, details)
        """
        try:
            if not search_path:
                search_path = str(pathlib.Path.home())

            search_path = pathlib.Path(search_path).expanduser().resolve()

            if not search_path.exists():
                return False, f"Path does not exist: {search_path}", ""

            op_logger.logger.info(f"🔍 Searching for '{pattern}' in {search_path}")

            matches = []

            if recursive:
                # Recursive search
                for file_path in search_path.rglob(pattern):
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        size_str = cls._format_size(size)
                        rel_path = file_path.relative_to(search_path)
                        matches.append(f"  📄 {rel_path} ({size_str})")
            else:
                # Non-recursive search
                for file_path in search_path.glob(pattern):
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        size_str = cls._format_size(size)
                        matches.append(f"  📄 {file_path.name} ({size_str})")

            if matches:
                result = f"✓ Found {len(matches)} file(s):\n" + "\n".join(matches[:50])
                if len(matches) > 50:
                    result += f"\n... and {len(matches) - 50} more files"

                details = f"Search: {pattern} | Path: {search_path} | Results: {len(matches)}"
                return True, result, details
            else:
                return True, f"No files found matching '{pattern}' in {search_path}", ""

        except PermissionError as e:
            return False, f"Permission denied: {search_path}", str(e)
        except Exception as e:
            op_logger.logger.error(f"File search failed: {e}")
            return False, f"Search failed: {str(e)}", ""

    @classmethod
    def get_storage_usage(cls, path: str = None) -> Tuple[bool, str, str]:
        """
        Get storage usage statistics for a path.

        Args:
            path: Path to analyze (defaults to user home)

        Returns:
            (success, message, details)
        """
        try:
            if not path:
                path = str(pathlib.Path.home())

            path = pathlib.Path(path).expanduser().resolve()

            if not path.exists():
                return False, f"Path does not exist: {path}", ""

            op_logger.logger.info(f"📊 Analyzing storage for {path}")

            total_size = 0
            file_count = 0
            folder_count = 0

            if path.is_file():
                # Single file
                total_size = path.stat().st_size
                file_count = 1
            else:
                # Directory
                for item in path.rglob('*'):
                    try:
                        if item.is_file():
                            total_size += item.stat().st_size
                            file_count += 1
                        elif item.is_dir():
                            folder_count += 1
                    except (PermissionError, OSError):
                        # Skip inaccessible files
                        continue

            size_str = cls._format_size(total_size)

            result = f"""📊 Storage Usage for {path.name}:
  Size: {size_str}
  Files: {file_count:,}
  Folders: {folder_count:,}
  Path: {path}"""

            details = f"Size: {size_str} | Files: {file_count} | Folders: {folder_count}"
            return True, result, details

        except PermissionError:
            return False, f"Permission denied: {path}", ""
        except Exception as e:
            op_logger.logger.error(f"Storage analysis failed: {e}")
            return False, f"Storage analysis failed: {str(e)}", ""

    @classmethod
    def create_directory(cls, path: str, nested: bool = False) -> Tuple[bool, str, str]:
        """
        Create a directory (single or nested).

        Args:
            path: Directory path to create
            nested: If True, creates all intermediate directories (mkdir -p)

        Returns:
            (success, message, details)
        """
        try:
            path = pathlib.Path(path).expanduser().resolve()

            if path.exists():
                return False, f"Path already exists: {path}", ""

            if nested:
                path.mkdir(parents=True, exist_ok=False)
                op_logger.logger.info(f"✓ Created nested directory: {path}")
                return True, f"✓ Created nested directory: {path}", f"Type: nested | Path: {path}"
            else:
                path.mkdir(exist_ok=False)
                op_logger.logger.info(f"✓ Created directory: {path}")
                return True, f"✓ Created directory: {path}", f"Type: single | Path: {path}"

        except FileExistsError:
            return False, f"Directory already exists: {path}", ""
        except PermissionError:
            return False, f"Permission denied: {path}", ""
        except Exception as e:
            op_logger.logger.error(f"Directory creation failed: {e}")
            return False, f"Failed to create directory: {str(e)}", ""

    @classmethod
    def move_item(cls, source: str, destination: str) -> Tuple[bool, str, str]:
        """
        Move file or folder to new location.

        Args:
            source: Source path
            destination: Destination path

        Returns:
            (success, message, details)
        """
        try:
            source = pathlib.Path(source).expanduser().resolve()
            destination = pathlib.Path(destination).expanduser().resolve()

            if not source.exists():
                return False, f"Source does not exist: {source}", ""

            if destination.exists():
                return False, f"Destination already exists: {destination}", ""

            # Determine if file or folder
            item_type = "file" if source.is_file() else "folder"

            shutil.move(str(source), str(destination))

            op_logger.logger.info(f"✓ Moved {item_type}: {source} → {destination}")
            return True, f"✓ Moved {item_type}: {source.name} → {destination}", f"Type: {item_type} | From: {source} | To: {destination}"

        except PermissionError:
            return False, f"Permission denied", ""
        except Exception as e:
            op_logger.logger.error(f"Move failed: {e}")
            return False, f"Move failed: {str(e)}", ""

    @classmethod
    def rename_item(cls, old_path: str, new_name: str) -> Tuple[bool, str, str]:
        """
        Rename file or folder.

        Args:
            old_path: Current path
            new_name: New name (not full path, just the name)

        Returns:
            (success, message, details)
        """
        try:
            old_path = pathlib.Path(old_path).expanduser().resolve()

            if not old_path.exists():
                return False, f"Path does not exist: {old_path}", ""

            # New path is in same directory with new name
            new_path = old_path.parent / new_name

            if new_path.exists():
                return False, f"Target name already exists: {new_name}", ""

            item_type = "file" if old_path.is_file() else "folder"

            old_path.rename(new_path)

            op_logger.logger.info(f"✓ Renamed {item_type}: {old_path.name} → {new_name}")
            return True, f"✓ Renamed {item_type}: {old_path.name} → {new_name}", f"Type: {item_type} | Old: {old_path.name} | New: {new_name}"

        except PermissionError:
            return False, f"Permission denied", ""
        except Exception as e:
            op_logger.logger.error(f"Rename failed: {e}")
            return False, f"Rename failed: {str(e)}", ""

    @classmethod
    def copy_item(cls, source: str, destination: str) -> Tuple[bool, str, str]:
        """
        Copy file or folder to new location.

        Args:
            source: Source path
            destination: Destination path

        Returns:
            (success, message, details)
        """
        try:
            source = pathlib.Path(source).expanduser().resolve()
            destination = pathlib.Path(destination).expanduser().resolve()

            if not source.exists():
                return False, f"Source does not exist: {source}", ""

            if destination.exists():
                return False, f"Destination already exists: {destination}", ""

            if source.is_file():
                shutil.copy2(str(source), str(destination))
                item_type = "file"
            else:
                shutil.copytree(str(source), str(destination))
                item_type = "folder"

            op_logger.logger.info(f"✓ Copied {item_type}: {source} → {destination}")
            return True, f"✓ Copied {item_type}: {source.name} → {destination}", f"Type: {item_type} | From: {source} | To: {destination}"

        except PermissionError:
            return False, f"Permission denied", ""
        except Exception as e:
            op_logger.logger.error(f"Copy failed: {e}")
            return False, f"Copy failed: {str(e)}", ""

    @classmethod
    def delete_item(cls, path: str, force: bool = False) -> Tuple[bool, str, str]:
        """
        Delete file or folder.

        Args:
            path: Path to delete
            force: If True, deletes non-empty folders

        Returns:
            (success, message, details)
        """
        try:
            path = pathlib.Path(path).expanduser().resolve()

            if not path.exists():
                return False, f"Path does not exist: {path}", ""

            if path.is_file():
                path.unlink()
                item_type = "file"
            else:
                if force:
                    shutil.rmtree(str(path))
                else:
                    path.rmdir()  # Only deletes empty directories
                item_type = "folder"

            op_logger.logger.info(f"✓ Deleted {item_type}: {path}")
            return True, f"✓ Deleted {item_type}: {path.name}", f"Type: {item_type} | Path: {path}"

        except OSError as e:
            if "not empty" in str(e).lower():
                return False, f"Directory not empty (use force to delete): {path}", ""
            return False, f"Delete failed: {str(e)}", ""
        except PermissionError:
            return False, f"Permission denied", ""
        except Exception as e:
            op_logger.logger.error(f"Delete failed: {e}")
            return False, f"Delete failed: {str(e)}", ""

    @classmethod
    def list_directory(cls, path: str = None, show_hidden: bool = False) -> Tuple[bool, str, str]:
        """
        List directory contents.

        Args:
            path: Directory path (defaults to current directory)
            show_hidden: Show hidden files

        Returns:
            (success, message, details)
        """
        try:
            if not path:
                path = os.getcwd()

            path = pathlib.Path(path).expanduser().resolve()

            if not path.exists():
                return False, f"Path does not exist: {path}", ""

            if not path.is_dir():
                return False, f"Not a directory: {path}", ""

            items = []
            file_count = 0
            folder_count = 0

            for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                # Skip hidden files unless requested
                if not show_hidden and item.name.startswith('.'):
                    continue

                if item.is_dir():
                    items.append(f"  📁 {item.name}/")
                    folder_count += 1
                else:
                    size = item.stat().st_size
                    size_str = cls._format_size(size)
                    items.append(f"  📄 {item.name} ({size_str})")
                    file_count += 1

            result = f"📂 Contents of {path}:\n"
            result += "\n".join(items[:100])
            if len(items) > 100:
                result += f"\n... and {len(items) - 100} more items"

            result += f"\n\nTotal: {folder_count} folders, {file_count} files"

            details = f"Path: {path} | Folders: {folder_count} | Files: {file_count}"
            return True, result, details

        except PermissionError:
            return False, f"Permission denied: {path}", ""
        except Exception as e:
            op_logger.logger.error(f"List directory failed: {e}")
            return False, f"Failed to list directory: {str(e)}", ""

    @classmethod
    def get_item_info(cls, path: str) -> Tuple[bool, str, str]:
        """
        Get detailed information about a file or folder.

        Args:
            path: Path to file or folder

        Returns:
            (success, message, details)
        """
        try:
            path = pathlib.Path(path).expanduser().resolve()

            if not path.exists():
                return False, f"Path does not exist: {path}", ""

            stat = path.stat()

            item_type = "File" if path.is_file() else "Folder"
            size = stat.st_size
            size_str = cls._format_size(size)

            # Get timestamps
            modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            created = datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')

            result = f"""📋 Info for {path.name}:
  Type: {item_type}
  Size: {size_str}
  Modified: {modified}
  Created: {created}
  Path: {path}"""

            if path.is_dir():
                # Count items in directory
                try:
                    item_count = len(list(path.iterdir()))
                    result += f"\n  Items: {item_count}"
                except PermissionError:
                    pass

            details = f"Type: {item_type} | Size: {size_str} | Path: {path}"
            return True, result, details

        except PermissionError:
            return False, f"Permission denied: {path}", ""
        except Exception as e:
            op_logger.logger.error(f"Get info failed: {e}")
            return False, f"Failed to get info: {str(e)}", ""

    @staticmethod
    def _format_size(size: int) -> str:
        """Format byte size to human-readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
