from __future__ import annotations

import random
import re
from typing import List, Sequence, Tuple

from .models import Lesson, QuizQuestion, UserSession

PROMPT_STYLES = (
    "{prompt}",
    "اختبار معرفة: {prompt}",
    "فحص المخاطرة أولًا: {prompt}",
    "اختبار التنفيذ: {prompt}",
    "مراجعة العملية: {prompt}",
    "تركيز على السيناريو: {scenario} {prompt}",
    "قبل تنفيذ الصفقة أجب: {prompt}",
)

OPTION_KEYS = ("A", "B", "C", "D")


def build_random_quiz_for_lesson(
    lesson: Lesson,
    session: UserSession,
    min_questions: int = 2,
    max_questions: int = 3,
) -> List[QuizQuestion]:
    """Generate a random non-repeating quiz variant for a lesson."""
    if not lesson.quiz:
        return []

    history = session.quiz_variant_history.setdefault(lesson.lesson_id, set())
    upper_bound = max(min_questions, min(max_questions, 3))
    target = random.randint(min_questions, upper_bound)

    generated: List[QuizQuestion] = []
    generated_signatures = set()
    used_base_prompts = set()
    attempts = 0
    max_attempts = 300

    while len(generated) < target and attempts < max_attempts:
        attempts += 1
        base = random.choice(lesson.quiz)
        base_key = _normalize_prompt(base.prompt)
        if len(used_base_prompts) < len(lesson.quiz) and base_key in used_base_prompts:
            continue

        variant, signature = _build_variant_question(base, lesson)

        if signature in history or signature in generated_signatures:
            continue

        generated.append(variant)
        generated_signatures.add(signature)
        used_base_prompts.add(base_key)

    if len(generated) < target:
        history.clear()
        while len(generated) < target and attempts < (max_attempts * 2):
            attempts += 1
            base = random.choice(lesson.quiz)
            variant, signature = _build_variant_question(base, lesson)
            if signature in generated_signatures:
                continue
            generated.append(variant)
            generated_signatures.add(signature)

    if not generated:
        generated = [_shuffle_options(question) for question in lesson.quiz]
        generated_signatures = {_signature_from_question(lesson.lesson_id, q) for q in generated}

    history.update(generated_signatures)
    return generated[:target]


def _build_variant_question(base: QuizQuestion, lesson: Lesson) -> Tuple[QuizQuestion, str]:
    style_index = random.randrange(len(PROMPT_STYLES))
    prompt = _format_prompt(base.prompt, lesson, style_index)

    shuffled, option_order = _shuffle_options_with_order(base)
    signature = _signature_from_parts(lesson.lesson_id, base.prompt, style_index, option_order)
    question = QuizQuestion(
        prompt=prompt,
        options=shuffled.options,
        answer=shuffled.answer,
        explanation=base.explanation,
    )
    return question, signature


def _format_prompt(base_prompt: str, lesson: Lesson, style_index: int) -> str:
    style = PROMPT_STYLES[style_index]
    scenario = _compact_scenario(lesson.example)
    return style.format(prompt=base_prompt, scenario=scenario)


def _compact_scenario(example: str) -> str:
    clean = re.sub(r"^\s*(?:Example|مثال)\s*:\s*", "", example.strip(), flags=re.IGNORECASE)
    if len(clean) <= 120:
        return clean
    return clean[:117].rstrip() + "..."


def _shuffle_options(question: QuizQuestion) -> QuizQuestion:
    shuffled, _ = _shuffle_options_with_order(question)
    return shuffled


def _shuffle_options_with_order(question: QuizQuestion) -> Tuple[QuizQuestion, Sequence[int]]:
    items = list(question.options.items())
    indices = list(range(len(items)))
    random.shuffle(indices)

    correct_text = question.options.get(question.answer.upper(), "")
    remapped = {}
    new_answer = "A"

    for out_key, idx in zip(OPTION_KEYS, indices):
        option_text = items[idx][1]
        remapped[out_key] = option_text
        if option_text == correct_text:
            new_answer = out_key

    shuffled = QuizQuestion(
        prompt=question.prompt,
        options=remapped,
        answer=new_answer,
        explanation=question.explanation,
    )
    return shuffled, tuple(indices)


def _signature_from_parts(
    lesson_id: str,
    base_prompt: str,
    style_index: int,
    option_order: Sequence[int],
) -> str:
    normalized_prompt = _normalize_prompt(base_prompt)
    order = ",".join(str(idx) for idx in option_order)
    return f"{lesson_id}|{normalized_prompt}|s{style_index}|o{order}"


def _signature_from_question(lesson_id: str, question: QuizQuestion) -> str:
    prompt = _normalize_prompt(question.prompt)
    options = "|".join(question.options.get(key, "") for key in OPTION_KEYS)
    return f"{lesson_id}|{prompt}|{options}|{question.answer}"


def _normalize_prompt(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())
