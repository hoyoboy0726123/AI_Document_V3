"""
Unified exception handling utilities for the application.

This module provides common exception patterns to reduce code duplication
and standardize error responses across the API.
"""

from typing import Optional, Type, TypeVar
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class ResourceNotFoundError:
    """Unified resource not found error handling."""

    @staticmethod
    def raise_if_none(resource, resource_name: str = "Resource"):
        """
        Raise 404 exception if resource is None.

        Args:
            resource: The resource object to check
            resource_name: Human-readable name of the resource

        Returns:
            The resource if it exists

        Raises:
            HTTPException: 404 if resource is None
        """
        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{resource_name} not found"
            )
        return resource

    @staticmethod
    def get_or_404(
        db: Session,
        model: Type[ModelType],
        resource_id: str,
        resource_name: Optional[str] = None
    ) -> ModelType:
        """
        Get resource by ID or raise 404 if not found.

        Args:
            db: Database session
            model: SQLAlchemy model class
            resource_id: ID of the resource
            resource_name: Human-readable name (defaults to model name)

        Returns:
            The resource object

        Raises:
            HTTPException: 404 if resource not found
        """
        resource = db.query(model).filter(model.id == resource_id).first()
        name = resource_name or model.__name__
        return ResourceNotFoundError.raise_if_none(resource, name)


class ValidationError:
    """Unified validation error handling."""

    @staticmethod
    def raise_bad_request(detail: str):
        """
        Raise 400 Bad Request exception.

        Args:
            detail: Error message

        Raises:
            HTTPException: 400 Bad Request
        """
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

    @staticmethod
    def raise_if_exists(
        db: Session,
        model: Type[ModelType],
        error_message: str,
        **filters
    ):
        """
        Raise 400 if resource already exists with given filters.

        Args:
            db: Database session
            model: SQLAlchemy model class
            error_message: Error message if resource exists
            **filters: Field name and value pairs for filtering

        Raises:
            HTTPException: 400 if resource exists

        Example:
            ValidationError.raise_if_exists(
                db, models.User,
                "Username already registered",
                username="john"
            )
        """
        query = db.query(model)
        for field, value in filters.items():
            query = query.filter(getattr(model, field) == value)

        if query.first() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )

    @staticmethod
    def raise_if_empty(value: Optional[str], field_name: str):
        """
        Raise 400 if value is empty or None.

        Args:
            value: Value to check
            field_name: Name of the field for error message

        Raises:
            HTTPException: 400 if value is empty
        """
        if not value or (isinstance(value, str) and not value.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} cannot be empty"
            )


class AuthorizationError:
    """Unified authorization error handling."""

    @staticmethod
    def raise_forbidden(detail: str = "You don't have permission to access this resource"):
        """
        Raise 403 Forbidden exception.

        Args:
            detail: Error message

        Raises:
            HTTPException: 403 Forbidden
        """
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )

    @staticmethod
    def raise_unauthorized(detail: str = "Authentication required"):
        """
        Raise 401 Unauthorized exception.

        Args:
            detail: Error message

        Raises:
            HTTPException: 401 Unauthorized
        """
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )
