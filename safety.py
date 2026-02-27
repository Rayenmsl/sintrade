from __future__ import annotations

import re

UNREALISTIC_PATTERNS = [
    r"100\s*%\s*win",
    r"win\s*every\s*trade",
    r"guaranteed\s*(profit|strategy|signal)",
    r"no\s*loss",
    r"make\s*me\s*rich\s*(today|fast)",
    r"sure\s*signal",
    r"guarantee\s*profits",
    r"ربح\s*مضمون",
    r"بدون\s*خسارة",
    r"اربحني\s*(اليوم|بسرعة)",
]

SAFETY_REFUSAL = (
    "لا أستطيع تقديم أنظمة ربح مضمون أو توصيات يقينية. "
    "لا توجد استراتيجية تربح كل صفقة، والخسائر جزء طبيعي من التداول."
)


def is_unrealistic_request(text: str) -> bool:
    lowered = text.lower().strip()
    return any(re.search(pattern, lowered) for pattern in UNREALISTIC_PATTERNS)

