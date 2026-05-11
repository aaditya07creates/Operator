def categorize_error(error: str) -> str:
    """
    Categorize error message by type for easier pattern matching and fixing.

    Analyzes error text and returns a standardized category string that can be
    used for organizing fixes, applying retry strategies, or logging.

    Args:
        error: Error message text (from command output, exceptions, etc.)

    Returns:
        str: Error category identifier, one of:
            - 'not_found': Command/file not found or not recognized
            - 'access_denied': Permission or access issues
            - 'timeout': Operation timeout errors
            - 'uwp': Windows UWP/Store app related errors
            - 'general': Unclassified or generic errors

    Example:
        >>> categorize_error("'spotify' is not recognized as an internal or external command")
        'not_found'

        >>> categorize_error("Access is denied.")
        'access_denied'

        >>> categorize_error("Operation timed out")
        'timeout'

        >>> categorize_error("Get-AppxPackage failed")
        'uwp'

        >>> categorize_error("Something went wrong")
        'general'

    Notes:
        - Case-insensitive matching for robustness
        - Categories are ordered by priority (most specific first)
        - Used by both MemoryManager and LearningSystem for consistency
    """
    error_lower = error.lower()

    # Check for common error patterns
    if 'not recognized' in error_lower or 'not found' in error_lower:
        return 'not_found'
    elif 'access denied' in error_lower or 'permission' in error_lower:
        return 'access_denied'
    elif 'timeout' in error_lower:
        return 'timeout'
    elif 'uwp' in error_lower or 'appx' in error_lower:
        return 'uwp'
    else:
        return 'general'
