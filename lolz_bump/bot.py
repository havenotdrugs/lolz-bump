from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from urllib.parse import urlsplit

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .db import Database
from .lolz_api import BumpResult
from .secrets import SecretStore
from .service import WindowSummary
from .settings import (
    DEFAULT_THREAD_DOMAIN,
    SUPPORTED_THREAD_DOMAINS,
    PostingTemplate,
    SchedulingSettings,
    validate_schedule_times,
)

PAGE_SIZE = 6
THREAD_PATH_PATTERN = re.compile(r"/threads/([1-9][0-9]*)(?:/.*)?$")


def parse_thread_reference(value: str) -> tuple[int, str]:
    reference = value.strip()
    if re.fullmatch(r"[1-9][0-9]*", reference):
        return int(reference), DEFAULT_THREAD_DOMAIN
    parsed = urlsplit(reference)
    domain = parsed.netloc.lower()
    if parsed.scheme != "https" or domain not in SUPPORTED_THREAD_DOMAINS:
        raise ValueError("unsupported thread reference")
    match = THREAD_PATH_PATTERN.fullmatch(parsed.path)
    if match is None:
        raise ValueError("unsupported thread reference")
    return int(match.group(1)), domain


def thread_url(thread_id: int, domain: str) -> str:
    return f"https://{domain}/threads/{thread_id}/"


class TelegramControl:
    def __init__(self, token: str, admin_ids: set[int], db: Database, secrets: SecretStore,
                 reload_scheduler: Callable[[], None], check_thread: Callable[[int], Awaitable[BumpResult]]) -> None:
        self._bot = Bot(token=token)
        self._admins = admin_ids
        self._db = db
        self._secrets = secrets
        self._reload_scheduler = reload_scheduler
        self._check_thread = check_thread
        self._pending: dict[int, tuple[str, tuple[str, ...]]] = {}
        self._router = Router()
        self._register_handlers()

    async def run(self) -> None:
        dispatcher = Dispatcher()
        dispatcher.include_router(self._router)
        await dispatcher.start_polling(self._bot, allowed_updates=dispatcher.resolve_used_update_types())

    async def close(self) -> None:
        await self._bot.session.close()

    def _register_handlers(self) -> None:
        @self._router.message(CommandStart())
        async def start(message: Message) -> None:
            if not self._admin_message(message):
                return
            if self._db.get_encrypted_lolz_token() is None:
                self._pending[message.from_user.id] = ("token", ())
                await self._show(
                    message.from_user.id,
                    message.chat.id,
                    "Отправьте LOLZ_API_TOKEN.",
                    self._back_keyboard("root"),
                    new_message=True,
                )
            else:
                await self._root(message.from_user.id, message.chat.id, new_message=True)

        @self._router.callback_query()
        async def callback(query: CallbackQuery) -> None:
            if not self._admin_callback(query):
                return
            await query.answer()
            await self._callback(query)

        @self._router.message(F.text)
        async def input_value(message: Message) -> None:
            if not self._admin_message(message):
                return
            pending = self._pending.pop(message.from_user.id, None)
            if pending is None:
                return
            with suppress(TelegramBadRequest):
                await message.delete()
            await self._input(message.from_user.id, message.chat.id, pending, message.text or "")

    def _admin_message(self, message: Message) -> bool:
        return message.chat.type == "private" and message.from_user is not None and message.from_user.id in self._admins

    def _admin_callback(self, query: CallbackQuery) -> bool:
        return query.message is not None and query.message.chat.type == "private" and query.from_user.id in self._admins

    async def _callback(self, query: CallbackQuery) -> None:
        data = (query.data or "").split(":")
        user_id, chat_id = query.from_user.id, query.message.chat.id
        if data == ["root"]:
            await self._root(user_id, chat_id)
        elif data == ["themes"]:
            await self._themes(user_id, chat_id)
        elif data[:2] == ["category", "important"] or data[:2] == ["category", "regular"]:
            await self._category(user_id, chat_id, data[1], int(data[2]))
        elif data[:2] == ["thread", "important"] or data[:2] == ["thread", "regular"]:
            await self._thread(user_id, chat_id, data[1], int(data[2]), int(data[3]))
        elif data[:1] == ["templates"]:
            await self._templates(user_id, chat_id, int(data[1]))
        elif data[:1] == ["template"]:
            await self._template(user_id, chat_id, int(data[1]))
        elif data == ["template_add"]:
            self._pending[user_id] = ("template_name", ())
            await self._show(user_id, chat_id, "Отправьте название шаблона.", self._back_keyboard("system"))
        elif data[:1] == ["template_schedule"]:
            self._pending[user_id] = ("template_schedule", (data[1],))
            await self._show(user_id, chat_id, "Отправьте HH:MM. Несколько значений — каждое с новой строки.", self._back_keyboard(f"template:{data[1]}"))
        elif data[:1] == ["template_rename"]:
            self._pending[user_id] = ("template_rename", (data[1],))
            await self._show(user_id, chat_id, "Отправьте новое название шаблона.", self._back_keyboard(f"template:{data[1]}"))
        elif data[:1] == ["template_delete"]:
            await self._delete_template(user_id, chat_id, int(data[1]))
        elif data[0] == "add":
            self._pending[user_id] = ("thread_id", (data[1], data[2]))
            await self._show(user_id, chat_id, "Отправьте ID или ссылку на тему.", self._back_keyboard(f"category:{data[1]}:{data[2]}"))
        elif data[0] == "schedule":
            self._pending[user_id] = ("schedule", tuple(data[1:]))
            await self._schedule_choice(user_id, chat_id)
        elif data == ["schedule_choice"]:
            await self._schedule_choice(user_id, chat_id)
        elif data == ["schedule_input"]:
            await self._schedule_input(user_id, chat_id)
        elif data[:1] == ["schedule_templates"]:
            await self._template_choices(user_id, chat_id, int(data[1]))
        elif data[:1] == ["use_template"]:
            await self._apply_template(user_id, chat_id, int(data[1]))
        elif data[0] == "delete":
            await self._delete_thread(user_id, chat_id, data[1], int(data[2]), int(data[3]))
        elif data[0] == "history":
            await self._history(user_id, chat_id, int(data[1]))
        elif data[0] == "attempt":
            await self._attempt(user_id, chat_id, int(data[1]), int(data[2]))
        elif data == ["system"]:
            await self._system(user_id, chat_id)
        elif data == ["token"]:
            self._pending[user_id] = ("token", ())
            await self._show(user_id, chat_id, "Отправьте LOLZ_API_TOKEN.", self._back_keyboard("system"))

    async def _input(self, user_id: int, chat_id: int, pending: tuple[str, tuple[str, ...]], value: str) -> None:
        action, context = pending
        try:
            if action == "token":
                if not value.strip():
                    raise ValueError("Токен не может быть пустым.")
                self._db.set_encrypted_lolz_token(self._secrets.encrypt(value.strip()))
                await self._root(user_id, chat_id)
                return
            if action == "thread_id":
                thread_id, thread_domain = parse_thread_reference(value)
                result = await self._check_thread(thread_id)
                if not result.success:
                    raise ValueError("Тема недоступна для токена.")
                self._pending[user_id] = ("new_schedule", (context[0], context[1], str(thread_id), thread_domain))
                await self._schedule_choice(user_id, chat_id)
                return
            if action == "template_name":
                settings = self._db.get_settings()
                name = self._validate_template_name(value, settings)
                self._pending[user_id] = ("template_schedule_new", (name,))
                await self._show(user_id, chat_id, "Отправьте HH:MM. Несколько значений — каждое с новой строки.", self._back_keyboard("system"))
                return
            if action == "template_rename":
                settings = self._db.get_settings()
                template_id = int(context[0])
                template = self._find_template(settings, template_id)
                if template is None:
                    raise ValueError("Шаблон не найден.")
                name = self._validate_template_name(value, settings, excluded_id=template_id)
                templates = [
                    PostingTemplate(id=item.id, name=name if item.id == template_id else item.name, schedule_times=item.schedule_times)
                    for item in settings.posting_templates
                ]
                self._save_settings(settings, posting_templates=templates, reload_scheduler=False)
                await self._template(user_id, chat_id, template_id)
                return
            times = validate_schedule_times([line.strip() for line in value.splitlines() if line.strip()], "schedule")
            if not times:
                raise ValueError("Укажите хотя бы одно время.")
            if action == "template_schedule_new":
                settings = self._db.get_settings()
                template = PostingTemplate(
                    id=self._next_template_id(settings),
                    name=context[0],
                    schedule_times=times,
                )
                self._save_settings(settings, posting_templates=[*settings.posting_templates, template], reload_scheduler=False)
                await self._templates(user_id, chat_id, 0)
                return
            if action == "template_schedule":
                settings = self._db.get_settings()
                template_id = int(context[0])
                template = self._find_template(settings, template_id)
                if template is None:
                    raise ValueError("Шаблон не найден.")
                templates = [
                    PostingTemplate(
                        id=item.id,
                        name=item.name,
                        schedule_times=times if item.id == template_id else item.schedule_times,
                    )
                    for item in settings.posting_templates
                ]
                self._save_settings(settings, posting_templates=templates, reload_scheduler=False)
                await self._template(user_id, chat_id, template_id)
                return
            settings = self._db.get_settings()
            priority, page = self._save_thread_schedule(settings, action, context, times)
            await self._category(user_id, chat_id, priority, page)
        except (ValueError, TypeError):
            back = "system" if action.startswith("template") else "root"
            await self._show(user_id, chat_id, "Не удалось сохранить значение. Повторите действие.", self._back_keyboard(back))

    async def _root(self, user_id: int, chat_id: int, new_message: bool = False) -> None:
        builder = InlineKeyboardBuilder()
        builder.button(text="Темы", callback_data="themes")
        builder.button(text="История", callback_data="history:0")
        builder.button(text="Системные настройки", callback_data="system")
        builder.adjust(1)
        await self._show(user_id, chat_id, "Главное меню", builder.as_markup(), new_message=new_message)

    async def _themes(self, user_id: int, chat_id: int) -> None:
        builder = InlineKeyboardBuilder()
        builder.button(text="Обычные", callback_data="category:regular:0")
        builder.button(text="Важные", callback_data="category:important:0")
        builder.button(text="Назад", callback_data="root")
        builder.adjust(1)
        await self._show(user_id, chat_id, "Темы", builder.as_markup())

    async def _category(self, user_id: int, chat_id: int, priority: str, page: int) -> None:
        items = self._db.get_settings().important_threads if priority == "important" else self._db.get_settings().regular_threads
        title = "Важные темы" if priority == "important" else "Обычные темы"
        builder = InlineKeyboardBuilder()
        builder.button(text="Добавить тему", callback_data=f"add:{priority}:{page}")
        for thread_id in items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
            builder.button(text=str(thread_id), callback_data=f"thread:{priority}:{thread_id}:{page}")
        self._pagination(builder, page, len(items), f"category:{priority}")
        builder.button(text="Назад", callback_data="themes")
        builder.adjust(1)
        await self._show(user_id, chat_id, title, builder.as_markup())

    async def _thread(self, user_id: int, chat_id: int, priority: str, thread_id: int, page: int) -> None:
        settings = self._db.get_settings()
        times = settings.schedule_times_for_thread(thread_id)
        builder = InlineKeyboardBuilder()
        builder.button(text="Задать график поднятия", callback_data=f"schedule:{priority}:{thread_id}:{page}")
        builder.button(text="Удалить тему", callback_data=f"delete:{priority}:{thread_id}:{page}")
        builder.button(text="Назад", callback_data=f"category:{priority}:{page}")
        builder.adjust(1)
        await self._show(user_id, chat_id, f"Тема {thread_url(thread_id, settings.thread_domains[thread_id])}\nГрафик:\n" + "\n".join(times), builder.as_markup())

    async def _schedule_choice(self, user_id: int, chat_id: int) -> None:
        pending = self._pending.get(user_id)
        if pending is None or pending[0] not in {"new_schedule", "schedule"}:
            await self._themes(user_id, chat_id)
            return
        action, context = pending
        builder = InlineKeyboardBuilder()
        builder.button(text="Ввести график", callback_data="schedule_input")
        builder.button(text="Выбрать шаблон", callback_data="schedule_templates:0")
        if action == "new_schedule":
            back = f"category:{context[0]}:{context[1]}"
        else:
            back = f"thread:{context[0]}:{context[1]}:{context[2]}"
        builder.button(text="Назад", callback_data=back)
        builder.adjust(1)
        await self._show(user_id, chat_id, "Выберите способ задания графика.", builder.as_markup())

    async def _schedule_input(self, user_id: int, chat_id: int) -> None:
        pending = self._pending.get(user_id)
        if pending is None:
            await self._themes(user_id, chat_id)
            return
        action, _ = pending
        if action not in {"new_schedule", "schedule"}:
            await self._themes(user_id, chat_id)
            return
        await self._show(user_id, chat_id, "Отправьте HH:MM. Несколько значений — каждое с новой строки.", self._back_keyboard("schedule_choice"))

    async def _template_choices(self, user_id: int, chat_id: int, page: int) -> None:
        pending = self._pending.get(user_id)
        if pending is None or pending[0] not in {"new_schedule", "schedule"}:
            await self._themes(user_id, chat_id)
            return
        templates = self._db.get_settings().posting_templates
        builder = InlineKeyboardBuilder()
        for template in templates[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
            builder.button(text=f"{template.name}: {', '.join(template.schedule_times)}", callback_data=f"use_template:{template.id}")
        if not templates:
            builder.button(text="Создать шаблон", callback_data="template_add")
        self._pagination(builder, page, len(templates), "schedule_templates")
        builder.button(text="Назад", callback_data="schedule_choice")
        builder.adjust(1)
        await self._show(user_id, chat_id, "Выберите шаблон постинга.", builder.as_markup())

    async def _delete_thread(self, user_id: int, chat_id: int, priority: str, thread_id: int, page: int) -> None:
        settings = self._db.get_settings()
        overrides = dict(settings.thread_schedule_overrides)
        overrides.pop(thread_id, None)
        domains = dict(settings.thread_domains)
        domains.pop(thread_id, None)
        changes = {"important_threads": [item for item in settings.important_threads if item != thread_id]} if priority == "important" else {"regular_threads": [item for item in settings.regular_threads if item != thread_id]}
        self._save_settings(settings, thread_schedule_overrides=overrides, thread_domains=domains, **changes)
        await self._category(user_id, chat_id, priority, page)

    async def _history(self, user_id: int, chat_id: int, page: int) -> None:
        items, total = self._db.list_attempts_page(page, PAGE_SIZE)
        builder = InlineKeyboardBuilder()
        for item in items:
            result = "успех" if item["success"] else "ошибка"
            builder.button(text=f"#{item['id']} · {item['thread_id']} · {result}", callback_data=f"attempt:{item['id']}:{page}")
        self._pagination(builder, page, total, "history")
        builder.button(text="Назад", callback_data="root")
        builder.adjust(1)
        await self._show(user_id, chat_id, "История поднятий", builder.as_markup())

    async def _attempt(self, user_id: int, chat_id: int, attempt_id: int, page: int) -> None:
        item = self._db.get_attempt(attempt_id)
        if item is None:
            await self._history(user_id, chat_id, page)
            return
        text = (f"Поднятие #{item['id']}\nВремя: {item['window_started_at']}\nТема: {item['thread_id']}\n"
                f"Категория: {item['priority']}\nРезультат: {'успех' if item['success'] else 'ошибка'}\n"
                f"HTTP: {item['status_code'] or 'нет'}\nОшибка: {item['error_message'] or 'нет'}")
        await self._show(user_id, chat_id, text, self._back_keyboard(f"history:{page}"))

    async def _system(self, user_id: int, chat_id: int) -> None:
        builder = InlineKeyboardBuilder()
        builder.button(text="Задать LOLZ_API_TOKEN", callback_data="token")
        builder.button(text="Шаблоны постинга", callback_data="templates:0")
        builder.button(text="Назад", callback_data="root")
        builder.adjust(1)
        await self._show(user_id, chat_id, "Системные настройки", builder.as_markup())

    async def _templates(self, user_id: int, chat_id: int, page: int) -> None:
        templates = self._db.get_settings().posting_templates
        builder = InlineKeyboardBuilder()
        builder.button(text="Добавить шаблон", callback_data="template_add")
        for template in templates[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
            builder.button(text=template.name, callback_data=f"template:{template.id}")
        self._pagination(builder, page, len(templates), "templates")
        builder.button(text="Назад", callback_data="system")
        builder.adjust(1)
        await self._show(user_id, chat_id, "Шаблоны постинга", builder.as_markup())

    async def _template(self, user_id: int, chat_id: int, template_id: int) -> None:
        template = self._find_template(self._db.get_settings(), template_id)
        if template is None:
            await self._templates(user_id, chat_id, 0)
            return
        builder = InlineKeyboardBuilder()
        builder.button(text="Изменить расписание", callback_data=f"template_schedule:{template.id}")
        builder.button(text="Переименовать", callback_data=f"template_rename:{template.id}")
        builder.button(text="Удалить шаблон", callback_data=f"template_delete:{template.id}")
        builder.button(text="Назад", callback_data="templates:0")
        builder.adjust(1)
        await self._show(user_id, chat_id, f"Шаблон: {template.name}\nГрафик:\n" + "\n".join(template.schedule_times), builder.as_markup())

    async def _delete_template(self, user_id: int, chat_id: int, template_id: int) -> None:
        settings = self._db.get_settings()
        templates = [template for template in settings.posting_templates if template.id != template_id]
        if len(templates) == len(settings.posting_templates):
            await self._templates(user_id, chat_id, 0)
            return
        self._save_settings(settings, posting_templates=templates, reload_scheduler=False)
        await self._templates(user_id, chat_id, 0)

    def _save_settings(self, settings: SchedulingSettings, reload_scheduler: bool = True, **changes: object) -> None:
        payload = settings.model_dump()
        payload.update(changes)
        self._db.save_settings(SchedulingSettings.model_validate(payload))
        if reload_scheduler:
            self._reload_scheduler()

    def _find_template(self, settings: SchedulingSettings, template_id: int) -> PostingTemplate | None:
        return next((template for template in settings.posting_templates if template.id == template_id), None)

    def _next_template_id(self, settings: SchedulingSettings) -> int:
        return max((template.id for template in settings.posting_templates), default=0) + 1

    def _validate_template_name(self, value: str, settings: SchedulingSettings, excluded_id: int | None = None) -> str:
        name = value.strip()
        if not name or len(name) > 64:
            raise ValueError("invalid posting template name")
        if any(template.name == name and template.id != excluded_id for template in settings.posting_templates):
            raise ValueError("duplicate posting template name")
        return name

    def _save_thread_schedule(
        self,
        settings: SchedulingSettings,
        action: str,
        context: tuple[str, ...],
        times: list[str],
    ) -> tuple[str, int]:
        if action == "new_schedule":
            priority, page, thread_id_raw, thread_domain = context
            thread_id = int(thread_id_raw)
            changes = {"important_threads": settings.important_threads + [thread_id]} if priority == "important" else {"regular_threads": settings.regular_threads + [thread_id]}
            domains = dict(settings.thread_domains)
            domains[thread_id] = thread_domain
            changes["thread_domains"] = domains
        else:
            priority, thread_id_raw, page = context
            thread_id = int(thread_id_raw)
            changes = {}
        overrides = dict(settings.thread_schedule_overrides)
        overrides[thread_id] = list(times)
        changes["thread_schedule_overrides"] = overrides
        self._save_settings(settings, **changes)
        return priority, int(page)

    async def _apply_template(self, user_id: int, chat_id: int, template_id: int) -> None:
        pending = self._pending.pop(user_id, None)
        if pending is None or pending[0] not in {"new_schedule", "schedule"}:
            await self._themes(user_id, chat_id)
            return
        settings = self._db.get_settings()
        template = self._find_template(settings, template_id)
        if template is None:
            self._pending[user_id] = pending
            await self._template_choices(user_id, chat_id, 0)
            return
        priority, page = self._save_thread_schedule(settings, pending[0], pending[1], template.schedule_times)
        await self._category(user_id, chat_id, priority, page)

    def _pagination(self, builder: InlineKeyboardBuilder, page: int, total: int, prefix: str) -> None:
        if page > 0:
            builder.button(text="‹", callback_data=f"{prefix}:{page - 1}")
        if (page + 1) * PAGE_SIZE < total:
            builder.button(text="›", callback_data=f"{prefix}:{page + 1}")

    def _back_keyboard(self, callback_data: str) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="Назад", callback_data=callback_data)
        return builder.as_markup()

    async def notify_window_finished(self, summary: WindowSummary) -> None:
        text = f"Окно {summary.schedule_time}: {summary.success_count} успешно, {summary.failed_count} с ошибкой."
        for chat_id, _ in self._db.list_dashboard_chats(sorted(self._admins)):
            try:
                await self._bot.send_message(chat_id, text)
            except (TelegramBadRequest, TelegramForbiddenError):
                continue
            await asyncio.sleep(1 / 30)

    async def _show(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        keyboard: InlineKeyboardMarkup,
        new_message: bool = False,
    ) -> None:
        if not new_message:
            dashboard = self._db.get_dashboard_message(user_id)
            if dashboard is not None:
                try:
                    await self._bot.edit_message_text(text=text, chat_id=dashboard[0], message_id=dashboard[1], reply_markup=keyboard)
                    return
                except TelegramBadRequest as exc:
                    if "message is not modified" in str(exc):
                        return
        message = await self._bot.send_message(chat_id, text, reply_markup=keyboard)
        self._db.set_dashboard_message(user_id, chat_id, message.message_id)
