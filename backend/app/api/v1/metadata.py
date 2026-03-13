from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ... import models, schemas
from ...core.security import get_current_user
from ...database import get_db
from ...services.metadata import MetadataService

router = APIRouter()


def _service(db: Session) -> MetadataService:
    return MetadataService(db)


@router.get("/metadata-fields", response_model=List[schemas.MetadataFieldRead])
@router.get("/metadata-fields/", response_model=List[schemas.MetadataFieldRead])
def list_metadata_fields(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = _service(db)
    fields = service.list_fields(active_only=True)

    # 對於 select 和 multi_select 欄位，動態添加所有文件中使用過的值
    for field in fields:
        if field.field_type in ("select", "multi_select"):
            # 收集所有文件中使用的值
            documents = db.query(models.Document).all()
            used_values = set()

            for doc in documents:
                if doc.metadata_data and field.name in doc.metadata_data:
                    value = doc.metadata_data.get(field.name)
                    if isinstance(value, list):
                        # multi_select 欄位
                        used_values.update(value)
                    elif value:
                        # select 欄位
                        used_values.add(value)

            # 獲取現有選項的 value
            existing_values = {opt.value for opt in field.options}

            # 為新的值創建臨時選項（這些不會存入資料庫）
            temp_options = []
            for value in sorted(used_values):
                if value and value not in existing_values:
                    # 創建臨時選項物件
                    temp_opt = models.MetadataOption(
                        id=f"temp_{field.name}_{value}",
                        field_id=field.id,
                        value=value,
                        display_value=value,
                        is_active=True,
                        order_index=9999
                    )
                    temp_options.append(temp_opt)

            # 將臨時選項添加到欄位的 options 中
            field.options.extend(temp_options)

    return fields


@router.get("/metadata-fields/required", response_model=List[schemas.MetadataFieldRead])
@router.get("/metadata-fields/required/", response_model=List[schemas.MetadataFieldRead])
def list_required_metadata_fields(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    service = _service(db)
    return service.list_required_fields()


@router.post("/metadata-fields/{field_id}/options", response_model=schemas.MetadataOptionRead, status_code=status.HTTP_201_CREATED)
@router.post("/metadata-fields/{field_id}/options/", response_model=schemas.MetadataOptionRead, status_code=status.HTTP_201_CREATED)
def add_metadata_option(
    field_id: str,
    payload: schemas.MetadataOptionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """允許用戶在建立文件時即時新增 metadata 選項（如文件類型、專案等）"""
    service = _service(db)
    field = service.get_field(field_id)
    if not field:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="欄位不存在")

    # 檢查是否已經存在相同的 value
    existing_option = db.query(models.MetadataOption).filter(
        models.MetadataOption.field_id == field_id,
        models.MetadataOption.value == payload.value
    ).first()
    if existing_option:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="選項值已存在")

    option = service.add_option(
        field=field,
        value=payload.value,
        display_value=payload.display_value,
        order_index=payload.order_index
    )
    return option
