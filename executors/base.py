from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseExecutor(ABC):
    """
    Abstract Base Class for all automation executors.
    Defines the contract for Vision, Web, and API channels.
    """
    
    @abstractmethod
    def execute(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step and return a structured result."""
        pass

    @abstractmethod
    def click(self, target: str, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    def type(self, target: str, value: str, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    def verify(self, target: str, **kwargs) -> Dict[str, Any]:
        pass

    def call_api(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Default implementation for executors that don't support API directly."""
        return {"success": False, "error": f"{self.__class__.__name__} does not support API calls."}
