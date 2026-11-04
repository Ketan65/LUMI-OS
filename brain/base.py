"""Brain abstraction — every LLM provider implements this interface."""

from abc import ABC, abstractmethod

from dataclasses import dataclass, field


@dataclass
class BrainReply:
    """Normalized brain output: plain text and/or native tool calls."""
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # [{"name","args"}]


class Brain(ABC):
    @abstractmethod
    def chat(self, messages: list[dict],
             tools: list[dict] | None = None,
             on_token=None, temperature: float | None = None) -> BrainReply:
        """Send history (+ optional tool schemas), get text and/or tool calls.
        on_token: agar diya toh har text chunk yahan push karo (streaming).
        temperature: None = config default; reflection jaise calls override karte hain."""
        raise NotImplementedError
