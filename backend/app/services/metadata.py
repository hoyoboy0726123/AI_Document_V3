from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from .. import models


class MetadataService:
    """系統管理員維護元數據欄位與選項的服務層骨架。"""

    def __init__(self, db: Session):
        self.db = db

    # ---- 欄位管理 ----
    def list_fields(self, *, active_only: bool = False) -> List[models.MetadataField]:
        query = self.db.query(models.MetadataField).options(joinedload(models.MetadataField.options))
        if active_only:
            query = query.filter(models.MetadataField.is_active.is_(True))
        fields = query.order_by(models.MetadataField.order_index).all()

        # 過濾掉停用的選項（僅在前端顯示時）
        if active_only:
            for field in fields:
                field.options = [opt for opt in field.options if opt.is_active]

        return fields

    def list_required_fields(self) -> List[models.MetadataField]:
        fields = (
            self.db.query(models.MetadataField)
            .options(joinedload(models.MetadataField.options))
            .filter(models.MetadataField.is_active.is_(True))
            .filter(models.MetadataField.is_required.is_(True))
            .order_by(models.MetadataField.order_index)
            .all()
        )

        # 過濾掉停用的選項
        for field in fields:
            field.options = [opt for opt in field.options if opt.is_active]

        return fields

    def get_field(self, field_id: str) -> Optional[models.MetadataField]:
        return (
            self.db.query(models.MetadataField)
            .options(joinedload(models.MetadataField.options))
            .filter(models.MetadataField.id == field_id)
            .first()
        )

    def get_option(self, option_id: str) -> Optional[models.MetadataOption]:
        return self.db.query(models.MetadataOption).filter(models.MetadataOption.id == option_id).first()

    def create_field(
        self,
        *,
        name: str,
        display_name: str,
        field_type: str,
        is_required: bool,
        created_by: Optional[models.User] = None,
        is_active: bool = True,
        order_index: int = 0,
        description: Optional[str] = None,
    ) -> models.MetadataField:
        if self.db.query(models.MetadataField).filter(models.MetadataField.name == name).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Field name already exists")
        field = models.MetadataField(
            name=name,
            display_name=display_name,
            field_type=field_type,
            is_required=is_required,
            created_by=created_by,
            is_active=is_active,
            order_index=order_index,
            description=description,
        )
        self.db.add(field)
        self.db.commit()
        self.db.refresh(field)
        return field

    def update_field(
        self,
        field: models.MetadataField,
        *,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        field_type: Optional[str] = None,
        is_required: Optional[bool] = None,
        is_active: Optional[bool] = None,
        order_index: Optional[int] = None,
        updated_by: Optional[models.User] = None,
    ) -> models.MetadataField:
        if display_name is not None:
            field.display_name = display_name
        if description is not None:
            field.description = description
        if field_type is not None:
            field.field_type = field_type
        if is_required is not None:
            field.is_required = is_required
        if is_active is not None:
            field.is_active = is_active
        if order_index is not None:
            field.order_index = order_index
        if updated_by is not None:
            field.updated_by = updated_by
        self.db.commit()
        self.db.refresh(field)
        return field

    def delete_field(self, field: models.MetadataField) -> None:
        self.db.delete(field)
        self.db.commit()

    # ---- 選項管理 ----
    def add_option(
        self,
        field: models.MetadataField,
        *,
        value: str,
        display_value: str,
        order_index: int = 0,
    ) -> models.MetadataOption:
        option = models.MetadataOption(
            field=field,
            value=value,
            display_value=display_value,
            order_index=order_index,
        )
        self.db.add(option)
        self.db.commit()
        self.db.refresh(option)
        return option

    def update_option(
        self,
        option: models.MetadataOption,
        *,
        display_value: Optional[str] = None,
        is_active: Optional[bool] = None,
        order_index: Optional[int] = None,
    ) -> models.MetadataOption:
        if display_value is not None:
            option.display_value = display_value
        if is_active is not None:
            option.is_active = is_active
        if order_index is not None:
            option.order_index = order_index
        self.db.commit()
        self.db.refresh(option)
        return option

    def delete_option(self, option: models.MetadataOption) -> None:
        self.db.delete(option)
        self.db.commit()
