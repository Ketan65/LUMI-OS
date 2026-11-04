"""Orchestrator states. PLAN/ACT/OBSERVE/REFLECT activate in later phases."""

from enum import Enum


class State(Enum):
    UNDERSTAND = "understand"
    PLAN = "plan"
    ACT = "act"
    OBSERVE = "observe"
    RESPOND = "respond"
    REFLECT = "reflect"
