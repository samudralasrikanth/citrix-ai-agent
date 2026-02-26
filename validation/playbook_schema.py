from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum

class ChannelType(str, Enum):
    VISION = "vision"
    WEB = "web"
    API = "api"
    AUTO = "auto"

class ActionType(str, Enum):
    CLICK = "click"
    TYPE = "type"
    VERIFY = "verify"
    CALL = "call"
    PAUSE = "pause"
    SCREENSHOT = "screenshot"

class PlaybookStep(BaseModel):
    action: ActionType
    target: str = ""
    value: str = ""
    channel: ChannelType = ChannelType.AUTO
    config: Optional[Dict[str, Any]] = None
    description: Optional[str] = None

    @root_validator
    def validate_action_channel(cls, values):
        action = values.get("action")
        channel = values.get("channel")
        
        if action == ActionType.CALL and channel != ChannelType.API and channel != ChannelType.AUTO:
            raise ValueError(f"Action 'call' is only compatible with 'api' or 'auto' channel.")
            
        if action in [ActionType.CLICK, ActionType.TYPE] and channel == ChannelType.API:
            raise ValueError(f"Action '{action}' is not compatible with 'api' channel.")
            
        return values

class PlaybookModel(BaseModel):
    name: str
    description: str = ""
    steps: List[PlaybookStep]

def validate_playbook(data: Dict[str, Any]) -> PlaybookModel:
    """
    Validate a raw playbook dictionary against the Pydantic schema.
    Returns a PlaybookModel if valid, raises ValidationError otherwise.
    """
    return PlaybookModel(**data)
