from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional


Category = Literal["jailbreak", "nsfw", "self_harm", "violence", "hate"]


_JAILBREAK = re.compile(
    r"(ignore (all|any|previous) (instructions|rules)|system prompt|developer message|jailbreak|do anything now)",
    re.IGNORECASE,
)
_NSFW = re.compile(r"\b(sex|porn|nude|naked|blowjob|anal|escort)\b", re.IGNORECASE)
_SELF_HARM = re.compile(r"\b(suicide|kill myself|self harm|cut myself)\b", re.IGNORECASE)
_VIOLENCE = re.compile(r"\b(how to make a bomb|build a bomb|poison|kill them)\b", re.IGNORECASE)
_HATE = re.compile(r"\b(genocide|gas the|racial slur)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SafetyResult:
    allowed: bool
    category: Optional[Category] = None
    reason: Optional[str] = None


def detect_unsafe(text: str) -> SafetyResult:
    if _JAILBREAK.search(text):
        return SafetyResult(False, "jailbreak", "prompt_injection")
    if _SELF_HARM.search(text):
        return SafetyResult(False, "self_harm", "self_harm")
    if _VIOLENCE.search(text):
        return SafetyResult(False, "violence", "violence")
    if _NSFW.search(text):
        return SafetyResult(False, "nsfw", "nsfw")
    if _HATE.search(text):
        return SafetyResult(False, "hate", "hate")
    return SafetyResult(True)


def refusal_message(*, tone: str | None = None, category: Category | None = None) -> str:
    # Minimal personality awareness via tone.
    if tone == "playful":
        return "I can’t help with that—but I *can* help with something safer if you want."
    if tone == "direct":
        return "I can’t help with that. If you want, tell me what safe goal you’re trying to achieve instead."
    # default warm
    if category == "self_harm":
        return "I’m really sorry you’re feeling this way. I can’t help with self-harm, but I can stay with you and help you find support."
    return "I can’t help with that, but I can help with something safer if you’d like."

