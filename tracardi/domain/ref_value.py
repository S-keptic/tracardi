import logging
from typing import Any, Optional

from dotty_dict import dotty
from pydantic import BaseModel

from tracardi.config import tracardi
from tracardi.exceptions.log_handler import log_handler

logger = logging.getLogger(__name__)
logger.setLevel(tracardi.logging_level)
logger.addHandler(log_handler)


class RefValue(BaseModel):
    value: Optional[str] = ''
    ref: bool

    def has_value(self) -> bool:
        return bool(self.value and self.value.strip())

    def get_value(self, payload: Any):
        value = None
        if self.has_value():
            if not self.ref:
                # Set plain value
                value = self.value.strip()
            else:
                # It is a reference to the event type in payload
                if isinstance(payload, dict):
                    dot = dotty(payload)
                    try:
                        value = dot[self.value.strip()]
                    except KeyError:
                        logger.warning(f"Could not find value in payload at `{self.value}`. "
                                       f"Default value was returned.")

        return value
