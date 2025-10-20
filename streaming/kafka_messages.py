"""Kafka message schemas for the distributed traffic monitoring system."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class MessageType(str, Enum):
    """Kafka message types."""
    DETECTION_RESULT = "detection_result"
    ASSESSMENT_TASK = "assessment_task"
    RISK_ASSESSMENT_RESULT = "risk_assessment_result"


class TaskStatus(str, Enum):
    """Assessment task status."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class RiskLevel(str, Enum):
    """Risk level enumeration."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class FrameMetadata:
    """Video frame metadata."""
    width: int
    height: int
    fps: Optional[float] = None
    format: str = "BGR"


@dataclass
class DetectedObject:
    """Single detected object."""
    object_id: int
    class_name: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    level: int = 0


@dataclass
class SpatialFeatures:
    """Spatial relationship features of a traffic group."""
    density: Optional[float] = None  # objects per 10000 pixels
    avg_spacing: Optional[float] = None  # average distance between objects
    min_spacing: Optional[float] = None  # minimum distance between objects
    ped_vehicle_min_dist: Optional[float] = None  # min distance between pedestrian and vehicle
    vehicle_count: int = 0
    pedestrian_count: int = 0


@dataclass
class TrafficGroup:
    """Traffic group information."""
    group_index: int
    object_count: int
    bbox: List[float]  # [x1, y1, x2, y2]
    classes: List[str]
    avg_confidence: float
    member_indices: List[int]
    group_image_base64: str
    spatial_features: Optional[SpatialFeatures] = None
    risk_level: str = "none"


@dataclass
class DetectionResultMessage:
    """Message for detection-results-topic.
    
    This message contains YOLO detection and group analysis results.
    """
    message_id: str = field(default_factory=lambda: str(uuid4()))
    message_type: str = field(default=MessageType.DETECTION_RESULT.value)
    camera_id: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    frame_metadata: FrameMetadata = field(default_factory=lambda: FrameMetadata(0, 0))
    detected_objects: List[DetectedObject] = field(default_factory=list)
    traffic_groups: List[TrafficGroup] = field(default_factory=list)
    raw_frame_base64: Optional[str] = None  # Optional for bandwidth optimization
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DetectionResultMessage:
        """Create from dictionary."""
        # Convert nested objects
        if "frame_metadata" in data and isinstance(data["frame_metadata"], dict):
            data["frame_metadata"] = FrameMetadata(**data["frame_metadata"])
        
        if "detected_objects" in data:
            data["detected_objects"] = [
                DetectedObject(**obj) if isinstance(obj, dict) else obj
                for obj in data["detected_objects"]
            ]
        
        if "traffic_groups" in data:
            groups = []
            for grp in data["traffic_groups"]:
                if isinstance(grp, dict):
                    if "spatial_features" in grp and grp["spatial_features"]:
                        grp["spatial_features"] = SpatialFeatures(**grp["spatial_features"])
                    groups.append(TrafficGroup(**grp))
                else:
                    groups.append(grp)
            data["traffic_groups"] = groups
        
        return cls(**data)


@dataclass
class DetectionContext:
    """Context information for LLM assessment."""
    detected_objects: List[DetectedObject]
    group_metadata: Dict[str, Any]
    spatial_features: Optional[SpatialFeatures] = None


@dataclass
class AssessmentTaskMessage:
    """Message for assessment-tasks-topic.
    
    This message represents a single LLM assessment task.
    """
    task_id: str = field(default_factory=lambda: str(uuid4()))
    message_type: str = field(default=MessageType.ASSESSMENT_TASK.value)
    origin_message_id: str = ""
    camera_id: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    group_index: int = 0
    group_image_base64: str = ""
    detection_context: Optional[DetectionContext] = None
    priority: int = 1  # 1=normal, 2=high, 3=critical
    retry_count: int = 0
    status: str = field(default=TaskStatus.PENDING.value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssessmentTaskMessage:
        """Create from dictionary."""
        if "detection_context" in data and data["detection_context"]:
            ctx = data["detection_context"]
            if isinstance(ctx, dict):
                if "detected_objects" in ctx:
                    ctx["detected_objects"] = [
                        DetectedObject(**obj) if isinstance(obj, dict) else obj
                        for obj in ctx["detected_objects"]
                    ]
                if "spatial_features" in ctx and ctx["spatial_features"]:
                    ctx["spatial_features"] = SpatialFeatures(**ctx["spatial_features"])
                data["detection_context"] = DetectionContext(**ctx)
        
        return cls(**data)


@dataclass
class AssessmentResult:
    """LLM assessment result."""
    has_dangerous_driving: bool
    risk_level: str
    risk_types: List[str]
    description: str
    confidence: float
    danger_object_ids: List[int] = field(default_factory=list)
    danger_object_count: int = 0


@dataclass
class LLMMetadata:
    """Metadata about the LLM API call."""
    model: str
    api_key_id: str
    latency_ms: float
    raw_response: Optional[str] = None
    tokens_used: Optional[int] = None


@dataclass
class RiskAssessmentResultMessage:
    """Message for risk-assessment-results-topic.
    
    This message contains the LLM risk assessment result.
    """
    result_id: str = field(default_factory=lambda: str(uuid4()))
    message_type: str = field(default=MessageType.RISK_ASSESSMENT_RESULT.value)
    task_id: str = ""
    origin_message_id: str = ""
    camera_id: int = 0
    group_index: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    assessment_result: Optional[AssessmentResult] = None
    llm_metadata: Optional[LLMMetadata] = None
    status: str = field(default=TaskStatus.SUCCESS.value)
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RiskAssessmentResultMessage:
        """Create from dictionary."""
        if "assessment_result" in data and data["assessment_result"]:
            if isinstance(data["assessment_result"], dict):
                data["assessment_result"] = AssessmentResult(**data["assessment_result"])
        
        if "llm_metadata" in data and data["llm_metadata"]:
            if isinstance(data["llm_metadata"], dict):
                data["llm_metadata"] = LLMMetadata(**data["llm_metadata"])
        
        return cls(**data)


# Message type registry for deserialization
MESSAGE_TYPE_REGISTRY = {
    MessageType.DETECTION_RESULT.value: DetectionResultMessage,
    MessageType.ASSESSMENT_TASK.value: AssessmentTaskMessage,
    MessageType.RISK_ASSESSMENT_RESULT.value: RiskAssessmentResultMessage,
}


def deserialize_message(data: Dict[str, Any]) -> Any:
    """Deserialize a message based on its type."""
    message_type = data.get("message_type")
    if not message_type:
        raise ValueError("Message missing 'message_type' field")
    
    message_class = MESSAGE_TYPE_REGISTRY.get(message_type)
    if not message_class:
        raise ValueError(f"Unknown message type: {message_type}")
    
    return message_class.from_dict(data)
