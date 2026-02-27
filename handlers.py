from __future__ import annotations

import random
import re
from typing import List, Optional, Set

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .ai_content import AIContentClient
from .config import (
    get_openai_api_key,
    get_openai_app_name,
    get_openai_base_url,
    get_openai_model,
    get_openai_site_url,
    get_openai_timeout_seconds,
)
from .content import (
    DAILY_CHALLENGES,
    LEVEL_ORDER,
    PREMIUM_LOCK_MESSAGE,
    RISK_REMINDER,
    SIMULATION_SCENARIOS,
    level_label,
    lessons_for_user,
    next_level,
)
from .models import DailyChallengeState, Lesson, QuizState, SimulationState, UserSession
from .quiz_generator import build_random_quiz_for_lesson
from .safety import SAFETY_REFUSAL, is_unrealistic_request
from .session_store import session_store

LANG_AR = "ar"
LANG_EN = "en"
SUPPORTED_LANGUAGES = {LANG_AR, LANG_EN}

BUTTON_LABELS = {
    LANG_AR: {
        "lesson": "📚 درس",
        "simulation": "🧪 محاكاة",
        "daily": "🎯 تحدي اليوم",
        "status": "📊 الحالة",
        "profile": "⚙️ الملف الشخصي",
        "help": "ℹ️ المساعدة",
        "menu": "🏠 القائمة",
        "kill": "🛑 إلغاء",
        "reset": "🔄 إعادة تعيين",
        "language": "🌐 اللغة",
        "askme": "💬 اسألني",
    },
    LANG_EN: {
        "lesson": "📚 Lesson",
        "simulation": "🧪 Simulation",
        "daily": "🎯 Daily Challenge",
        "status": "📊 Status",
        "profile": "⚙️ Profile",
        "help": "ℹ️ Help",
        "menu": "🏠 Menu",
        "kill": "🛑 Kill",
        "reset": "🔄 Reset",
        "language": "🌐 Language",
        "askme": "💬 Ask Me",
    },
}

BTN_LESSON = BUTTON_LABELS[LANG_AR]["lesson"]
BTN_SIMULATION = BUTTON_LABELS[LANG_AR]["simulation"]
BTN_DAILY_CHALLENGE = BUTTON_LABELS[LANG_AR]["daily"]
BTN_STATUS = BUTTON_LABELS[LANG_AR]["status"]
BTN_PROFILE = BUTTON_LABELS[LANG_AR]["profile"]
BTN_HELP = BUTTON_LABELS[LANG_AR]["help"]
BTN_MENU = BUTTON_LABELS[LANG_AR]["menu"]
BTN_KILL = BUTTON_LABELS[LANG_AR]["kill"]
BTN_RESET = BUTTON_LABELS[LANG_AR]["reset"]
BTN_LANGUAGE = BUTTON_LABELS[LANG_AR]["language"]

CB_ACTION_LESSON = "act:lesson"
CB_ACTION_SIMULATION = "act:simulation"
CB_ACTION_DAILY = "act:daily"
CB_ACTION_STATUS = "act:status"
CB_ACTION_PROFILE = "act:profile"
CB_ACTION_ASKME = "act:askme"
CB_ACTION_ASKME_QUIT = "act:askme_quit"
CB_ACTION_KILL = "act:kill"
CB_ACTION_RESET = "act:reset"

CB_MENU_MAIN = "menu:main"
CB_MENU_PROFILE = "menu:profile"
CB_MENU_LEVEL = "menu:level"
CB_MENU_ACCESS = "menu:access"
CB_MENU_FOCUS = "menu:focus"
CB_MENU_LANGUAGE = "menu:language"

CB_SET_LEVEL_PREFIX = "set:level:"
CB_SET_ACCESS_PREFIX = "set:access:"
CB_SET_FOCUS_PREFIX = "set:focus:"
CB_SET_LANGUAGE_PREFIX = "set:lang:"

CB_LESSON_COMPLETE_PREFIX = "lesson:complete:"
CB_QUIZ_PREFIX = "quiz:"
CB_SIM_DIR_PREFIX = "simdir:"

_AI_CLIENT: Optional[AIContentClient] = None
EMOJI_TRUE = "✅"
EMOJI_FALSE = "❌"
DEVELOPER_CONTACT = "@is_Ray_X"
ADMIN_USERNAME = "is_ray_x"
AI_TOTAL_LESSONS = 100
AI_QUIZ_PER_LESSON = 50


def _get_ai_client() -> Optional[AIContentClient]:
    global _AI_CLIENT
    if _AI_CLIENT is not None:
        return _AI_CLIENT

    api_key = get_openai_api_key()
    if not api_key:
        return None

    _AI_CLIENT = AIContentClient(
        api_key=api_key,
        model=get_openai_model(),
        base_url=get_openai_base_url(),
        site_url=get_openai_site_url(),
        app_name=get_openai_app_name(),
        timeout_seconds=get_openai_timeout_seconds(),
    )
    return _AI_CLIENT


def _content_mode_label(session: Optional[UserSession] = None) -> str:
    client = _get_ai_client()
    if client is None:
        return _t(session, "منهج مدمج", "Built-in curriculum")
    return client.status_label(language=_lang(session))


def _get_session(update: Update) -> Optional[UserSession]:
    user = update.effective_user
    if user is None:
        return None
    session = session_store.get(user.id)
    if session.access == "premium":
        session.access = "free"
    return session


def _active_message(update: Update) -> Optional[Message]:
    if update.message is not None:
        return update.message
    if update.callback_query is not None and isinstance(update.callback_query.message, Message):
        return update.callback_query.message
    return None


def _bool_emoji(value: bool) -> str:
    return EMOJI_TRUE if value else EMOJI_FALSE


def _lang(session: Optional[UserSession]) -> str:
    if session is None:
        return LANG_AR
    return session.language if session.language in SUPPORTED_LANGUAGES else LANG_AR


def _t(session: Optional[UserSession], ar_text: str, en_text: str) -> str:
    return en_text if _lang(session) == LANG_EN else ar_text


def _btn(session: Optional[UserSession], key: str) -> str:
    lang = _lang(session)
    return BUTTON_LABELS.get(lang, BUTTON_LABELS[LANG_AR]).get(key, key)


def _button_variants(key: str) -> Set[str]:
    return {
        BUTTON_LABELS[LANG_AR].get(key, key),
        BUTTON_LABELS[LANG_EN].get(key, key),
    }


def _language_label(value: str, session: Optional[UserSession]) -> str:
    labels = {
        LANG_AR: {"ar": "العربية", "en": "الإنجليزية"},
        LANG_EN: {"ar": "Arabic", "en": "English"},
    }
    lang = _lang(session)
    return labels[lang].get(value, value)


def _level_label(level: str, session: Optional[UserSession]) -> str:
    if _lang(session) == LANG_EN:
        return {
            "beginner": "Level 1 - Beginner",
            "intermediate": "Level 2 - Intermediate",
            "advanced": "Level 3 - Advanced",
            "professional": "Level 4 - Professional",
        }.get(level, level.title())
    return level_label(level)


def _access_label(access: str, session: Optional[UserSession]) -> str:
    if _lang(session) == LANG_EN:
        return {"free": "Free", "premium": "Premium"}.get(access, access)
    return {"free": "مجاني", "premium": "بريميوم"}.get(access, access)


def _focus_label(focus: str, session: Optional[UserSession]) -> str:
    if _lang(session) == LANG_EN:
        return {"spot": "Spot", "futures": "Futures", "both": "Both"}.get(focus, focus)
    return {"spot": "سبوت", "futures": "فيوتشرز", "both": "كلاهما"}.get(focus, focus)


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    return (user.username or "").strip().lower() == ADMIN_USERNAME


def _admin_only_message(session: Optional[UserSession] = None) -> str:
    return _t(
        session,
        f"{EMOJI_FALSE} مقيد. هذا الإجراء للإدارة فقط. تواصل مع {DEVELOPER_CONTACT}.",
        f"{EMOJI_FALSE} Restricted. This action is admin-only. Contact {DEVELOPER_CONTACT}.",
    )


def _premium_info_message(session: Optional[UserSession] = None) -> str:
    if _lang(session) == LANG_EN:
        return (
            "🔒 Premium Courses Preview\n\n"
            "Premium includes:\n"
            "- Full advanced and professional frameworks\n"
            "- Deeper strategy design and execution planning\n"
            "- More advanced learning tracks and guided practice\n\n"
            f"To subscribe, contact the developer: {DEVELOPER_CONTACT}"
        )
    return (
        "🔒 معاينة دورات البريميوم\n\n"
        "ماذا يشمل البريميوم:\n"
        "- أطر متقدمة كاملة وأنظمة احترافية\n"
        "- بناء استراتيجي أعمق وخطط تنفيذ أدق\n"
        "- مسارات دراسية أكثر عمقًا وتطبيقات موجهة\n\n"
        f"للاشتراك تواصل مع المطور: {DEVELOPER_CONTACT}"
    )


def _completion_thanks_text(session: Optional[UserSession] = None) -> str:
    if _lang(session) == LANG_EN:
        return (
            "Thank you for using Sin Trade AI bot.\n"
            "If this bot helped you, please share it with your friends.\n"
            f"Developer: {DEVELOPER_CONTACT}"
        )
    return (
        "شكرًا لاستخدامك بوت Sin Trade AI.\n"
        "إذا أفادك البوت، شاركه مع أصدقائك.\n"
        f"المطور: {DEVELOPER_CONTACT}"
    )


def _sync_ai_curriculum_level(session: UserSession) -> None:
    if session.ai_lessons_completed >= 75:
        session.level = "professional"
    elif session.ai_lessons_completed >= 50:
        session.level = "advanced"
    elif session.ai_lessons_completed >= 25:
        session.level = "intermediate"
    else:
        session.level = "beginner"


def _commands_text(session: Optional[UserSession] = None) -> str:
    if _lang(session) == LANG_EN:
        return (
            "Commands (fallback):\n"
            "/lesson - get your next lesson\n"
            "/setlevel beginner|intermediate|advanced|professional (admin only)\n"
            "/setaccess free|premium (admin only)\n"
            "/setfocus spot|futures|both (admin only)\n"
            "/simulate - start a training simulation\n"
            "/dailychallenge - get a daily analysis challenge\n"
            "/buttons - show buttons again\n"
            "/kill - cancel active lesson/quiz/simulation/challenge\n"
            "/status - show your progress\n"
            "/profile - open profile settings\n"
            "/language - choose bot language (Arabic/English)\n"
            "/menu - open actions menu\n"
            "/reset - reset session"
        )
    return (
        "الأوامر (احتياطية):\n"
        "/lesson - الحصول على الدرس التالي حسب مستواك\n"
        "/setlevel beginner|intermediate|advanced|professional (للإدارة فقط)\n"
        "/setaccess free|premium (للإدارة فقط)\n"
        "/setfocus spot|futures|both (للإدارة فقط)\n"
        "/simulate - بدء محاكاة تداول تدريبية\n"
        "/dailychallenge - الحصول على تحدي تحليل يومي\n"
        "/buttons - إظهار الأزرار مرة أخرى\n"
        "/kill - إلغاء الدرس/الاختبار/المحاكاة/التحدي النشط\n"
        "/status - عرض تقدمك\n"
        "/profile - فتح إعدادات الملف الشخصي\n"
        "/language - اختيار لغة البوت (العربية/الإنجليزية)\n"
        "/menu - فتح لوحة الإجراءات\n"
        "/reset - إعادة تعيين الجلسة"
    )


def _main_reply_keyboard(session: Optional[UserSession] = None) -> ReplyKeyboardMarkup:
    keyboard = [
        [_btn(session, "lesson"), _btn(session, "simulation")],
        [_btn(session, "language"), _btn(session, "status")],
        [_btn(session, "daily"), _btn(session, "profile")],
        [_btn(session, "askme"), _btn(session, "help")],
        [_btn(session, "kill"), _btn(session, "reset")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def _main_inline_keyboard(session: Optional[UserSession] = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(_btn(session, "lesson"), callback_data=CB_ACTION_LESSON),
                InlineKeyboardButton(_btn(session, "simulation"), callback_data=CB_ACTION_SIMULATION),
            ],
            [
                InlineKeyboardButton(_btn(session, "daily"), callback_data=CB_ACTION_DAILY),
                InlineKeyboardButton(_btn(session, "status"), callback_data=CB_ACTION_STATUS),
            ],
            [
                InlineKeyboardButton(_btn(session, "askme"), callback_data=CB_ACTION_ASKME),
                InlineKeyboardButton(_btn(session, "profile"), callback_data=CB_ACTION_PROFILE),
            ],
            [
                InlineKeyboardButton(_btn(session, "kill"), callback_data=CB_ACTION_KILL),
                InlineKeyboardButton(_btn(session, "reset"), callback_data=CB_ACTION_RESET),
            ],
        ]
    )


def _profile_menu_keyboard(session: UserSession, is_admin: bool = False) -> InlineKeyboardMarkup:
    lang_text = _t(session, "اللغة", "Language")
    main_menu_text = _t(session, "🏠 القائمة الرئيسية", "🏠 Main Menu")
    if not is_admin:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(f"🔒 {_t(session, 'المستوى', 'Level')}: {_level_label(session.level, session)}", callback_data=CB_MENU_LEVEL)],
                [InlineKeyboardButton(_t(session, "🔒 دورات البريميوم", "🔒 Premium Courses"), callback_data=CB_MENU_ACCESS)],
                [InlineKeyboardButton(f"🔒 {_t(session, 'التركيز', 'Focus')}: {_focus_label(session.focus, session)}", callback_data=CB_MENU_FOCUS)],
                [InlineKeyboardButton(f"🌐 {lang_text}: {_language_label(_lang(session), session)}", callback_data=CB_MENU_LANGUAGE)],
                [InlineKeyboardButton(main_menu_text, callback_data=CB_MENU_MAIN)],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"{_t(session, 'المستوى', 'Level')}: {_level_label(session.level, session)}", callback_data=CB_MENU_LEVEL)],
            [InlineKeyboardButton(f"{_t(session, 'الوصول', 'Access')}: {_access_label(session.access, session)}", callback_data=CB_MENU_ACCESS)],
            [InlineKeyboardButton(f"{_t(session, 'التركيز', 'Focus')}: {_focus_label(session.focus, session)}", callback_data=CB_MENU_FOCUS)],
            [InlineKeyboardButton(f"🌐 {lang_text}: {_language_label(_lang(session), session)}", callback_data=CB_MENU_LANGUAGE)],
            [InlineKeyboardButton(main_menu_text, callback_data=CB_MENU_MAIN)],
        ]
    )


def _level_selection_keyboard(session: UserSession) -> InlineKeyboardMarkup:
    rows = []
    for level in LEVEL_ORDER:
        marker = _bool_emoji(session.level == level)
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {_level_label(level, session)}",
                    callback_data=f"{CB_SET_LEVEL_PREFIX}{level}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(_t(session, "⬅️ رجوع للملف الشخصي", "⬅️ Back to Profile"), callback_data=CB_MENU_PROFILE)])
    return InlineKeyboardMarkup(rows)


def _access_selection_keyboard(session: UserSession) -> InlineKeyboardMarkup:
    rows = []
    for access in ("free", "premium"):
        is_selected = session.access == access
        marker = _bool_emoji(is_selected)
        label = _access_label(access, session)
        if access == "premium":
            label = _t(session, "🔒 بريميوم", "🔒 Premium")
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {label}",
                    callback_data=f"{CB_SET_ACCESS_PREFIX}{access}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(_t(session, "⬅️ رجوع للملف الشخصي", "⬅️ Back to Profile"), callback_data=CB_MENU_PROFILE)])
    return InlineKeyboardMarkup(rows)


def _focus_selection_keyboard(session: UserSession) -> InlineKeyboardMarkup:
    rows = []
    for focus in ("spot", "futures", "both"):
        marker = _bool_emoji(session.focus == focus)
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {_focus_label(focus, session)}",
                    callback_data=f"{CB_SET_FOCUS_PREFIX}{focus}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(_t(session, "⬅️ رجوع للملف الشخصي", "⬅️ Back to Profile"), callback_data=CB_MENU_PROFILE)])
    return InlineKeyboardMarkup(rows)


def _language_selection_keyboard(session: UserSession) -> InlineKeyboardMarkup:
    rows = []
    for lang_code in (LANG_AR, LANG_EN):
        marker = _bool_emoji(_lang(session) == lang_code)
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker} {_language_label(lang_code, session)}",
                    callback_data=f"{CB_SET_LANGUAGE_PREFIX}{lang_code}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(_t(session, "⬅️ رجوع للملف الشخصي", "⬅️ Back to Profile"), callback_data=CB_MENU_PROFILE)])
    return InlineKeyboardMarkup(rows)


def _simulation_direction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📈 لونغ", callback_data=f"{CB_SIM_DIR_PREFIX}long"),
                InlineKeyboardButton("📉 شورت", callback_data=f"{CB_SIM_DIR_PREFIX}short"),
            ]
        ]
    )


def _quiz_keyboard(session: UserSession) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("A", callback_data=f"{CB_QUIZ_PREFIX}A"),
                InlineKeyboardButton("B", callback_data=f"{CB_QUIZ_PREFIX}B"),
            ],
            [
                InlineKeyboardButton("C", callback_data=f"{CB_QUIZ_PREFIX}C"),
                InlineKeyboardButton("D", callback_data=f"{CB_QUIZ_PREFIX}D"),
            ],
            [
                InlineKeyboardButton(_t(session, "🏠 القائمة", "🏠 Menu"), callback_data=CB_MENU_MAIN),
                InlineKeyboardButton(_btn(session, "kill"), callback_data=CB_ACTION_KILL),
            ],
        ]
    )


def _lesson_complete_keyboard(session: UserSession, lesson_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(session, "✅ إكمال", "✅ Complete"), callback_data=f"{CB_LESSON_COMPLETE_PREFIX}{lesson_id}")],
            [
                InlineKeyboardButton(_t(session, "🏠 القائمة", "🏠 Menu"), callback_data=CB_MENU_MAIN),
                InlineKeyboardButton(_btn(session, "kill"), callback_data=CB_ACTION_KILL),
            ],
        ]
    )


def _askme_keyboard(session: UserSession) -> InlineKeyboardMarkup:
    """Keyboard shown during AI assistant conversation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(_t(session, "❌ إنهاء المحادثة", "❌ End Chat"), callback_data=CB_ACTION_ASKME_QUIT)],
        ]
    )


def _profile_summary(session: UserSession) -> str:
    return (
        f"- {_t(session, 'المستوى', 'Level')}: {_level_label(session.level, session)}\n"
        f"- {_t(session, 'الوصول', 'Access')}: {EMOJI_TRUE if session.access == 'premium' else EMOJI_FALSE} {_access_label(session.access, session)}\n"
        f"- {_t(session, 'التركيز', 'Focus')}: {_focus_label(session.focus, session)}\n"
        f"- {_t(session, 'اللغة', 'Language')}: {_language_label(_lang(session), session)}"
    )


def _menu_panel_text(session: UserSession) -> str:
    return _t(session, "اضغط على أيقونة للمتابعة.", "Tap an icon to continue.")


def _kill_active_states(session: UserSession) -> List[str]:
    killed: List[str] = []
    if session.pending_lesson is not None:
        session.pending_lesson = None
        killed.append(_t(session, "درس", "lesson"))
    if session.quiz_state is not None:
        session.quiz_state = None
        killed.append(_t(session, "اختبار", "quiz"))
    if session.simulation_state is not None:
        session.simulation_state = None
        killed.append(_t(session, "محاكاة", "simulation"))
    if session.daily_challenge_state is not None:
        session.daily_challenge_state = None
        killed.append(_t(session, "تحدي يومي", "daily challenge"))
    if session.assistant_mode:
        session.assistant_mode = False
        killed.append(_t(session, "مساعد ذكي", "AI assistant"))
    return killed


def _remember_ai_lesson_title(session: UserSession, lesson: Lesson) -> None:
    session.ai_recent_lesson_titles.append(lesson.title)
    session.ai_recent_lesson_titles = session.ai_recent_lesson_titles[-30:]


def _remember_ai_quiz_prompts(session: UserSession, prompts: List[str]) -> None:
    for prompt in prompts:
        session.ai_recent_quiz_prompts.append(prompt)
    session.ai_recent_quiz_prompts = session.ai_recent_quiz_prompts[-80:]


async def _reply(update: Update, text: str, reply_markup=None) -> None:
    message = _active_message(update)
    if message is None:
        return
    await message.reply_text(text, reply_markup=reply_markup)


async def _edit_or_reply(update: Update, text: str, reply_markup=None) -> None:
    query = update.callback_query
    if query is None or not isinstance(query.message, Message):
        await _reply(update, text, reply_markup=reply_markup)
        return
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest:
        await query.message.reply_text(text, reply_markup=reply_markup)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    message = _active_message(update)
    if session is None or message is None:
        return

    intro = _t(
        session,
        (
            "مرحبًا بك في Sin Trade AI.\n\n"
            "هذا البوت مساعد تعليمي في التداول يساعدك على التعلم خطوة بخطوة "
            "من خلال الدروس والاختبارات والمحاكاة وتحديات التحليل اليومية. "
            "يركز على إدارة المخاطر والانضباط وبناء العادات الاحترافية. "
            "استخدم الأزرار بالأسفل للبدء.\n\n"
            f"المطور: {DEVELOPER_CONTACT}"
        ),
        (
            "Welcome to Sin Trade AI.\n\n"
            "This bot is an educational trading assistant to help you learn step by step "
            "through lessons, quizzes, simulations, and daily analysis challenges. "
            "It focuses on risk management, discipline, and professional habits. "
            "Use the buttons below to start.\n\n"
            f"Developer: {DEVELOPER_CONTACT}"
        ),
    )
    await message.reply_text(intro, reply_markup=_main_reply_keyboard(session))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    await _reply(
        update,
        _t(session, f"{_commands_text(session)}\n\nاستخدم الأزرار لتجربة أسهل.", f"{_commands_text(session)}\n\nUse buttons for an easier flow."),
        reply_markup=_main_reply_keyboard(session),
    )


async def askme_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    session.assistant_mode = True
    await _reply(
        update,
        _t(
            session,
            "💬 سؤالني أي سؤال عن التداول وسأجيبك!",
            "💬 Ask me any question about trading and I'll answer!",
        ),
        reply_markup=_main_reply_keyboard(session),
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    await _reply(update, "👇", reply_markup=_main_reply_keyboard(session))


async def buttons_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    message = _active_message(update)
    if session is None or message is None:
        return
    await message.reply_text("👇", reply_markup=_main_reply_keyboard(session))


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    await _reply(
        update,
        _t(session, "اختر اللغة:", "Choose language:"),
        reply_markup=_language_selection_keyboard(session),
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    is_admin = _is_admin(update)
    if not is_admin:
        await _reply(
            update,
            _t(
                session,
                (
                    f"الملف الشخصي (قراءة فقط)\n\n{_profile_summary(session)}\n\n"
                    "كل الخيارات قابلة للضغط.\n"
                    "البريميوم يعرض التفاصيل، وباقي خيارات الإدارة مقيدة."
                ),
                (
                    f"Profile (read-only)\n\n{_profile_summary(session)}\n\n"
                    "All options are clickable.\n"
                    "Premium shows details, while admin settings remain restricted."
                ),
            ),
            reply_markup=_profile_menu_keyboard(session, is_admin=False),
        )
        return
    await _reply(
        update,
        _t(
            session,
            f"إعدادات الملف الشخصي\n\n{_profile_summary(session)}\n\nاختر القسم الذي تريد تعديله.",
            f"Profile Settings\n\n{_profile_summary(session)}\n\nChoose the section you want to edit.",
        ),
        reply_markup=_profile_menu_keyboard(session, is_admin=True),
    )


def _set_level_value(session: UserSession, level: str) -> str:
    if level not in LEVEL_ORDER:
        return f"{EMOJI_FALSE} مستوى غير صالح. القيم المتاحة: beginner | intermediate | advanced | professional."

    session.level = level
    extra = ""
    if session.access == "free" and level in {"advanced", "professional"}:
        extra = (
            "\n\nالمستخدم المجاني يحصل على شرح عام فقط في المستويات المتقدمة. "
            "الأطر الكاملة متاحة للبريميوم."
        )
    return f"{EMOJI_TRUE} تم تحديث المستوى إلى: {_level_label(level, session)}.{extra}"


def _set_access_value(session: UserSession, access: str) -> str:
    if access not in {"free", "premium"}:
        return f"{EMOJI_FALSE} نوع وصول غير صالح. القيم المتاحة: free | premium."
    if access == "premium":
        session.access = "free"
        return (
            f"{EMOJI_FALSE} البريميوم مقفول.\n"
            f"تواصل مع المطور لدورات البريميوم: {DEVELOPER_CONTACT}"
        )
    session.access = access
    return f"{EMOJI_TRUE} تم تحديث الوصول إلى: {_access_label(access, session)}."


def _set_focus_value(session: UserSession, focus: str) -> str:
    if focus not in {"spot", "futures", "both"}:
        return f"{EMOJI_FALSE} تركيز غير صالح. القيم المتاحة: spot | futures | both."
    session.focus = focus
    return f"{EMOJI_TRUE} تم تحديث التركيز إلى: {_focus_label(focus, session)}."


async def setlevel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    if not _is_admin(update):
        await _reply(update, _admin_only_message(session), reply_markup=_main_reply_keyboard(session))
        return
    if not context.args:
        await _reply(update, "الاستخدام: /setlevel beginner|intermediate|advanced|professional")
        return
    level = context.args[0].lower().strip()
    await _reply(update, _set_level_value(session, level), reply_markup=_main_reply_keyboard(session))


async def setaccess_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    if not _is_admin(update):
        await _reply(update, _admin_only_message(session), reply_markup=_main_reply_keyboard(session))
        return
    if not context.args:
        await _reply(update, "الاستخدام: /setaccess free|premium")
        return
    access = context.args[0].lower().strip()
    await _reply(update, _set_access_value(session, access), reply_markup=_main_reply_keyboard(session))


async def setfocus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    if not _is_admin(update):
        await _reply(update, _admin_only_message(session), reply_markup=_main_reply_keyboard(session))
        return
    if not context.args:
        await _reply(update, "الاستخدام: /setfocus spot|futures|both")
        return
    focus = context.args[0].lower().strip()
    await _reply(update, _set_focus_value(session, focus), reply_markup=_main_reply_keyboard(session))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return

    available_lessons = lessons_for_user(session.level, session.access)
    completed = len([lesson for lesson in available_lessons if lesson.lesson_id in session.completed_lessons])
    content_mode = _content_mode_label(session)

    text = _t(
        session,
        (
            "حالة الملف الشخصي\n"
            f"{_profile_summary(session)}\n"
            f"- وضع المحتوى: {content_mode}\n"
            f"- تقدم المنهج: {completed}/{len(available_lessons)} درس مكتمل في المستوى الحالي\n"
            f"- تقدم منهج الذكاء الاصطناعي: {session.ai_lessons_completed}/{AI_TOTAL_LESSONS}\n"
            f"- المحاكاة المكتملة: {session.ai_simulations_completed}\n"
            f"- التحديات المكتملة: {session.ai_challenges_completed}\n"
            f"- درس نشط بانتظار الإكمال: {_bool_emoji(session.pending_lesson is not None)}\n"
            f"- اختبار نشط: {_bool_emoji(session.quiz_state is not None)}\n"
            f"- محاكاة نشطة: {_bool_emoji(session.simulation_state is not None)}\n"
            f"- تحدي يومي قيد الانتظار: {_bool_emoji(session.daily_challenge_state is not None)}"
        ),
        (
            "Profile Status\n"
            f"{_profile_summary(session)}\n"
            f"- Content mode: {content_mode}\n"
            f"- Curriculum progress: {completed}/{len(available_lessons)} lessons completed at current level\n"
            f"- AI curriculum progress: {session.ai_lessons_completed}/{AI_TOTAL_LESSONS}\n"
            f"- Completed simulations: {session.ai_simulations_completed}\n"
            f"- Completed challenges: {session.ai_challenges_completed}\n"
            f"- Pending lesson: {_bool_emoji(session.pending_lesson is not None)}\n"
            f"- Active quiz: {_bool_emoji(session.quiz_state is not None)}\n"
            f"- Active simulation: {_bool_emoji(session.simulation_state is not None)}\n"
            f"- Waiting daily challenge: {_bool_emoji(session.daily_challenge_state is not None)}"
        ),
    )

    await _reply(update, text, reply_markup=_main_reply_keyboard(session))


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None:
        return
    session = session_store.reset(update.effective_user.id)
    await _reply(
        update,
        _t(
            session,
            f"{EMOJI_TRUE} تمت إعادة تعيين الجلسة. استخدم /start للبدء من جديد.",
            f"{EMOJI_TRUE} Session has been reset. Use /start to begin again.",
        ),
        reply_markup=_main_reply_keyboard(session),
    )


async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return
    killed = _kill_active_states(session)
    if not killed:
        await _reply(
            update,
            _t(session, f"{EMOJI_FALSE} لا يوجد شيء نشط لإلغائه.", f"{EMOJI_FALSE} Nothing active to cancel."),
            reply_markup=_main_reply_keyboard(session),
        )
        return
    await _reply(
        update,
        _t(session, f"{EMOJI_TRUE} تم الإلغاء: {', '.join(killed)}.", f"{EMOJI_TRUE} Cancelled: {', '.join(killed)}."),
        reply_markup=_main_reply_keyboard(session),
    )


async def lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return

    # Reset assistant mode if active
    session.assistant_mode = False

    _sync_ai_curriculum_level(session)

    if session.pending_lesson is not None:
        await _reply(
            update,
            f"{EMOJI_FALSE} لديك درس مفتوح بالفعل. اضغط ✅ إكمال أولًا أو استخدم 🛑 إلغاء.",
            reply_markup=_main_reply_keyboard(session),
        )
        return

    if session.quiz_state is not None:
        await _reply(update, f"{EMOJI_FALSE} لديك اختبار نشط. أجب عليه قبل بدء درس جديد.")
        return

    ai_client = _get_ai_client()
    if ai_client is not None:
        if session.ai_lessons_completed >= AI_TOTAL_LESSONS:
            await _reply(
                update,
                (
                    f"{EMOJI_TRUE} أنهيت مسار الذكاء الاصطناعي المكوّن من {AI_TOTAL_LESSONS} درسًا.\n\n"
                    f"{_completion_thanks_text(session)}"
                ),
                reply_markup=_main_reply_keyboard(session),
            )
            return

        ai_lesson = await ai_client.generate_lesson(
            level=session.level,
            access=session.access,
            focus=session.focus,
            recent_titles=session.ai_recent_lesson_titles,
            recent_questions=session.ai_recent_quiz_prompts,
            lesson_number=session.ai_lessons_completed + 1,
            total_lessons=AI_TOTAL_LESSONS,
            language=_lang(session),
        )
        if ai_lesson is not None:
            _remember_ai_lesson_title(session, ai_lesson)
            session.pending_lesson = ai_lesson
            await _reply(
                update,
                _render_lesson(session, ai_lesson),
                reply_markup=_lesson_complete_keyboard(session, ai_lesson.lesson_id),
            )
            return
        error_code = ai_client.last_error_code()
        if error_code:
            await _reply(
                update,
                f"{EMOJI_FALSE} الذكاء الاصطناعي غير متاح ({error_code}). سيتم استخدام المنهج المدمج.",
            )
        else:
            await _reply(
                update,
                f"{EMOJI_FALSE} توليد الذكاء الاصطناعي غير متاح مؤقتًا. سيتم استخدام المنهج المدمج.",
            )

    available_lessons = lessons_for_user(session.level, session.access)
    if not available_lessons:
        await _reply(update, f"{PREMIUM_LOCK_MESSAGE}\n\n{RISK_REMINDER}")
        return

    next_lesson = None
    for lesson in available_lessons:
        if lesson.lesson_id not in session.completed_lessons:
            next_lesson = lesson
            break

    if next_lesson is None:
        next_lvl = next_level(session.level)
        if session.level == "advanced" and session.access == "free":
            done_msg = (
                "أنهيت المحتوى التعريفي المجاني للمستوى المتقدم. "
                "البريميوم يفتح الأطر المتقدمة والأنظمة الاحترافية كاملة."
            )
        elif next_lvl is None:
            done_msg = (
                "لقد أنهيت جميع الدروس المتاحة في ملفك.\n\n"
                f"{_completion_thanks_text(session)}"
            )
        elif next_lvl == "professional" and session.access == "free":
            done_msg = (
                "أنهيت هذا المستوى. المستوى الاحترافي مخصص للبريميوم فقط. "
                "يمكنك إعادة الدروس أو الاستمرار في وضع التدريب."
            )
        else:
            session.level = next_lvl
            done_msg = (
                f"{EMOJI_TRUE} أنهيت هذا المستوى. "
                f"تم فتح: {_level_label(next_lvl, session)}. اضغط درس للمتابعة."
            )
        await _reply(update, f"{done_msg}\n\n{RISK_REMINDER}")
        return

    session.pending_lesson = next_lesson
    await _reply(
        update,
        _render_lesson(session, next_lesson),
        reply_markup=_lesson_complete_keyboard(session, next_lesson.lesson_id),
    )


async def _complete_pending_lesson(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: UserSession,
    lesson_id: str,
) -> None:
    if session.pending_lesson is None:
        await _reply(update, f"{EMOJI_FALSE} لا يوجد درس نشط لإكماله.")
        return

    lesson = session.pending_lesson
    if lesson_id and lesson.lesson_id != lesson_id:
        await _reply(update, f"{EMOJI_FALSE} هذا الدرس لم يعد نشطًا.")
        return

    session.pending_lesson = None

    query = update.callback_query
    if query is not None and isinstance(query.message, Message):
        try:
            await query.edit_message_text(f"{EMOJI_TRUE} تم إكمال الدرس. جاري بدء الاختبار...")
        except BadRequest:
            pass

    is_dynamic = lesson.lesson_id.startswith("AI-")
    questions = []

    if is_dynamic:
        ai_client = _get_ai_client()
        if ai_client is not None:
            questions = await ai_client.generate_lesson_quiz_pack(
                lesson=lesson,
                focus=session.focus,
                recent_questions=session.ai_recent_quiz_prompts,
                quiz_count=AI_QUIZ_PER_LESSON,
                language=_lang(session),
            )
            if questions:
                _remember_ai_quiz_prompts(session, [q.prompt for q in questions])
        if not questions and lesson.quiz:
            questions = lesson.quiz[:AI_QUIZ_PER_LESSON]
        if not questions:
            session.ai_lessons_completed += 1
            await _reply(
                update,
                f"{EMOJI_FALSE} تعذر توليد الاختبار. تم تعليم الدرس كمكتمل بدون اختبار.",
                reply_markup=_main_reply_keyboard(session),
            )
            return
    else:
        questions = build_random_quiz_for_lesson(lesson, session)
        if not questions:
            session.completed_lessons.add(lesson.lesson_id)
            await _reply(
                update,
                f"{EMOJI_TRUE} تم إكمال الدرس. استخدم زر الدرس للموضوع التالي.",
                reply_markup=_main_reply_keyboard(session),
            )
            return

    session.quiz_state = QuizState(
        lesson_id=lesson.lesson_id,
        questions=questions,
        is_dynamic=is_dynamic,
        level=lesson.level,
    )
    await _send_quiz_question(update, session)


async def simulate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return

    # Reset assistant mode if active
    session.assistant_mode = False

    if session.simulation_state is not None:
        await _reply(update, f"{EMOJI_FALSE} توجد محاكاة نشطة بالفعل. أكملها أولًا.")
        return

    scenario = None
    fallback_note = ""
    ai_client = _get_ai_client()
    if ai_client is not None:
        scenario = await ai_client.generate_simulation(level=session.level, focus=session.focus, language=_lang(session))
        error_code = ai_client.last_error_code()
        if scenario is None and error_code:
            fallback_note = f"{EMOJI_FALSE} الذكاء الاصطناعي غير متاح ({error_code}). سيتم استخدام محاكاة مدمجة.\n\n"

    if scenario is None:
        scenario = random.choice(SIMULATION_SCENARIOS)
        scenario_context = ""
    else:
        scenario_context = str(scenario.get("context", "")).strip()

    session.simulation_state = SimulationState(
        symbol=scenario["symbol"],
        entry=scenario["entry"],
        support=scenario["support"],
        resistance=scenario["resistance"],
        context=scenario_context,
    )
    context_line = f"- السياق: {scenario_context}\n" if scenario_context else ""
    text = (
        f"{fallback_note}"
        "محاكاة تداول تدريبية\n"
        f"- الرمز: {scenario['symbol']}\n"
        f"- السعر الحالي: {scenario['entry']:.2f} DZD\n"
        f"- الدعم: {scenario['support']:.2f} DZD\n"
        f"- المقاومة: {scenario['resistance']:.2f} DZD\n\n"
        f"{context_line}"
        "السؤال 1/4: اختر الاتجاه."
    )
    await _reply(update, text, reply_markup=_simulation_direction_keyboard())


async def daily_challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = _get_session(update)
    if session is None:
        return

    # Reset assistant mode if active
    session.assistant_mode = False

    challenge = None
    fallback_note = ""
    ai_client = _get_ai_client()
    if ai_client is not None:
        challenge = await ai_client.generate_daily_challenge(level=session.level, focus=session.focus, language=_lang(session))
        error_code = ai_client.last_error_code()
        if challenge is None and error_code:
            fallback_note = f"{EMOJI_FALSE} الذكاء الاصطناعي غير متاح ({error_code}). سيتم استخدام تحدٍ مدمج.\n\n"
    if challenge is None:
        challenge = random.choice(DAILY_CHALLENGES)

    session.daily_challenge_state = DailyChallengeState(
        prompt=challenge["prompt"],
        expected_keywords=list(challenge["expected_keywords"]),
    )
    text = (
        f"{fallback_note}"
        f"{challenge['prompt']}\n\n"
        "اكتب تحليلك مع التركيز على الهيكل ونقطة الإبطال وإدارة المخاطر."
    )
    await _reply(update, text, reply_markup=_main_reply_keyboard(session))

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    session = _get_session(update)
    if query is None or session is None:
        return
    data = query.data or ""
    if data in {CB_ACTION_LESSON, CB_ACTION_SIMULATION, CB_ACTION_DAILY} or data.startswith(
        CB_LESSON_COMPLETE_PREFIX
    ):
        await query.answer(_t(session, "جارٍ التنفيذ...", "Processing..."))
    else:
        await query.answer()

    if data == CB_ACTION_LESSON:
        await lesson_command(update, context)
        return
    if data == CB_ACTION_SIMULATION:
        await simulate_command(update, context)
        return
    if data == CB_ACTION_DAILY:
        await daily_challenge_command(update, context)
        return
    if data == CB_ACTION_STATUS:
        await status_command(update, context)
        return
    if data == CB_ACTION_PROFILE:
        await profile_command(update, context)
        return
    if data == CB_ACTION_ASKME:
        await askme_command(update, context)
        return
    if data == CB_ACTION_ASKME_QUIT:
        session.assistant_mode = False
        await query.answer()
        await _edit_or_reply(
            update,
            _t(
                session,
                "✅ تم إنهاء المحادثة مع الذكاء الاصطناعي.",
                "✅ AI chat session ended.",
            ),
        )
        await _reply(update, "👇", reply_markup=_main_reply_keyboard(session))
        return
    if data == CB_ACTION_KILL:
        await kill_command(update, context)
        return
    if data == CB_ACTION_RESET:
        await reset_command(update, context)
        return

    if data == CB_MENU_MAIN:
        await _edit_or_reply(update, _t(session, "تم فتح القائمة الرئيسية.", "Main menu opened."))
        await _reply(update, "👇", reply_markup=_main_reply_keyboard(session))
        return
    if data == CB_MENU_PROFILE:
        is_admin = _is_admin(update)
        if not is_admin:
            await _edit_or_reply(
                update,
                _t(
                    session,
                    (
                        f"الملف الشخصي (قراءة فقط)\n\n{_profile_summary(session)}\n\n"
                        "كل الخيارات قابلة للضغط.\n"
                        "البريميوم يعرض التفاصيل، وباقي خيارات الإدارة مقيدة."
                    ),
                    (
                        f"Profile (read-only)\n\n{_profile_summary(session)}\n\n"
                        "All options are clickable.\n"
                        "Premium shows details, while admin settings remain restricted."
                    ),
                ),
                reply_markup=_profile_menu_keyboard(session, is_admin=False),
            )
            return
        await _edit_or_reply(
            update,
            _t(
                session,
                f"إعدادات الملف الشخصي\n\n{_profile_summary(session)}\n\nاختر القسم الذي تريد تعديله.",
                f"Profile Settings\n\n{_profile_summary(session)}\n\nChoose the section you want to edit.",
            ),
            reply_markup=_profile_menu_keyboard(session, is_admin=True),
        )
        return
    if data == CB_MENU_LEVEL:
        if not _is_admin(update):
            await _edit_or_reply(
                update,
                _admin_only_message(session),
                reply_markup=_profile_menu_keyboard(session, is_admin=False),
            )
            return
        await _edit_or_reply(update, _t(session, "اختر مستواك:", "Choose your level:"), reply_markup=_level_selection_keyboard(session))
        return
    if data == CB_MENU_ACCESS:
        if not _is_admin(update):
            await _edit_or_reply(
                update,
                _premium_info_message(session),
                reply_markup=_profile_menu_keyboard(session, is_admin=False),
            )
            return
        await _edit_or_reply(update, _t(session, "اختر نوع الوصول:", "Choose access type:"), reply_markup=_access_selection_keyboard(session))
        return
    if data == CB_MENU_FOCUS:
        if not _is_admin(update):
            await _edit_or_reply(
                update,
                _admin_only_message(session),
                reply_markup=_profile_menu_keyboard(session, is_admin=False),
            )
            return
        await _edit_or_reply(update, _t(session, "اختر تركيزك:", "Choose your focus:"), reply_markup=_focus_selection_keyboard(session))
        return
    if data == CB_MENU_LANGUAGE:
        await _edit_or_reply(update, _t(session, "اختر اللغة:", "Choose language:"), reply_markup=_language_selection_keyboard(session))
        return

    if data.startswith(CB_SET_LEVEL_PREFIX):
        if not _is_admin(update):
            await _edit_or_reply(
                update,
                _admin_only_message(session),
                reply_markup=_profile_menu_keyboard(session, is_admin=False),
            )
            return
        level = data.replace(CB_SET_LEVEL_PREFIX, "", 1)
        result = _set_level_value(session, level)
        await _edit_or_reply(
            update,
            f"{result}\n\n{_profile_summary(session)}",
            reply_markup=_profile_menu_keyboard(session, is_admin=True),
        )
        return
    if data.startswith(CB_SET_ACCESS_PREFIX):
        if not _is_admin(update):
            await _edit_or_reply(
                update,
                _admin_only_message(session),
                reply_markup=_profile_menu_keyboard(session, is_admin=False),
            )
            return
        access = data.replace(CB_SET_ACCESS_PREFIX, "", 1)
        result = _set_access_value(session, access)
        await _edit_or_reply(
            update,
            f"{result}\n\n{_profile_summary(session)}",
            reply_markup=_profile_menu_keyboard(session, is_admin=True),
        )
        return
    if data.startswith(CB_SET_FOCUS_PREFIX):
        if not _is_admin(update):
            await _edit_or_reply(
                update,
                _admin_only_message(session),
                reply_markup=_profile_menu_keyboard(session, is_admin=False),
            )
            return
        focus = data.replace(CB_SET_FOCUS_PREFIX, "", 1)
        result = _set_focus_value(session, focus)
        await _edit_or_reply(
            update,
            f"{result}\n\n{_profile_summary(session)}",
            reply_markup=_profile_menu_keyboard(session, is_admin=True),
        )
        return
    if data.startswith(CB_SET_LANGUAGE_PREFIX):
        selected = data.replace(CB_SET_LANGUAGE_PREFIX, "", 1).strip().lower()
        if selected not in SUPPORTED_LANGUAGES:
            await _edit_or_reply(update, _t(session, f"{EMOJI_FALSE} لغة غير صالحة.", f"{EMOJI_FALSE} Invalid language."))
            return
        session.language = selected
        await _edit_or_reply(
            update,
            _t(
                session,
                f"{EMOJI_TRUE} تم تحديث اللغة إلى: {_language_label(selected, session)}.",
                f"{EMOJI_TRUE} Language updated to: {_language_label(selected, session)}.",
            ),
            reply_markup=_profile_menu_keyboard(session, is_admin=_is_admin(update)),
        )
        await _reply(update, "👇", reply_markup=_main_reply_keyboard(session))
        return

    if data.startswith(CB_LESSON_COMPLETE_PREFIX):
        lesson_id = data.replace(CB_LESSON_COMPLETE_PREFIX, "", 1).strip()
        await _complete_pending_lesson(update, context, session, lesson_id)
        return

    if data.startswith(CB_QUIZ_PREFIX):
        option = data.replace(CB_QUIZ_PREFIX, "", 1).strip().upper()
        await _evaluate_quiz_option(update, session, option)
        return

    if data.startswith(CB_SIM_DIR_PREFIX):
        direction = data.replace(CB_SIM_DIR_PREFIX, "", 1).strip().lower()
        await _set_simulation_direction(update, session, direction)
        return


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or not update.message.text:
        return

    session = _get_session(update)
    if session is None:
        return

    text = update.message.text.strip()
    lowered = text.lower()

    if is_unrealistic_request(text):
        await _reply(update, f"{SAFETY_REFUSAL}\n\n{RISK_REMINDER}")
        return

    if text in _button_variants("menu"):
        await menu_command(update, context)
        return
    if lowered == "buttons":
        await buttons_command(update, context)
        return
    if text in _button_variants("kill"):
        await kill_command(update, context)
        return
    if text in _button_variants("help"):
        await help_command(update, context)
        return
    if text in _button_variants("status"):
        await status_command(update, context)
        return
    if text in _button_variants("profile"):
        await profile_command(update, context)
        return
    if text in _button_variants("reset"):
        await reset_command(update, context)
        return
    if text in _button_variants("lesson"):
        await lesson_command(update, context)
        return
    if text in _button_variants("simulation"):
        await simulate_command(update, context)
        return
    if text in _button_variants("daily"):
        await daily_challenge_command(update, context)
        return
    if text in _button_variants("language") or lowered == "language":
        await language_command(update, context)
        return

    if text in _button_variants("askme"):
        await askme_command(update, context)
        return

    if lowered in {"complete", "اكمال", "إكمال", "اكمل", "أكمل", "إكمل"} and session.pending_lesson is not None:
        await _complete_pending_lesson(update, context, session, session.pending_lesson.lesson_id)
        return

    if session.quiz_state is not None:
        await _handle_quiz_answer(update, session, text)
        return

    if session.simulation_state is not None:
        await _handle_simulation_answer(update, session, text)
        return

    if session.daily_challenge_state is not None:
        await _handle_daily_challenge_answer(update, session, text)
        return

    # Handle AI assistant mode (Ask Me)
    if session.assistant_mode:
        ai_client = _get_ai_client()
        if ai_client is not None:
            await _reply(update, _t(session, "⌛ جاري التفكير...", "⌛ Thinking..."))
            answer = await ai_client.answer_question(text, session.language)
            if answer:
                await _reply(
                    update,
                    f"💬 {answer}",
                    reply_markup=_askme_keyboard(session),
                )
            else:
                await _reply(
                    update,
                    _t(
                        session,
                        "عذرًا، لم أستطع الإجابة على سؤالك. حاول مرة أخرى.",
                        "Sorry, I couldn't answer your question. Try again.",
                    ),
                    reply_markup=_askme_keyboard(session),
                )
        else:
            await _reply(
                update,
                _t(
                    session,
                    "عذرًا، خدمة الذكاء الاصطناعي غير متاحة حاليًا.",
                    "Sorry, AI service is currently unavailable.",
                ),
            )
        # Keep assistant_mode True to continue the conversation
        return

    frustration_words = ["frustrated", "lost money", "blew", "angry", "revenge trade", "متضايق", "خسرت", "معصب"]
    if any(word in lowered for word in frustration_words):
        response = (
            "الخسائر صعبة نفسيًا وهذا طبيعي. توقف قليلًا، خفف الحجم، "
            "وراجع آخر صفقاتك قبل أي دخول جديد.\n\n"
            "قائمة المراجعة:\n"
            "- هل التزمت بقواعد دخولك؟\n"
            "- هل كانت المخاطرة <= 2%؟\n"
            "- هل كان وقف الخسارة منطقيًا؟\n"
            "- هل العاطفة غلبت الخطة؟\n\n"
            f"{RISK_REMINDER}"
        )
        await _reply(update, response)
        return

    if "lesson" in lowered or "teach" in lowered or "درس" in lowered:
        await lesson_command(update, context)
        return
    if "simulate" in lowered or "practice" in lowered or "محاكاة" in lowered:
        await simulate_command(update, context)
        return
    if "challenge" in lowered or "تحدي" in lowered:
        await daily_challenge_command(update, context)
        return

    fallback = _t(
        session,
        (
            "استخدم الأزرار بالأسفل للتنقل بسهولة.\n\n"
            f"{_commands_text(session)}\n\n"
            "إذا كنت جديدًا، ابدأ بزر الدرس."
        ),
        (
            "Use the buttons below for easier navigation.\n\n"
            f"{_commands_text(session)}\n\n"
            "If you're new, start with Lesson."
        ),
    )
    await _reply(update, f"{fallback}\n\n{RISK_REMINDER}", reply_markup=_main_reply_keyboard(session))


def _render_lesson(session: UserSession, lesson) -> str:
    bullet_text = "\n".join(f"- {point}" for point in lesson.bullet_points)
    quiz_plan = _t(
        session,
        (
            f"اضغط ✅ إكمال لبدء {AI_QUIZ_PER_LESSON} سؤال اختبار."
            if lesson.lesson_id.startswith("AI-")
            else "اضغط ✅ إكمال لبدء الاختبار."
        ),
        (
            f"Tap ✅ Complete to start {AI_QUIZ_PER_LESSON} quiz questions."
            if lesson.lesson_id.startswith("AI-")
            else "Tap ✅ Complete to start the quiz."
        ),
    )
    return (
        f"{_level_label(lesson.level, session)}\n"
        f"{_t(session, 'الدرس', 'Lesson')}: {lesson.title}\n"
        f"{_t(session, 'الهدف', 'Objective')}: {lesson.objective}\n\n"
        f"{_t(session, 'النقاط الرئيسية', 'Key Points')}:\n{bullet_text}\n\n"
        f"{_t(session, 'مثال عملي', 'Practical Example')}:\n{lesson.example}\n\n"
        f"{quiz_plan}"
    )


async def _send_quiz_question(update: Update, session: UserSession) -> None:
    if session.quiz_state is None:
        return
    quiz_state = session.quiz_state
    question = quiz_state.questions[quiz_state.current_index]
    options = "\n".join(
        f"{key}) {value}" for key, value in sorted(question.options.items(), key=lambda item: item[0])
    )
    text = _t(
        session,
        (
            f"اختبار {quiz_state.current_index + 1}/{len(quiz_state.questions)}\n"
            f"{question.prompt}\n"
            f"{options}\n\n"
            "استخدم الأزرار أو اكتب A أو B أو C أو D."
        ),
        (
            f"Quiz {quiz_state.current_index + 1}/{len(quiz_state.questions)}\n"
            f"{question.prompt}\n"
            f"{options}\n\n"
            "Use buttons or type A, B, C, or D."
        ),
    )
    await _reply(update, text, reply_markup=_quiz_keyboard(session))


def _extract_option(text: str) -> Optional[str]:
    normalized = text.strip().upper()
    if normalized in {"A", "B", "C", "D"}:
        return normalized
    match = re.search(r"\b([ABCD])\b", normalized)
    if match:
        return match.group(1)
    return None


async def _handle_quiz_answer(update: Update, session: UserSession, text: str) -> None:
    option = _extract_option(text)
    if option is None:
        await _reply(update, f"{EMOJI_FALSE} اختر إجابة واحدة: A أو B أو C أو D.")
        return
    await _evaluate_quiz_option(update, session, option)


async def _evaluate_quiz_option(update: Update, session: UserSession, option: str) -> None:
    if session.quiz_state is None:
        await _reply(update, f"{EMOJI_FALSE} لا يوجد اختبار نشط. ابدأ درسًا أولًا.")
        return
    if option not in {"A", "B", "C", "D"}:
        await _reply(update, f"{EMOJI_FALSE} اختر إجابة واحدة: A أو B أو C أو D.")
        return

    quiz_state = session.quiz_state
    question = quiz_state.questions[quiz_state.current_index]

    if option == question.answer.upper():
        quiz_state.score += 1
        await _reply(update, f"{EMOJI_TRUE} إجابة صحيحة. ركّز على جودة العملية أكثر من التوقع.")
    else:
        await _reply(update, f"{EMOJI_FALSE} إجابة غير صحيحة. {question.explanation}")

    quiz_state.current_index += 1
    if quiz_state.current_index < len(quiz_state.questions):
        await _send_quiz_question(update, session)
        return

    total = len(quiz_state.questions)
    score = quiz_state.score
    lesson_id = quiz_state.lesson_id
    completed_level = quiz_state.level or session.level
    previous_level = session.level
    if quiz_state.is_dynamic:
        session.ai_lessons_completed += 1
        _sync_ai_curriculum_level(session)
    else:
        session.completed_lessons.add(lesson_id)
    session.quiz_state = None

    if quiz_state.is_dynamic:
        unlocked_text = ""
        if session.level != previous_level:
            unlocked_text = f"{EMOJI_TRUE} تم فتح مستوى جديد: {_level_label(session.level, session)}."
        finished_curriculum = session.ai_lessons_completed >= AI_TOTAL_LESSONS
        next_step = (
            f"{EMOJI_TRUE} تم إكمال منهج الذكاء الاصطناعي."
            if finished_curriculum
            else "اضغط زر الدرس مرة أخرى للدرس التالي."
        )
        lines = [
            f"اكتمل الاختبار: {score}/{total}.",
            f"تم إكمال درس الذكاء الاصطناعي في {_level_label(completed_level, session)}.",
            f"تقدم منهج الذكاء الاصطناعي: {session.ai_lessons_completed}/{AI_TOTAL_LESSONS}.",
            unlocked_text,
            next_step,
            _completion_thanks_text(session) if finished_curriculum else "",
            RISK_REMINDER,
        ]
        await _reply(update, "\n\n".join([line for line in lines if line]), reply_markup=_main_reply_keyboard(session))
        return

    available_lessons = lessons_for_user(completed_level, session.access)
    completed = len([lesson for lesson in available_lessons if lesson.lesson_id in session.completed_lessons])

    lines = [
        f"اكتمل الاختبار: {score}/{total}.",
        f"التقدم في {_level_label(completed_level, session)}: {completed}/{len(available_lessons)} دروس مكتملة.",
    ]
    if completed == len(available_lessons):
        nxt = next_level(session.level)
        if session.level == "advanced" and session.access == "free":
            lines.append(
                "تم إكمال المحتوى التعريفي المتقدم. البريميوم يفتح الأطر المتقدمة والاحترافية الكاملة."
            )
        elif nxt is None:
            lines.append("أنهيت جميع المستويات المتاحة لملفك الحالي.")
            lines.append(_completion_thanks_text(session))
        elif nxt == "professional" and session.access == "free":
            lines.append("المحتوى الاحترافي مخصص للبريميوم فقط. واصل التدريب بالمحاكاة واليومية.")
        else:
            session.level = nxt
            lines.append(f"{EMOJI_TRUE} تم فتح مستوى جديد: {_level_label(nxt, session)}.")

    lines.append(RISK_REMINDER)
    await _reply(update, "\n\n".join(lines), reply_markup=_main_reply_keyboard(session))

def _extract_number(text: str) -> Optional[float]:
    cleaned = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    return float(match.group(0))


async def _set_simulation_direction(update: Update, session: UserSession, direction: str) -> None:
    if session.simulation_state is None:
        await _reply(update, f"{EMOJI_FALSE} لا توجد محاكاة نشطة. ابدأ واحدة عبر زر المحاكاة.")
        return
    if session.simulation_state.stage != "direction":
        await _reply(update, "تم تحديد الاتجاه بالفعل. تابع السؤال التالي.")
        return
    if direction not in {"long", "short"}:
        await _reply(update, f"{EMOJI_FALSE} اختر لونغ أو شورت.")
        return

    state = session.simulation_state
    state.direction = direction
    state.stage = "stop_loss"
    direction_label = "لونغ" if direction == "long" else "شورت"
    await _reply(
        update,
        f"{EMOJI_TRUE} تم تحديد الاتجاه: {direction_label}.\nالسؤال 2/4: حدد سعر وقف الخسارة للدخول {state.entry:.2f} DZD.",
        reply_markup=_main_reply_keyboard(session),
    )


async def _handle_simulation_answer(update: Update, session: UserSession, text: str) -> None:
    if session.simulation_state is None:
        return
    state = session.simulation_state
    lowered = text.lower().strip()

    if state.stage == "direction":
        if "long" in lowered:
            await _set_simulation_direction(update, session, "long")
            return
        if "short" in lowered:
            await _set_simulation_direction(update, session, "short")
            return
        await _reply(update, f"{EMOJI_FALSE} اختر الاتجاه: لونغ أو شورت.")
        return

    if state.stage == "stop_loss":
        value = _extract_number(text)
        if value is None:
            await _reply(update, f"{EMOJI_FALSE} أرسل سعر وقف خسارة رقمي صحيح.")
            return
        if state.direction == "long" and value >= state.entry:
            await _reply(update, f"{EMOJI_FALSE} في صفقة لونغ يجب أن يكون وقف الخسارة أسفل الدخول.")
            return
        if state.direction == "short" and value <= state.entry:
            await _reply(update, f"{EMOJI_FALSE} في صفقة شورت يجب أن يكون وقف الخسارة أعلى الدخول.")
            return
        state.stop_loss = value
        state.stage = "take_profit"
        await _reply(update, "السؤال 3/4: حدد سعر جني الربح.")
        return

    if state.stage == "take_profit":
        value = _extract_number(text)
        if value is None:
            await _reply(update, f"{EMOJI_FALSE} أرسل سعر جني ربح رقمي صحيح.")
            return
        if state.direction == "long" and value <= state.entry:
            await _reply(update, f"{EMOJI_FALSE} في صفقة لونغ يجب أن يكون جني الربح أعلى الدخول.")
            return
        if state.direction == "short" and value >= state.entry:
            await _reply(update, f"{EMOJI_FALSE} في صفقة شورت يجب أن يكون جني الربح أسفل الدخول.")
            return
        state.take_profit = value
        state.stage = "risk_percent"
        await _reply(update, "السؤال 4/4: كم نسبة المخاطرة من الحساب في هذه الصفقة؟")
        return

    if state.stage == "risk_percent":
        risk_percent = _extract_number(text)
        if risk_percent is None or risk_percent <= 0 or risk_percent > 100:
            await _reply(
                update,
                f"{EMOJI_FALSE} قدم نسبة مخاطرة واقعية (مثال: 1 أو 1.5).",
            )
            return
        feedback = _build_simulation_feedback(state, risk_percent)
        session.ai_simulations_completed += 1
        session.simulation_state = None
        await _reply(update, feedback, reply_markup=_main_reply_keyboard(session))


def _build_simulation_feedback(state: SimulationState, risk_percent: float) -> str:
    if state.stop_loss is None or state.take_profit is None or state.direction is None:
        return f"{EMOJI_FALSE} خطأ في المحاكاة. أعد البدء عبر زر المحاكاة."

    risk_distance = abs(state.entry - state.stop_loss)
    reward_distance = abs(state.take_profit - state.entry)
    rr = reward_distance / risk_distance if risk_distance else 0.0

    direction_label = "لونغ" if state.direction == "long" else "شورت"
    lines = [
        "تقييم المحاكاة",
        f"- الاتجاه: {direction_label}",
        f"- الدخول: {state.entry:.2f} DZD",
        f"- وقف الخسارة: {state.stop_loss:.2f} DZD",
        f"- جني الربح: {state.take_profit:.2f} DZD",
        f"- العائد إلى المخاطرة: {rr:.2f}R",
        f"- المخاطرة لكل صفقة: {risk_percent:.2f}%",
    ]
    if rr < 1.5:
        lines.append(f"- جودة R:R: {EMOJI_FALSE} ضعيفة لمعظم الأنظمة. حسّن العائد أو قلّل الإبطال.")
    elif rr < 2.0:
        lines.append("- جودة R:R: ✅ مقبولة. تأكد أنها مناسبة لنسبة نجاحك التاريخية.")
    else:
        lines.append("- جودة R:R: ✅ قوية. حافظ على جودة التنفيذ والانضباط.")

    if risk_percent > 2.0:
        lines.append(f"- حجم المخاطرة: {EMOJI_FALSE} مرتفع. الأفضل إبقاؤها بين 0.5% و2% للصفقة.")
    else:
        lines.append("- حجم المخاطرة: ✅ ضمن نطاق تعليمي محافظ.")

    if state.direction == "long" and state.stop_loss > state.support:
        lines.append("- موضع الوقف: ❌ أعلى دعم مهم. قد يكون ضيقًا قرب السيولة.")
    if state.direction == "short" and state.stop_loss < state.resistance:
        lines.append("- موضع الوقف: ❌ أسفل مقاومة مهمة. فكّر في إبطال أبعد من الهيكل.")

    lines.append("مراجعة العملية: هل تضمنت الخطة سياقًا وإشارة دخول وإبطالًا وحد مخاطرة؟")
    lines.append(RISK_REMINDER)
    return "\n".join(lines)


async def _handle_daily_challenge_answer(update: Update, session: UserSession, text: str) -> None:
    if session.daily_challenge_state is None:
        return
    challenge = session.daily_challenge_state

    word_count = len(text.split())
    if word_count < 8:
        await _reply(
            update,
            f"{EMOJI_FALSE} أضف تحليلًا أكثر: التحيز، إشارة التأكيد، الإبطال، وحد المخاطرة.",
        )
        return

    lowered = text.lower()
    hit_count = sum(1 for keyword in challenge.expected_keywords if keyword in lowered)
    if hit_count >= 3:
        feedback = (
            f"{EMOJI_TRUE} جودة التحليل جيدة. إجابتك تضمنت الهيكل والتفكير بالمخاطر، "
            "وهذا الاتجاه الاحترافي الصحيح."
        )
    elif hit_count == 2:
        feedback = "✅ هيكل جيد. حسّنه بتحديد أوضح لنقطة الإبطال ومعايير الدخول."
    else:
        feedback = (
            f"{EMOJI_FALSE} إجابتك عامة جدًا. اجعلها أكثر تنظيمًا بسياق الاتجاه "
            "والمستوى المهم والإبطال ومخاطرة الصفقة."
        )

    session.ai_challenges_completed += 1
    session.daily_challenge_state = None
    response = (
        f"{feedback}\n\n"
        "قائمة التحدي القادم:\n"
        "- سياق السوق\n"
        "- إشارة الدخول\n"
        "- الإبطال (منطق الوقف)\n"
        "- المخاطرة لكل صفقة\n"
        "- خطة المراجعة بعد النتيجة\n\n"
        f"{RISK_REMINDER}"
    )
    await _reply(update, response, reply_markup=_main_reply_keyboard(session))
