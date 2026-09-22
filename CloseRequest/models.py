from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class InactivityTimer:
    thread_id: int
    user_id: int
    started_at: datetime
    expires_at: datetime
    active: bool = True

    def cancel(self):
        self.active = False

    def is_active(self) -> bool:
        return self.active


@dataclass
class CloseRequest:
    thread_id: int
    user_id: int
    created_at: datetime
    active: bool = True

    def disable(self):
        self.active = False

    def is_active(self) -> bool:
        return self.active
