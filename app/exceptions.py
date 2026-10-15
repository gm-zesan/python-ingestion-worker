"""
Extraction Exceptions and Error Sanitization.
Prevents leaking absolute filesystem paths, internal stack traces, or credentials.
"""

import re
from typing import Optional

# Pattern matching absolute filesystem paths in Unix and Windows systems
PATH_PATTERN = re.compile(r"(\/[a-zA-Z0-9_\-\.]+)+|\b[a-zA-Z]:\\[a-zA-Z0-9_\-\.\\]+")


def sanitize_error_message(message: str) -> str:
    """Removes absolute paths and internal system details from error messages."""
    if not message:
        return ""
    # Mask full filesystem paths
    sanitized = PATH_PATTERN.sub("[FILE_PATH]", message)
    # Remove user home references
    sanitized = re.sub(r"/Users/[^/\s]+", "[USER_DIR]", sanitized)
    sanitized = re.sub(r"/home/[^/\s]+", "[USER_DIR]", sanitized)
    return sanitized.strip()


class ExtractionException(Exception):
    """Base exception for all document extraction errors."""

    def __init__(self, message: str, error_code: str = "EXTRACTION_FAILED", original_exception: Optional[Exception] = None):
        self.error_code = error_code
        self.raw_message = message
        self.sanitized_message = sanitize_error_message(message)
        self.original_exception = original_exception
        super().__init__(self.sanitized_message)


class UnsupportedFormatException(ExtractionException):
    def __init__(self, message: str = "Unsupported document format"):
        super().__init__(message, error_code="UNSUPPORTED_FORMAT")


class CorruptedFileException(ExtractionException):
    def __init__(self, message: str = "Document is corrupted, truncated, or malformed"):
        super().__init__(message, error_code="CORRUPTED_FILE")


class ResourceLimitException(ExtractionException):
    def __init__(self, message: str = "Document exceeds allowable size or resource limits"):
        super().__init__(message, error_code="RESOURCE_LIMIT_EXCEEDED")


class SecurityException(ExtractionException):
    def __init__(self, message: str = "Security policy violation detected in document"):
        super().__init__(message, error_code="SECURITY_VIOLATION")


class EmptyFileException(ExtractionException):
    def __init__(self, message: str = "Document is empty (0 bytes or no extractable content)"):
        super().__init__(message, error_code="FILE_EMPTY")
