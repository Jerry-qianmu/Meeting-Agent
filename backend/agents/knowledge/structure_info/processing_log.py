from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
from dataclasses import dataclass, field
import operator

class ProcessingLogItem(TypedDict):
    stage: str
    duration_ms: int
    original: str
    rewritten: str
    history_turns: int