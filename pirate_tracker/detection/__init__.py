"""Vision par ordinateur : détection des ouvertures de coffre et du jeton pirate."""
from .chest import ChestDetector, ChestDetectorConfig, ChestEvent
from .token import TokenDetector, TokenDetectorConfig, TokenEvent
from .templates import TemplateStore

__all__ = [
    "ChestDetector", "ChestDetectorConfig", "ChestEvent",
    "TokenDetector", "TokenDetectorConfig", "TokenEvent",
    "TemplateStore",
]
