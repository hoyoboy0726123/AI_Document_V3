"""
Security utility functions for file path validation and other security checks.
"""
import logging
from pathlib import Path
from typing import Union

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def validate_file_path(
    file_path: Union[str, Path],
    base_dir: Union[str, Path],
    check_exists: bool = True
) -> Path:
    """
    Validate that a file path is within the allowed base directory.

    Security: Prevents path traversal attacks by ensuring the resolved
    absolute path is within the base directory.

    Args:
        file_path: The file path to validate (can be relative or absolute)
        base_dir: The base directory that must contain the file
        check_exists: Whether to verify the file exists (default: True)

    Returns:
        Validated Path object (resolved to absolute path)

    Raises:
        HTTPException(403): If path is outside base_dir
        HTTPException(404): If check_exists=True and file doesn't exist
        HTTPException(400): If path format is invalid

    Example:
        >>> from app.core.config import settings
        >>> validated = validate_file_path(
        ...     file_path="storage/documents/file.pdf",
        ...     base_dir=settings.FILE_STORAGE_DIR
        ... )
    """
    try:
        # Resolve to absolute paths
        base_path = Path(base_dir).resolve()
        target_path = Path(file_path).resolve()

        # Check if target is within base directory
        # is_relative_to() is available in Python 3.9+
        try:
            if not target_path.is_relative_to(base_path):
                logger.warning(
                    f"Path traversal attempt detected: {file_path} "
                    f"(base: {base_dir})"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Invalid file path"
                )
        except AttributeError:
            # Fallback for Python < 3.9
            try:
                target_path.relative_to(base_path)
            except ValueError:
                logger.warning(
                    f"Path traversal attempt detected: {file_path} "
                    f"(base: {base_dir})"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Invalid file path"
                )

        # Check if file exists
        if check_exists and not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )

        return target_path

    except HTTPException:
        # Re-raise HTTPException as-is
        raise
    except Exception as e:
        logger.error(f"Path validation error for {file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path format"
        )


def safe_file_delete(file_path: Union[str, Path], base_dir: Union[str, Path]) -> bool:
    """
    Safely delete a file after validating it's within the allowed directory.

    Args:
        file_path: The file path to delete
        base_dir: The base directory that must contain the file

    Returns:
        True if file was deleted, False if file didn't exist

    Raises:
        HTTPException(403): If path is outside base_dir
    """
    try:
        # Validate path (but don't require file to exist)
        validated_path = validate_file_path(
            file_path=file_path,
            base_dir=base_dir,
            check_exists=False
        )

        if validated_path.exists():
            validated_path.unlink()
            logger.info(f"Deleted file: {validated_path}")
            return True
        else:
            logger.debug(f"File not found for deletion: {validated_path}")
            return False

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file"
        )
