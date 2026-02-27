from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class QuizQuestion:
    prompt: str
    options: Dict[str, str]
    answer: str
    explanation: str


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    level: str
    title: str
    objective: str
    bullet_points: List[str]
    example: str
    quiz: List[QuizQuestion]
    premium_only: bool = False


@dataclass
class QuizState:
    lesson_id: str
    questions: List[QuizQuestion]
    current_index: int = 0
    score: int = 0
    is_dynamic: bool = False
    level: str = ""


@dataclass
class SimulationState:
    symbol: str
    entry: float
    support: float
    resistance: float
    context: str = ""
    stage: str = "direction"
    direction: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class DailyChallengeState:
    prompt: str
    expected_keywords: List[str]


@dataclass
class UserSession:
    user_id: int
    level: str = "beginner"
    access: str = "free"
    focus: str = "both"
    language: str = "ar"
    assistant_mode: bool = False
    completed_lessons: Set[str] = field(default_factory=set)
    quiz_variant_history: Dict[str, Set[str]] = field(default_factory=dict)
    ai_recent_lesson_titles: List[str] = field(default_factory=list)
    ai_recent_quiz_prompts: List[str] = field(default_factory=list)
    ai_lessons_completed: int = 0
    ai_simulations_completed: int = 0
    ai_challenges_completed: int = 0
    pending_lesson: Optional[Lesson] = None
    quiz_state: Optional[QuizState] = None
    simulation_state: Optional[SimulationState] = None
    daily_challenge_state: Optional[DailyChallengeState] = None

