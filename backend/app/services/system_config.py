"""系統配置管理服務"""
import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .. import models


# 預設配置值
DEFAULT_VECTOR_CONFIG = {
    "overlap_chars": 250,  # 向量塊重疊字符數（0 表示取消）
    "max_chars": 1800,  # 向量塊最大字符數
    "min_similarity_score": 0.3,  # 向量匹配閾值
    "default_top_k": 5,  # 預設返回來源數量
    "search_multiplier": 10,  # 搜索倍數
}


class SystemConfigService:
    """系統配置服務"""

    def __init__(self, db: Session):
        self.db = db

    def get_config(self, key: str, default: Any = None) -> Any:
        """獲取配置值"""
        config = self.db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
        if config:
            try:
                return json.loads(config.value)
            except json.JSONDecodeError:
                return config.value
        return default

    def set_config(self, key: str, value: Any, description: Optional[str] = None) -> None:
        """設置配置值"""
        config = self.db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()

        # 將值轉換為 JSON 字符串
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
        else:
            value_str = json.dumps(value)

        if config:
            config.value = value_str
            if description:
                config.description = description
        else:
            config = models.SystemConfig(
                key=key,
                value=value_str,
                description=description
            )
            self.db.add(config)

        self.db.commit()

    def get_vector_config(self) -> Dict[str, Any]:
        """獲取向量配置"""
        saved_config = self.get_config("vector_config")
        if saved_config:
            # 合併預設值和已保存的值
            config = DEFAULT_VECTOR_CONFIG.copy()
            config.update(saved_config)
            return config
        return DEFAULT_VECTOR_CONFIG.copy()

    def update_vector_config(self, config: Dict[str, Any]) -> None:
        """更新向量配置"""
        # 驗證配置值
        if "overlap_chars" in config:
            overlap = config["overlap_chars"]
            if not isinstance(overlap, int) or overlap < 0:
                raise ValueError("overlap_chars 必須是非負整數")

        if "max_chars" in config:
            max_chars = config["max_chars"]
            if not isinstance(max_chars, int) or max_chars <= 0:
                raise ValueError("max_chars 必須是正整數")

        if "min_similarity_score" in config:
            score = config["min_similarity_score"]
            if not isinstance(score, (int, float)) or not (0 <= score <= 1):
                raise ValueError("min_similarity_score 必須在 0-1 之間")

        if "default_top_k" in config:
            top_k = config["default_top_k"]
            if not isinstance(top_k, int) or top_k <= 0:
                raise ValueError("default_top_k 必須是正整數")

        if "search_multiplier" in config:
            multiplier = config["search_multiplier"]
            if not isinstance(multiplier, int) or multiplier <= 0:
                raise ValueError("search_multiplier 必須是正整數")

        self.set_config("vector_config", config, "向量處理相關配置")

    def get_all_configs(self) -> Dict[str, Any]:
        """獲取所有配置"""
        configs = self.db.query(models.SystemConfig).all()
        result = {}
        for config in configs:
            try:
                result[config.key] = json.loads(config.value)
            except json.JSONDecodeError:
                result[config.key] = config.value
        return result
