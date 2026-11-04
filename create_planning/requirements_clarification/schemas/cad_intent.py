"""
CAD Intent Schema - 定义用户意图和参数的数据结构
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class ParameterSource(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    DEFAULT = "default"


class AmbiguityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CADParameter(BaseModel):
    name: str = Field(..., description="参数名称")
    value: Optional[Any] = Field(None, description="参数值")
    source: ParameterSource = Field(..., description="参数来源")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    description: Optional[str] = Field(None, description="参数说明")


class CADIntent(BaseModel):
    component_type: str = Field(..., description="零件类型，如'法兰'、'齿轮'")

    explicit_params: Dict[str, CADParameter] = Field(default_factory=dict, description="用户明确指定的参数")
    inferred_params: Dict[str, CADParameter] = Field(default_factory=dict, description="从上下文推断的参数")
    default_params: Dict[str, CADParameter] = Field(default_factory=dict, description="使用默认值的参数")

    missing_critical: List[str] = Field(default_factory=list, description="缺失的关键参数（影响拓扑结构）")
    missing_optional: List[str] = Field(default_factory=list, description="缺失的可选参数（不影响拓扑结构）")

    ambiguity_level: AmbiguityLevel = Field(default=AmbiguityLevel.LOW, description="整体模糊度")
    ambiguity_reasons: List[str] = Field(default_factory=list, description="模糊的原因")

    raw_input: str = Field(..., description="用户原始输入")

    def has_critical_missing(self) -> bool:
        return len(self.missing_critical) > 0
