from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx

from .models import Lesson, QuizQuestion

EMOJI_TRUE = "✅"
EMOJI_FALSE = "❌"

SUPPORTED_LANGUAGES = {"ar", "en"}

SYSTEM_PROMPTS = {
    "ar": (
        "أنت Sin Trade AI، مساعد تعليمي في التداول. "
        "لا تقدم نصائح مالية مباشرة، ولا تضمن الأرباح. "
        "أكد دائمًا على إدارة المخاطر والانضباط."
    ),
    "en": (
        "You are Sin Trade AI, an educational trading assistant. "
        "Do not provide direct financial advice and never guarantee profits. "
        "Always emphasize risk management and discipline."
    ),
}


def _lang(language: str) -> str:
    return language if language in SUPPORTED_LANGUAGES else "ar"


class AIContentClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4.1-mini",
        base_url: str = "https://api.openai.com/v1/chat/completions",
        site_url: str = "",
        app_name: str = "Sin Trade AI",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.strip() or "https://api.openai.com/v1/chat/completions"
        self._site_url = site_url.strip()
        self._app_name = app_name.strip() or "Sin Trade AI"
        self._timeout_seconds = max(3.0, timeout_seconds)
        self._suspend_until = 0.0
        self._last_error = ""

    def status_label(self, language: str = "ar") -> str:
        lang = _lang(language)
        if time.time() < self._suspend_until and self._last_error:
            if lang == "en":
                return f"{EMOJI_FALSE} Dynamic AI content (temporarily unavailable: {self._last_error})"
            return f"{EMOJI_FALSE} محتوى AI ديناميكي (غير متاح مؤقتًا: {self._last_error})"
        if lang == "en":
            return f"{EMOJI_TRUE} Dynamic AI content (unlimited)"
        return f"{EMOJI_TRUE} محتوى AI ديناميكي (غير محدود)"

    def last_error_code(self) -> str:
        return self._last_error.strip()

    async def answer_question(
        self,
        question: str,
        language: str = "ar",
    ) -> Optional[str]:
        """Answer a general trading question."""
        # Detect language from question text
        # Count Arabic characters to determine if the question is in Arabic
        arabic_chars = sum(1 for c in question if '\u0600' <= c <= '\u06FF' or '\u0750' <= c <= '\u077F')
        is_arabic = arabic_chars > len(question) * 0.3

        if is_arabic:
            user_prompt = (
                f"المستخدم يسأل: {question}\n\n"
                "أجب على سؤال المستخدم بلغة عربية واضحة ومختصرة. "
                "تذكر: لا تعطي نصائح مالية مباشرة، ركز على التعليم وإدارة المخاطر."
            )
            lang = "ar"
        else:
            user_prompt = (
                f"User asks: {question}\n\n"
                "Answer the user's question in clear, concise English. "
                "Remember: Do not give direct financial advice, focus on education and risk management."
            )
            lang = "en"

        return await self._request_text(user_prompt, temperature=0.7, language=lang)

    async def _request_text(
        self,
        user_prompt: str,
        temperature: float = 1.0,
        timeout_seconds: Optional[float] = None,
        language: str = "ar",
    ) -> Optional[str]:
        """Make a request that returns plain text instead of JSON."""
        lang = _lang(language)

        request_timeout = max(3.0, timeout_seconds if timeout_seconds is not None else self._timeout_seconds)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPTS[lang]},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in self._base_url:
            if self._site_url:
                headers["HTTP-Referer"] = self._site_url
            if self._app_name:
                headers["X-Title"] = self._app_name

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await asyncio.wait_for(
                    client.post(self._base_url, headers=headers, json=payload),
                    timeout=request_timeout,
                )
            body = response.json()
        except asyncio.TimeoutError:
            self._last_error = "timeout"
            self._suspend_until = time.time() + 20
            return None
        except httpx.TimeoutException:
            self._last_error = "timeout"
            self._suspend_until = time.time() + 20
            return None
        except (httpx.HTTPError, ValueError):
            self._last_error = "network_error"
            self._suspend_until = time.time() + 60
            return None

        if response.status_code >= 400:
            self._last_error = _extract_error_code(body) or f"http_{response.status_code}"
            if response.status_code in {401, 403}:
                self._suspend_until = time.time() + 300
            elif response.status_code == 429:
                if self._last_error == "insufficient_quota":
                    self._suspend_until = time.time() + 1800
                else:
                    self._suspend_until = time.time() + 120
            else:
                self._suspend_until = time.time() + 60
            return None

        content = _extract_content(body)
        if not content:
            self._last_error = "empty_content"
            return None

        self._last_error = ""
        return content.strip()

    async def generate_lesson(
        self,
        *,
        level: str,
        access: str,
        focus: str,
        recent_titles: List[str],
        recent_questions: List[str],
        lesson_number: int = 1,
        total_lessons: int = 100,
        language: str = "ar",
    ) -> Optional[Lesson]:
        lang = _lang(language)
        recent_titles_text = ", ".join(recent_titles[-8:]) if recent_titles else ("none" if lang == "en" else "لا يوجد")
        recent_questions_text = " | ".join(recent_questions[-8:]) if recent_questions else ("none" if lang == "en" else "لا يوجد")

        if lang == "en":
            user_prompt = (
                "Create one concise trading lesson in strict JSON.\n"
                f"Curriculum position: lesson {lesson_number} of {total_lessons}\n"
                f"Level: {level}\n"
                f"Access: {access}\n"
                f"Focus: {focus}\n"
                f"Avoid repeating these recent lesson titles: {recent_titles_text}\n"
                f"Avoid repeating these recent quiz questions: {recent_questions_text}\n\n"
                "JSON schema:\n"
                "{\n"
                '  "title": "string",\n'
                '  "objective": "string",\n'
                '  "bullet_points": ["string","string","string","string"],\n'
                '  "example": "string"\n'
                "}\n\n"
                "Rules:\n"
                "- Keep it practical and concise.\n"
                "- Provide exactly 4 bullet points.\n"
                "- Emphasize risk, discipline, and emotional control.\n"
                "- If money is referenced, use Algerian dinar (DZD) only.\n"
                "- Return JSON only, no markdown."
            )
        else:
            user_prompt = (
                "أنشئ درس تداول واحدًا مختصرًا بصيغة JSON صارمة وباللغة العربية.\n"
                f"موقع الدرس في المنهج: الدرس {lesson_number} من {total_lessons}\n"
                f"المستوى: {level}\n"
                f"نوع الوصول: {access}\n"
                f"التركيز: {focus}\n"
                f"تجنب تكرار عناوين الدروس الأخيرة التالية: {recent_titles_text}\n"
                f"تجنب تكرار أسئلة الاختبارات الأخيرة التالية: {recent_questions_text}\n\n"
                "مخطط JSON:\n"
                "{\n"
                '  "title": "string",\n'
                '  "objective": "string",\n'
                '  "bullet_points": ["string","string","string","string"],\n'
                '  "example": "string"\n'
                "}\n\n"
                "القواعد:\n"
                "- اجعل الدرس مختصرًا وعمليًا.\n"
                "- قدم 4 نقاط رئيسية بالضبط.\n"
                "- ركز على المخاطر والانضباط والتحكم العاطفي.\n"
                "- عند ذكر المال استخدم الدينار الجزائري (DZD/دج) فقط.\n"
                "- أعد JSON فقط دون Markdown."
            )

        data = await self._request_json(user_prompt, temperature=1.0, language=lang)
        if not data:
            return None
        return _parse_lesson(data, level, lang)

    async def generate_lesson_quiz_pack(
        self,
        *,
        lesson: Lesson,
        focus: str,
        recent_questions: List[str],
        quiz_count: int = 50,
        language: str = "ar",
    ) -> List[QuizQuestion]:
        if quiz_count <= 0:
            return []
        lang = _lang(language)
        recent_questions_text = " | ".join(recent_questions[-16:]) if recent_questions else ("none" if lang == "en" else "لا يوجد")
        lesson_points = " | ".join(lesson.bullet_points[:4])
        chunk_size = 25
        total_chunks = (quiz_count + chunk_size - 1) // chunk_size

        async def _fetch_chunk(chunk_index: int, chunk_target: int) -> List[QuizQuestion]:
            if lang == "en":
                user_prompt = (
                    "Create quiz questions for this lesson in strict JSON.\n"
                    f"Part: {chunk_index + 1}/{total_chunks}\n"
                    f"Level: {lesson.level}\n"
                    f"Focus: {focus}\n"
                    f"Lesson title: {lesson.title}\n"
                    f"Lesson objective: {lesson.objective}\n"
                    f"Lesson points: {lesson_points}\n"
                    f"Avoid repeating recent quiz questions: {recent_questions_text}\n\n"
                    "JSON schema:\n"
                    "{\n"
                    '  "quiz": [\n'
                    "    {\n"
                    '      "prompt": "string",\n'
                    '      "options": {"A":"string","B":"string","C":"string","D":"string"},\n'
                    '      "answer": "A|B|C|D",\n'
                    '      "explanation": "string"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "Rules:\n"
                    f"- Provide exactly {chunk_target} questions.\n"
                    "- Keep each chunk distinct.\n"
                    "- Prioritize practical risk-management thinking.\n"
                    "- If money appears, use DZD only.\n"
                    "- Return JSON only."
                )
            else:
                user_prompt = (
                    "أنشئ أسئلة اختبار لهذا الدرس بصيغة JSON صارمة وباللغة العربية.\n"
                    f"جزء: {chunk_index + 1}/{total_chunks}\n"
                    f"المستوى: {lesson.level}\n"
                    f"التركيز: {focus}\n"
                    f"عنوان الدرس: {lesson.title}\n"
                    f"هدف الدرس: {lesson.objective}\n"
                    f"نقاط الدرس: {lesson_points}\n"
                    f"تجنب تكرار أسئلة الاختبار الأخيرة التالية: {recent_questions_text}\n\n"
                    "مخطط JSON:\n"
                    "{\n"
                    '  "quiz": [\n'
                    "    {\n"
                    '      "prompt": "string",\n'
                    '      "options": {"A":"string","B":"string","C":"string","D":"string"},\n'
                    '      "answer": "A|B|C|D",\n'
                    '      "explanation": "string"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    "القواعد:\n"
                    f"- قدم {chunk_target} سؤالًا بالضبط.\n"
                    "- اجعل هذا الجزء مختلفًا عن بقية الأجزاء.\n"
                    "- كل سؤال يجب أن يختبر التفكير العملي المبني على إدارة المخاطر أولًا.\n"
                    "- إذا ظهر سياق مالي استخدم الدينار الجزائري (DZD/دج) فقط.\n"
                    "- أعد JSON فقط دون Markdown."
                )
            data = await self._request_json(
                user_prompt,
                temperature=0.8,
                timeout_seconds=max(self._timeout_seconds, 90.0),
                respect_suspend=False,
                language=lang,
            )
            if not data:
                return []
            return _parse_quiz(data.get("quiz"), lang)[:chunk_target]

        merged: List[QuizQuestion] = []
        for chunk_index in range(total_chunks):
            start = chunk_index * chunk_size
            target = min(chunk_size, quiz_count - start)
            result = await _fetch_chunk(chunk_index, target)
            merged.extend(result)
        return _ensure_quiz_count(merged, quiz_count, lang)

    async def generate_simulation(
        self,
        *,
        level: str,
        focus: str,
        language: str = "ar",
    ) -> Optional[Dict[str, Any]]:
        lang = _lang(language)
        if lang == "en":
            user_prompt = (
                "Create one trading simulation scenario in strict JSON.\n"
                f"Level: {level}\n"
                f"Focus: {focus}\n\n"
                "JSON schema:\n"
                "{\n"
                '  "symbol": "BTCDZD|ETHDZD|SOLDZD|BNBDZD|XRPDZD",\n'
                '  "entry": 123.45,\n'
                '  "support": 120.00,\n'
                '  "resistance": 130.00,\n'
                '  "context": "short educational context sentence"\n'
                "}\n\n"
                "Rules:\n"
                "- Use realistic DZD-based values.\n"
                "- Keep context educational.\n"
                "- Return JSON only."
            )
        else:
            user_prompt = (
                "أنشئ سيناريو محاكاة تداول واحدًا بصيغة JSON صارمة وباللغة العربية.\n"
                f"المستوى: {level}\n"
                f"التركيز: {focus}\n\n"
                "مخطط JSON:\n"
                "{\n"
                '  "symbol": "BTCDZD|ETHDZD|SOLDZD|BNBDZD|XRPDZD",\n'
                '  "entry": 123.45,\n'
                '  "support": 120.00,\n'
                '  "resistance": 130.00,\n'
                '  "context": "جملة سياق تعليمية قصيرة"\n'
                "}\n\n"
                "القواعد:\n"
                "- استخدم أرقامًا واقعية بالدينار الجزائري (DZD/دج).\n"
                "- اجعل السياق تعليميًا.\n"
                "- أعد JSON فقط."
            )
        data = await self._request_json(user_prompt, temperature=1.0, language=lang)
        if not data:
            return None
        return _parse_simulation(data, lang)

    async def generate_daily_challenge(
        self,
        *,
        level: str,
        focus: str,
        language: str = "ar",
    ) -> Optional[Dict[str, Any]]:
        lang = _lang(language)
        if lang == "en":
            user_prompt = (
                "Create one daily trading analysis challenge in strict JSON.\n"
                f"Level: {level}\n"
                f"Focus: {focus}\n\n"
                "JSON schema:\n"
                "{\n"
                '  "prompt": "Daily Challenge: ...",\n'
                '  "expected_keywords": ["risk","invalidation","confirmation","structure"]\n'
                "}\n\n"
                "Rules:\n"
                "- Require analytical reasoning, not guessing.\n"
                "- Include invalidation and risk.\n"
                "- If prices appear, use DZD.\n"
                "- Return exactly 4 keywords.\n"
                "- Return JSON only."
            )
        else:
            user_prompt = (
                "أنشئ تحدي تحليل تداول يومي واحد بصيغة JSON صارمة وباللغة العربية.\n"
                f"المستوى: {level}\n"
                f"التركيز: {focus}\n\n"
                "مخطط JSON:\n"
                "{\n"
                '  "prompt": "تحدي اليوم: ...",\n'
                '  "expected_keywords": ["مخاطرة","إبطال","تأكيد","هيكل"]\n'
                "}\n\n"
                "القواعد:\n"
                "- يجب أن يطلب السؤال تحليلًا ومنطقًا وليس تخمينًا.\n"
                "- يجب أن يتضمن إبطال الفكرة والمخاطرة.\n"
                "- إذا احتوى على أسعار فلتكن بالدينار الجزائري (DZD/دج).\n"
                "- أعد 4 كلمات مفتاحية بالضبط.\n"
                "- أعد JSON فقط."
            )
        data = await self._request_json(user_prompt, temperature=1.0, language=lang)
        if not data:
            return None
        return _parse_daily_challenge(data, lang)

    async def _request_json(
        self,
        user_prompt: str,
        temperature: float = 1.0,
        timeout_seconds: Optional[float] = None,
        respect_suspend: bool = True,
        language: str = "ar",
    ) -> Optional[Dict[str, Any]]:
        lang = _lang(language)
        if respect_suspend and time.time() < self._suspend_until:
            return None

        request_timeout = max(3.0, timeout_seconds if timeout_seconds is not None else self._timeout_seconds)
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPTS[lang]},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if "openrouter.ai" not in self._base_url:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in self._base_url:
            if self._site_url:
                headers["HTTP-Referer"] = self._site_url
            if self._app_name:
                headers["X-Title"] = self._app_name

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await asyncio.wait_for(
                    client.post(self._base_url, headers=headers, json=payload),
                    timeout=request_timeout,
                )
            body = response.json()
        except asyncio.TimeoutError:
            self._last_error = "timeout"
            if respect_suspend:
                self._suspend_until = time.time() + 20
            return None
        except httpx.TimeoutException:
            self._last_error = "timeout"
            if respect_suspend:
                self._suspend_until = time.time() + 20
            return None
        except (httpx.HTTPError, ValueError):
            self._last_error = "network_error"
            if respect_suspend:
                self._suspend_until = time.time() + 60
            return None

        if response.status_code >= 400:
            self._last_error = _extract_error_code(body) or f"http_{response.status_code}"
            if respect_suspend:
                if response.status_code in {401, 403}:
                    self._suspend_until = time.time() + 300
                elif response.status_code == 429:
                    if self._last_error == "insufficient_quota":
                        self._suspend_until = time.time() + 1800
                    else:
                        self._suspend_until = time.time() + 120
                else:
                    self._suspend_until = time.time() + 60
            return None

        content = _extract_content(body)
        if not content:
            self._last_error = "empty_content"
            return None

        raw = _extract_json_block(content)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            self._last_error = "invalid_json"
            return None
        if isinstance(parsed, list):
            parsed = {"quiz": parsed}
        if not isinstance(parsed, dict):
            self._last_error = "invalid_json_shape"
            return None
        self._last_error = ""
        return parsed


def _extract_content(body: Dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _extract_error_code(body: Dict[str, Any]) -> str:
    error = body.get("error")
    if not isinstance(error, dict):
        return ""
    code = error.get("code")
    if isinstance(code, str):
        return code.strip()
    error_type = error.get("type")
    if isinstance(error_type, str):
        return error_type.strip()
    message = error.get("message")
    if isinstance(message, str):
        normalized = message.strip().lower().replace(" ", "_")
        return normalized[:80]
    return ""


def _extract_json_block(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    list_start = stripped.find("[")
    list_end = stripped.rfind("]")
    if list_start != -1 and list_end != -1 and list_end > list_start:
        return stripped[list_start : list_end + 1]
    return "{}"


def _parse_lesson(data: Dict[str, Any], level: str, language: str) -> Optional[Lesson]:
    lang = _lang(language)
    if lang == "en":
        title_default = "AI Lesson"
        objective_default = "Build a disciplined process that starts with risk management."
        example_default = "Plan the trade before entry with clear invalidation."
    else:
        title_default = "درس ذكاء اصطناعي"
        objective_default = "بناء عملية تداول منضبطة تبدأ بإدارة المخاطر."
        example_default = "خطط للصفقة قبل الدخول مع تحديد نقطة الإبطال."

    title = _safe_text(data.get("title"), title_default)
    objective = _safe_text(data.get("objective"), objective_default)
    bullet_points = _safe_list_of_text(data.get("bullet_points"), fallback_count=4)
    if len(bullet_points) < 4:
        bullet_points = (bullet_points + _fallback_bullets(lang))[:4]
    example = _safe_text(data.get("example"), example_default)
    quiz = _parse_quiz(data.get("quiz"), lang)

    return Lesson(
        lesson_id=f"AI-{uuid.uuid4().hex[:10]}",
        level=level,
        title=title,
        objective=objective,
        bullet_points=bullet_points[:4],
        example=example,
        quiz=quiz,
        premium_only=False,
    )


def _parse_quiz(raw: Any, language: str) -> List[QuizQuestion]:
    if not isinstance(raw, list):
        return []
    lang = _lang(language)
    fallback_expl = "Review risk logic first." if lang == "en" else "راجع منطق إدارة المخاطر أولًا."

    parsed: List[QuizQuestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        prompt = _safe_text(item.get("prompt") or item.get("question"), "")
        explanation = _safe_text(item.get("explanation") or item.get("reasoning") or item.get("why"), fallback_expl)
        options_raw = item.get("options") or item.get("choices")
        options = _normalize_options(options_raw)
        if not prompt or len(options) < 4:
            continue
        answer = _normalize_answer(item.get("answer") or item.get("correct_answer") or item.get("correct"), options)
        parsed.append(
            QuizQuestion(
                prompt=prompt,
                options=options,
                answer=answer,
                explanation=explanation,
            )
        )
    return parsed


def _normalize_options(options_raw: Any) -> Dict[str, str]:
    if isinstance(options_raw, dict):
        normalized: Dict[str, str] = {}
        for key in ("A", "B", "C", "D"):
            value = options_raw.get(key) or options_raw.get(key.lower())
            if isinstance(value, str) and value.strip():
                normalized[key] = value.strip()
        if len(normalized) == 4:
            return normalized

    if isinstance(options_raw, list):
        values: List[str] = []
        for item in options_raw:
            if isinstance(item, dict):
                value = item.get("text") or item.get("option") or item.get("value")
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
                continue
            text = str(item).strip()
            if text:
                values.append(text)
        if len(values) >= 4:
            return {k: values[i] for i, k in enumerate(("A", "B", "C", "D"))}
    return {}


def _normalize_answer(raw_answer: Any, options: Dict[str, str]) -> str:
    if isinstance(raw_answer, str):
        key = raw_answer.strip().upper()
        if key in options:
            return key
        for option_key, option_text in options.items():
            if option_text.strip().lower() == raw_answer.strip().lower():
                return option_key
    if isinstance(raw_answer, int):
        keys = ("A", "B", "C", "D")
        if 1 <= raw_answer <= 4:
            return keys[raw_answer - 1]
    return "A"


def _parse_simulation(data: Dict[str, Any], language: str) -> Optional[Dict[str, Any]]:
    lang = _lang(language)
    symbol = _safe_text(data.get("symbol"), "")
    entry = _safe_float(data.get("entry"))
    support = _safe_float(data.get("support"))
    resistance = _safe_float(data.get("resistance"))
    default_context = "Use your plan, not predictions." if lang == "en" else "اعتمد على الخطة لا على التوقع."
    context = _safe_text(data.get("context"), default_context)
    if not symbol or entry is None or support is None or resistance is None:
        return None
    return {
        "symbol": symbol.upper(),
        "entry": entry,
        "support": support,
        "resistance": resistance,
        "context": context,
    }


def _parse_daily_challenge(data: Dict[str, Any], language: str) -> Optional[Dict[str, Any]]:
    lang = _lang(language)
    prompt = _safe_text(data.get("prompt"), "")
    keywords = _safe_list_of_text(data.get("expected_keywords"), fallback_count=4)[:4]
    if len(keywords) < 4:
        keywords = (
            ["risk", "invalidation", "structure", "confirmation"]
            if lang == "en"
            else ["مخاطرة", "إبطال", "هيكل", "تأكيد"]
        )
    if not prompt:
        return None
    prompt_lower = prompt.lower()
    if lang == "en":
        if not prompt_lower.startswith("daily challenge"):
            prompt = f"Daily Challenge: {prompt}"
    else:
        if not (prompt_lower.startswith("تحدي اليوم") or prompt_lower.startswith("daily challenge")):
            prompt = f"تحدي اليوم: {prompt}"
    return {
        "prompt": prompt,
        "expected_keywords": keywords,
    }


def _safe_text(value: Any, default: str) -> str:
    if isinstance(value, str):
        normalized = re.sub(r"\s+", " ", value).strip()
        if normalized:
            return normalized
    return default


def _safe_list_of_text(value: Any, fallback_count: int = 0) -> List[str]:
    if isinstance(value, list):
        items: List[str] = []
        for item in value:
            if isinstance(item, str):
                normalized = re.sub(r"\s+", " ", item).strip()
                if normalized:
                    items.append(normalized)
        return items
    return [""] * fallback_count if fallback_count else []


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ensure_quiz_count(quiz: List[QuizQuestion], count: int, language: str) -> List[QuizQuestion]:
    if count <= 0:
        return []
    if len(quiz) >= count:
        return quiz[:count]

    padded = list(quiz)
    seed = _fallback_quiz(language)
    index = 0
    while len(padded) < count:
        base = seed[index % len(seed)]
        suffix = len(padded) + 1
        padded.append(
            QuizQuestion(
                prompt=f"{base.prompt} ({suffix})",
                options=dict(base.options),
                answer=base.answer,
                explanation=base.explanation,
            )
        )
        index += 1
    return padded


def _fallback_bullets(language: str) -> List[str]:
    if _lang(language) == "en":
        return [
            "Define invalidation before every entry.",
            "Use small, consistent risk per trade.",
            "Avoid emotional and revenge trading.",
            "Journal executions and review process quality.",
        ]
    return [
        "حدد نقطة الإبطال قبل دخول أي صفقة.",
        "خاطر بنسبة صغيرة وثابتة في كل صفقة.",
        "تجنب الدخول العاطفي وتداول الانتقام.",
        "سجل تنفيذك وراجع جودة العملية.",
    ]


def _fallback_quiz(language: str) -> List[QuizQuestion]:
    if _lang(language) == "en":
        return [
            QuizQuestion(
                prompt="What must be defined before any entry?",
                options={
                    "A": "Invalidation point and risk limit",
                    "B": "Guaranteed outcome",
                    "C": "Maximum leverage",
                    "D": "A social media signal",
                },
                answer="A",
                explanation="Every trade needs invalidation and controlled risk.",
            ),
            QuizQuestion(
                prompt="Which mindset is more professional?",
                options={
                    "A": "Win every trade",
                    "B": "Process consistency over short-term outcomes",
                    "C": "Double risk after a loss",
                    "D": "Enter every opportunity",
                },
                answer="B",
                explanation="Professional growth comes from repeatable process quality.",
            ),
        ]
    return [
        QuizQuestion(
            prompt="ما الذي يجب تحديده قبل أي دخول؟",
            options={
                "A": "نقطة الإبطال وحد المخاطرة",
                "B": "نتيجة مضمونة",
                "C": "أعلى رافعة ممكنة",
                "D": "إشارة من مواقع التواصل",
            },
            answer="A",
            explanation="كل صفقة تحتاج نقطة إبطال ومخاطرة منضبطة.",
        ),
        QuizQuestion(
            prompt="أي عقلية هي الأكثر احترافية؟",
            options={
                "A": "الربح في كل صفقة",
                "B": "ثبات العملية أهم من النتائج القصيرة",
                "C": "مضاعفة المخاطرة بعد الخسارة",
                "D": "الدخول في كل فرصة",
            },
            answer="B",
            explanation="النمو الاحترافي يأتي من جودة عملية قابلة للتكرار.",
        ),
    ]
