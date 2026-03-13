"""
Validation utilities for common business logic checks.

This module provides reusable validation functions to reduce code duplication
and standardize validation logic across the application.
"""

from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from .. import models
from .exceptions import ValidationError, ResourceNotFoundError


class ClassificationValidator:
    """Validator for classification-related operations."""

    @staticmethod
    def get_active_or_404(
        db: Session,
        classification_id: str
    ) -> models.ClassificationCategory:
        """
        Get active classification category or raise 404.

        Args:
            db: Database session
            classification_id: ID of the classification category

        Returns:
            ClassificationCategory object

        Raises:
            HTTPException: 404 if classification not found or not active
        """
        classification = (
            db.query(models.ClassificationCategory)
            .filter(models.ClassificationCategory.id == classification_id)
            .filter(models.ClassificationCategory.is_active.is_(True))
            .first()
        )

        if not classification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Classification category not found or inactive"
            )

        return classification

    @staticmethod
    def get_active_or_none(
        db: Session,
        classification_id: Optional[str]
    ) -> Optional[models.ClassificationCategory]:
        """
        Get active classification category or return None if ID is None.

        Args:
            db: Database session
            classification_id: Optional ID of the classification category

        Returns:
            ClassificationCategory object or None

        Raises:
            HTTPException: 404 if ID provided but classification not found
        """
        if not classification_id:
            return None

        return ClassificationValidator.get_active_or_404(db, classification_id)


class TempOptionValidator:
    """Validator for temporary/dynamic metadata options."""

    @staticmethod
    def validate_not_temp(option_id: str, operation: str = "編輯"):
        """
        Validate that option is not a temporary option.

        Temporary options (prefixed with "temp_") are dynamically generated
        from document metadata and cannot be directly modified.

        Args:
            option_id: ID of the metadata option
            operation: Operation being performed (for error message)

        Raises:
            HTTPException: 400 if option is temporary
        """
        if option_id.startswith("temp_"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"無法{operation}動態生成的關鍵字選項。"
                       f"這些關鍵字來自文件的實際使用，若要修改，請編輯對應的文件。"
            )


class FileValidator:
    """Validator for file-related operations."""

    @staticmethod
    def validate_pdf_not_empty(pdf_bytes: bytes):
        """
        Validate that PDF bytes are not empty.

        Args:
            pdf_bytes: PDF file content

        Raises:
            HTTPException: 400 if PDF is empty
        """
        if not pdf_bytes:
            ValidationError.raise_bad_request("Uploaded PDF is empty")

    @staticmethod
    def validate_text_extracted(text: Optional[str]):
        """
        Validate that text was successfully extracted from PDF.

        Args:
            text: Extracted text content

        Raises:
            HTTPException: 400 if text extraction failed
        """
        if not text:
            ValidationError.raise_bad_request(
                "Failed to extract text from PDF. "
                "The file may be corrupted or contain only images."
            )


class MetadataValidator:
    """Validator for metadata-related operations."""

    @staticmethod
    def validate_field_name_unique(
        db: Session,
        field_name: str,
        exclude_id: Optional[str] = None
    ):
        """
        Validate that metadata field name is unique.

        Args:
            db: Database session
            field_name: Name of the metadata field
            exclude_id: Optional field ID to exclude from check (for updates)

        Raises:
            HTTPException: 400 if field name already exists
        """
        query = db.query(models.MetadataField).filter(
            models.MetadataField.name == field_name
        )

        if exclude_id:
            query = query.filter(models.MetadataField.id != exclude_id)

        if query.first():
            ValidationError.raise_bad_request(
                f"Metadata field with name '{field_name}' already exists"
            )


class UserValidator:
    """Validator for user-related operations."""

    @staticmethod
    def validate_username_unique(db: Session, username: str):
        """
        Validate that username is unique.

        Args:
            db: Database session
            username: Username to check

        Raises:
            HTTPException: 400 if username already exists
        """
        existing_user = db.query(models.User).filter(
            models.User.username == username
        ).first()

        if existing_user:
            ValidationError.raise_bad_request("Username already registered")

    @staticmethod
    def validate_email_unique(db: Session, email: str):
        """
        Validate that email is unique.

        Args:
            db: Database session
            email: Email to check

        Raises:
            HTTPException: 400 if email already exists
        """
        existing_user = db.query(models.User).filter(
            models.User.email == email
        ).first()

        if existing_user:
            ValidationError.raise_bad_request("Email already registered")
