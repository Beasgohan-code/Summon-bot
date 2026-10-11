"""Aiogram 3 runtime and a small legacy-shaped handler bridge.

The bot's feature modules historically receive ``(update, context)``.  This
module keeps that stable application boundary while the transport, dispatcher,
filters, webhook updates, keyboards, and Telegram API client are all provided
by aiogram 3.  No other Telegram bot framework is imported or used at runtime.
"""
from __future__ import annotations

import asyncio
import io
import re
from collections import defaultdict
from typing import Any, Awaitable, Callable, Iterable

from aiogram import Bot as AiogramBot
from aiogram import Dispatcher, F, Router
from aiogram.enums import ChatAction, ChatType, ParseMode
from aiogram.exceptions import TelegramNetworkError as NetworkError
from aiogram.filters import BaseFilter, Command as AiogramCommand
from aiogram.types import (
    BotCommand as AiogramBotCommand,
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton as AiogramInlineKeyboardButton,
    InlineKeyboardMarkup as AiogramInlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent as AiogramInputTextMessageContent,
    Message,
    Update as AiogramUpdate,
)


Bot = AiogramBot


# The previous handler layer accepted the most common keyboard/command fields
# positionally. Aiogram 3's Pydantic models are keyword-only, so keep the
# existing feature modules source-compatible while returning native objects.
def BotCommand(command: str, description: str, **kwargs: Any) -> AiogramBotCommand:
    return AiogramBotCommand(command=command, description=description, **kwargs)


def InlineKeyboardButton(text: str, **kwargs: Any) -> AiogramInlineKeyboardButton:
    return AiogramInlineKeyboardButton(text=text, **kwargs)


def InlineKeyboardMarkup(inline_keyboard: list[list[AiogramInlineKeyboardButton]], **kwargs: Any) -> AiogramInlineKeyboardMarkup:
    return AiogramInlineKeyboardMarkup(inline_keyboard=inline_keyboard, **kwargs)


# ---------------------------------------------------------------------------
# Update/message facades used by the existing feature functions
# ---------------------------------------------------------------------------

def _normalise_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    values = dict(kwargs)
    # Legacy-only compatibility fields are not Telegram Bot API parameters in
    # aiogram. Reply methods set the reply target explicitly below.
    values.pop("quote", None)
    values.pop("user_id", None)
    return values


def _media(value: Any) -> Any:
    """Convert legacy file objects to aiogram input files."""
    if isinstance(value, io.BytesIO):
        position = value.tell()
        value.seek(0)
        data = value.read()
        value.seek(position)
        return BufferedInputFile(data, filename=getattr(value, "name", None) or "upload.bin")
    return value


class UserView:
    """Expose aiogram user fields plus the legacy profile-photo convenience API."""

    def __init__(self, user: Any, bot: "BotProxy | None" = None):
        self._user = user
        self._bot = bot

    def __getattr__(self, name: str) -> Any:
        return getattr(self._user, name)

    async def get_profile_photos(self, limit: int = 1, **kwargs: Any):
        if self._bot is None:
            raise RuntimeError("A bot is required to load Telegram profile photos")
        return await self._bot.get_user_profile_photos(
            user_id=self._user.id,
            limit=limit,
            **kwargs,
        )


class MessageView:
    def __init__(self, message: Message):
        self._message = message

    def __getattr__(self, name: str) -> Any:
        return getattr(self._message, name)

    async def reply_text(self, text: str, **kwargs: Any):
        values = _normalise_kwargs(kwargs)
        values.setdefault("reply_to_message_id", self._message.message_id)
        return await self._message.answer(text=text, **values)

    async def reply_photo(self, photo: Any, **kwargs: Any):
        values = _normalise_kwargs(kwargs)
        values.setdefault("reply_to_message_id", self._message.message_id)
        return await self._message.answer_photo(photo=_media(photo), **values)

    async def reply_video(self, video: Any, **kwargs: Any):
        values = _normalise_kwargs(kwargs)
        values.setdefault("reply_to_message_id", self._message.message_id)
        return await self._message.answer_video(video=_media(video), **values)

    async def reply_animation(self, animation: Any, **kwargs: Any):
        values = _normalise_kwargs(kwargs)
        values.setdefault("reply_to_message_id", self._message.message_id)
        return await self._message.answer_animation(animation=_media(animation), **values)

    async def reply_document(self, document: Any, **kwargs: Any):
        values = _normalise_kwargs(kwargs)
        values.setdefault("reply_to_message_id", self._message.message_id)
        return await self._message.answer_document(document=_media(document), **values)

    async def edit_text(self, text: str | None = None, **kwargs: Any):
        values = _normalise_kwargs(kwargs)
        if text is not None:
            values["text"] = text
        return await self._message.edit_text(**values)

    async def edit_caption(self, caption: str | None = None, **kwargs: Any):
        values = _normalise_kwargs(kwargs)
        if caption is not None:
            values["caption"] = caption
        return await self._message.edit_caption(**values)

    async def delete(self, **kwargs: Any):
        return await self._message.delete(**kwargs)


class CallbackQueryView:
    def __init__(self, query: CallbackQuery):
        self._query = query

    @property
    def message(self) -> MessageView | None:
        return MessageView(self._query.message) if self._query.message else None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._query, name)

    async def answer(self, *args: Any, **kwargs: Any):
        return await self._query.answer(*args, **kwargs)

    async def edit_message_text(self, text: str | None = None, **kwargs: Any):
        if self._query.message:
            return await MessageView(self._query.message).edit_text(text, **kwargs)
        return await self._query.edit_message_text(text=text, **_normalise_kwargs(kwargs))

    async def edit_message_caption(self, caption: str | None = None, **kwargs: Any):
        if self._query.message:
            return await MessageView(self._query.message).edit_caption(caption, **kwargs)
        return await self._query.edit_message_caption(caption=caption, **_normalise_kwargs(kwargs))

    async def edit_message_reply_markup(self, **kwargs: Any):
        if self._query.message:
            return await self._query.message.edit_reply_markup(**_normalise_kwargs(kwargs))
        return await self._query.edit_message_reply_markup(**_normalise_kwargs(kwargs))


class InlineQueryView:
    def __init__(self, query: InlineQuery):
        self._query = query

    def __getattr__(self, name: str) -> Any:
        return getattr(self._query, name)

    async def answer(self, *args: Any, **kwargs: Any):
        return await self._query.answer(*args, **kwargs)


class UpdateView:
    """Expose the legacy update properties used by the bot on aiogram events."""

    def __init__(self, event: Any, bot: "BotProxy | None" = None):
        self._event = event
        self._bot = bot

    @property
    def message(self) -> MessageView | None:
        message = self._message_object()
        return MessageView(message) if message else None

    @property
    def callback_query(self) -> CallbackQueryView | None:
        query = self._callback_object()
        return CallbackQueryView(query) if query else None

    @property
    def inline_query(self) -> InlineQueryView | None:
        query = self._inline_object()
        return InlineQueryView(query) if query else None

    @property
    def effective_message(self) -> MessageView | None:
        return self.message

    @property
    def effective_user(self):
        event = self._event
        if isinstance(event, (Message, CallbackQuery, InlineQuery)):
            return UserView(event.from_user, self._bot)
        if isinstance(event, AiogramUpdate):
            if event.message:
                return UserView(event.message.from_user, self._bot)
            if event.edited_message:
                return UserView(event.edited_message.from_user, self._bot)
            if event.callback_query:
                return UserView(event.callback_query.from_user, self._bot)
            if event.inline_query:
                return UserView(event.inline_query.from_user, self._bot)
        return None

    @property
    def effective_chat(self):
        event = self._event
        if isinstance(event, Message):
            return event.chat
        if isinstance(event, CallbackQuery):
            return event.message.chat if event.message else None
        if isinstance(event, AiogramUpdate):
            if event.message:
                return event.message.chat
            if event.edited_message:
                return event.edited_message.chat
            if event.callback_query and event.callback_query.message:
                return event.callback_query.message.chat
        return None

    def _message_object(self) -> Message | None:
        event = self._event
        if isinstance(event, Message):
            return event
        if isinstance(event, CallbackQuery):
            return event.message
        if isinstance(event, AiogramUpdate):
            return event.message or event.edited_message or (
                event.callback_query.message if event.callback_query else None
            )
        return None

    def _callback_object(self) -> CallbackQuery | None:
        event = self._event
        if isinstance(event, CallbackQuery):
            return event
        if isinstance(event, AiogramUpdate):
            return event.callback_query
        return None

    def _inline_object(self) -> InlineQuery | None:
        event = self._event
        if isinstance(event, InlineQuery):
            return event
        if isinstance(event, AiogramUpdate):
            return event.inline_query
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._event, name)


class Update:
    """Webhook deserialiser kept under the old symbol used by main.py."""

    @staticmethod
    def de_json(payload: dict[str, Any], bot: Any = None) -> AiogramUpdate:
        return AiogramUpdate.model_validate(payload)


class _DownloadedFile:
    def __init__(self, bot: AiogramBot, file: Any):
        self._bot = bot
        self._file = file

    async def download_as_bytearray(self) -> bytearray:
        buffer = io.BytesIO()
        await self._bot.download(self._file, destination=buffer)
        return bytearray(buffer.getvalue())


class BotProxy:
    """Delegate Telegram API calls to an aiogram Bot with small legacy aliases."""

    def __init__(self, bot: AiogramBot):
        self._bot = bot

    def __getattr__(self, name: str) -> Any:
        return getattr(self._bot, name)

    async def get_file(self, file_id: str, *args: Any, **kwargs: Any):
        file = await self._bot.get_file(file_id, *args, **kwargs)
        return _DownloadedFile(self._bot, file)

    async def send_photo(self, *args: Any, **kwargs: Any):
        if "photo" in kwargs:
            kwargs["photo"] = _media(kwargs["photo"])
        return await self._bot.send_photo(*args, **_normalise_kwargs(kwargs))

    async def send_video(self, *args: Any, **kwargs: Any):
        if "video" in kwargs:
            kwargs["video"] = _media(kwargs["video"])
        return await self._bot.send_video(*args, **_normalise_kwargs(kwargs))

    async def send_animation(self, *args: Any, **kwargs: Any):
        if "animation" in kwargs:
            kwargs["animation"] = _media(kwargs["animation"])
        return await self._bot.send_animation(*args, **_normalise_kwargs(kwargs))

    async def send_document(self, *args: Any, **kwargs: Any):
        if "document" in kwargs:
            kwargs["document"] = _media(kwargs["document"])
        return await self._bot.send_document(*args, **_normalise_kwargs(kwargs))

    async def send_message(self, *args: Any, **kwargs: Any):
        return await self._bot.send_message(*args, **_normalise_kwargs(kwargs))


# ---------------------------------------------------------------------------
# Legacy-shaped contexts and filters backed by aiogram
# ---------------------------------------------------------------------------
_user_data: dict[int, dict[str, Any]] = defaultdict(dict)
_chat_data: dict[int, dict[str, Any]] = defaultdict(dict)


class AiogramContext:
    def __init__(self, application: "Application", event: Any, *, args: list[str] | None = None, error: Exception | None = None):
        self.application = application
        self.bot = application.bot
        self.update = UpdateView(event, application.bot)
        self.args = list(args or [])
        self.error = error
        self.user_data = _user_data[int(self.update.effective_user.id)] if self.update.effective_user else {}
        self.chat_data = _chat_data[int(self.update.effective_chat.id)] if self.update.effective_chat else {}
        self.bot_data = application.bot_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class ContextTypes:
    DEFAULT_TYPE = AiogramContext


class _DocumentFilters:
    ALL = F.document


class _ChatFilters:
    GROUPS = F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
    PRIVATE = F.chat.type == ChatType.PRIVATE


class _Filters:
    TEXT = F.text
    PHOTO = F.photo
    VIDEO = F.video
    ANIMATION = F.animation
    COMMAND = F.text.startswith("/")
    Document = _DocumentFilters
    ChatType = _ChatFilters


filters = _Filters()


def _command_args(event: Any) -> list[str]:
    text = getattr(event, "text", None) or getattr(event, "caption", None) or ""
    return text.split()[1:]


async def _invoke(application: "Application", callback: Callable[..., Awaitable[Any]], event: Any, *, error: Exception | None = None) -> Any:
    view = UpdateView(event, application.bot)
    context = AiogramContext(application, event, args=_command_args(event), error=error)
    return await callback(view, context)


class _RegexCallbackFilter(BaseFilter):
    def __init__(self, pattern: str | re.Pattern[str]):
        self.pattern = re.compile(pattern) if isinstance(pattern, str) else pattern

    async def __call__(self, callback: CallbackQuery) -> bool:
        return bool(self.pattern.search(callback.data or ""))


class _Handler:
    def register(self, router: Router, application: "Application") -> None:
        raise NotImplementedError


class CommandHandler(_Handler):
    def __init__(self, commands: str | Iterable[str], callback: Callable[..., Awaitable[Any]], filters: Any = None, **_kwargs: Any):
        self.commands = [commands] if isinstance(commands, str) else list(commands)
        self.callback = callback
        self.extra_filter = filters

    def register(self, router: Router, application: "Application") -> None:
        command_filter = AiogramCommand(commands=self.commands, ignore_mention=False)
        extra = [self.extra_filter] if self.extra_filter is not None else []

        async def handler(message: Message):
            return await _invoke(application, self.callback, message)

        router.message.register(handler, command_filter, *extra)


class CallbackQueryHandler(_Handler):
    def __init__(self, callback: Callable[..., Awaitable[Any]], pattern: str | re.Pattern[str] | None = None, **_kwargs: Any):
        self.callback = callback
        self.pattern = pattern

    def register(self, router: Router, application: "Application") -> None:
        callback_filter = [_RegexCallbackFilter(self.pattern)] if self.pattern else []

        async def handler(query: CallbackQuery):
            return await _invoke(application, self.callback, query)

        router.callback_query.register(handler, *callback_filter)


class MessageHandler(_Handler):
    def __init__(self, message_filter: Any, callback: Callable[..., Awaitable[Any]], **_kwargs: Any):
        self.message_filter = message_filter
        self.callback = callback

    def register(self, router: Router, application: "Application") -> None:
        async def handler(message: Message):
            return await _invoke(application, self.callback, message)

        filters_to_apply = [self.message_filter] if self.message_filter is not None else []
        router.message.register(handler, *filters_to_apply)


class InlineQueryHandler(_Handler):
    def __init__(self, callback: Callable[..., Awaitable[Any]], **_kwargs: Any):
        self.callback = callback

    def register(self, router: Router, application: "Application") -> None:
        async def handler(query: InlineQuery):
            return await _invoke(application, self.callback, query)

        router.inline_query.register(handler)


class _UpdateQueue:
    def __init__(self, application: "Application"):
        self.application = application

    def put_nowait(self, update: AiogramUpdate) -> None:
        loop = self.application.loop
        if loop is None:
            raise RuntimeError("Aiogram application loop is not initialized")
        loop.call_soon_threadsafe(self.application._schedule_update, update)


class _DispatcherFacade:
    """Expose a dispatcher-like surface across the compatibility groups."""

    def __init__(self, application: "Application"):
        self._application = application

    @property
    def sub_routers(self) -> list[Router]:
        return [
            router
            for dispatcher in self._application._group_dispatchers
            for router in dispatcher.sub_routers
        ]

    async def feed_update(self, _bot: Any, update: AiogramUpdate) -> Any:
        return await self._application._process_update(update)

    def resolve_used_update_types(self) -> list[str]:
        update_types: set[str] = set()
        for dispatcher in self._application._group_dispatchers:
            update_types.update(dispatcher.resolve_used_update_types())
        return sorted(update_types)


class _ApplicationBuilder:
    def __init__(self):
        self._token = ""

    def token(self, token: str) -> "_ApplicationBuilder":
        self._token = token
        return self

    def build(self) -> "Application":
        return Application(self._token)


class Application:
    """Webhook-oriented aiogram dispatcher with the existing app boundary."""

    def __init__(self, token: str):
        self._raw_bot = AiogramBot(token)
        self.bot = BotProxy(self._raw_bot)
        self.dispatcher = _DispatcherFacade(self)
        self.bot_data: dict[str, Any] = {}
        self.update_queue = _UpdateQueue(self)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._handlers: list[tuple[int, int, _Handler]] = []
        self._error_callbacks: list[Callable[..., Awaitable[Any]]] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._group_dispatchers: list[Dispatcher] = []
        self._built = False
        self._sequence = 0

    @classmethod
    def builder(cls) -> _ApplicationBuilder:
        return _ApplicationBuilder()

    def add_handler(self, handler: _Handler, group: int = 0) -> None:
        self._sequence += 1
        self._handlers.append((int(group), self._sequence, handler))

    def add_error_handler(self, callback: Callable[..., Awaitable[Any]], **_kwargs: Any) -> None:
        self._error_callbacks.append(callback)

    def create_task(self, awaitable: Awaitable[Any], **_kwargs: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(awaitable)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def initialize(self) -> None:
        self.loop = asyncio.get_running_loop()
        if self._built:
            return

        # The previous dispatcher evaluated one matching handler per group and
        # then continued with later groups. A single aiogram router stops after
        # its first matching handler, so each compatibility group gets its own
        # dispatcher and the update is fed through them in group order below.
        grouped: dict[int, Router] = {}
        for group, _sequence, handler in sorted(self._handlers, key=lambda item: (item[0], item[1])):
            router = grouped.setdefault(group, Router(name=f"summon_group_{group}"))
            handler.register(router, self)

        for group in sorted(grouped):
            dispatcher = Dispatcher()
            dispatcher.include_router(grouped[group])
            for callback in self._error_callbacks:
                async def on_error(event: ErrorEvent, callback=callback):
                    await callback(
                        UpdateView(event.update, self.bot),
                        AiogramContext(self, event.update, error=event.exception),
                    )
                dispatcher.errors.register(on_error)
            self._group_dispatchers.append(dispatcher)
        self._built = True

    async def start(self) -> None:
        # Webhook updates are fed by HealthServer; aiogram's polling loop is
        # intentionally not used.
        return None

    async def stop(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        await self._raw_bot.session.close()

    async def _process_update(self, update: AiogramUpdate) -> None:
        for dispatcher in self._group_dispatchers:
            await dispatcher.feed_update(self._raw_bot, update)

    def _schedule_update(self, update: AiogramUpdate) -> None:
        self.create_task(self._process_update(update))


# The previous inline content constructor accepted the message text
# positionally; aiogram's Pydantic model is keyword-only.
def InputTextMessageContent(message_text: str, **kwargs: Any) -> AiogramInputTextMessageContent:
    return AiogramInputTextMessageContent(message_text=message_text, **kwargs)


__all__ = [
    "Application", "BotCommand", "Bot", "CallbackQueryHandler", "ChatAction", "ChatType",
    "CommandHandler", "ContextTypes", "filters", "InlineKeyboardButton",
    "InlineKeyboardMarkup", "InlineQueryHandler", "InlineQueryResultArticle",
    "InlineQueryResultPhoto", "InputTextMessageContent", "MessageHandler", "NetworkError",
    "ParseMode", "Update",
]
