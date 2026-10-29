#!/usr/bin/env python3
"""Unit tests for the /tasks command (bot/modules/status.py::tasks_count).

The real bot needs Telegram credentials, a database and many third-party
packages just to be imported, so these tests stub those out and load the REAL:
  - bot/modules/status.py                    (the handler under test)
  - bot/helper/telegram_helper/bot_commands.py
  - bot/helper/themes/kpsml_minimal.py       (the real message template)

Run from the project root:
    python3 -m unittest tests.test_tasks_command -v
"""
import asyncio
import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


def build_module_under_test(suffix=''):
    """Stub the heavy imports, then import the real status.py."""
    state = SimpleNamespace(download_dict={}, download_dict_lock=asyncio.Lock())

    # --- stand-in for the top-level `bot` package -------------------------
    fake_bot_client = MagicMock(name='bot_client')
    _stub('bot',
          bot_cache={}, status_reply_dict_lock=asyncio.Lock(),
          download_dict=state.download_dict, download_dict_lock=state.download_dict_lock,
          botStartTime=0, Interval=[], bot=fake_bot_client, bot_name='testbot',
          CMD_SUFFIX=suffix, config_dict={'SHOW_EXTRA_CMDS': False, 'STATUS_UPDATE_INTERVAL': 10,
                                      'DOWNLOAD_DIR': '/tmp'})

    # --- third-party packages ---------------------------------------------
    handler_cls = MagicMock(name='MessageHandler')
    command_fn = MagicMock(name='command')
    _stub('pyrogram')
    _stub('pyrogram.handlers', MessageHandler=handler_cls, CallbackQueryHandler=MagicMock())
    _stub('pyrogram.filters', command=command_fn, regex=MagicMock())
    _stub('psutil', cpu_percent=MagicMock(), virtual_memory=MagicMock(), disk_usage=MagicMock())

    # --- bot.helper.* ------------------------------------------------------
    for pkg in ('bot.helper', 'bot.helper.telegram_helper', 'bot.helper.ext_utils', 'bot.helper.themes'):
        _stub(pkg)
    _stub('bot.helper.telegram_helper.filters', CustomFilters=MagicMock(name='CustomFilters'))
    _stub('bot.helper.telegram_helper.message_utils',
          sendMessage=AsyncMock(), editMessage=AsyncMock(), deleteMessage=AsyncMock(),
          auto_delete_message=AsyncMock(), sendStatusMessage=AsyncMock(), user_info=AsyncMock(),
          update_all_messages=AsyncMock(), delete_all_messages=AsyncMock())
    _stub('bot.helper.ext_utils.bot_utils',
          get_readable_file_size=MagicMock(), get_readable_time=MagicMock(),
          turn_page=AsyncMock(), setInterval=MagicMock(),
          new_task=lambda f: f)  # run the coroutine directly so tests can await it

    # real BotCommands + real theme
    cmds_mod = _load('bot.helper.telegram_helper.bot_commands',
                     'bot/helper/telegram_helper/bot_commands.py')
    theme_mod = _load('real_theme', 'bot/helper/themes/kpsml_minimal.py')

    def BotTheme(var_name, **fmt):  # same logic as the real BotTheme()
        return getattr(theme_mod.KPSMLStyle(), var_name).format_map(fmt)
    sys.modules['bot.helper.themes'].BotTheme = BotTheme

    status = _load('status_under_test', 'bot/modules/status.py')
    return status, state, cmds_mod, handler_cls, command_fn


def make_dl(user_id):
    """Minimal stand-in for a status object stored in download_dict."""
    from_user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(message=SimpleNamespace(from_user=from_user))


def make_msg(user_id):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id) if user_id is not None else None)


class TasksCommandTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        (cls.status, cls.state, cls.cmds_mod,
         cls.handler_cls, cls.command_fn) = build_module_under_test()

    def setUp(self):
        self.state.download_dict.clear()
        self.status.sendMessage = AsyncMock(return_value='reply_obj')
        self.status.auto_delete_message = AsyncMock()

    async def run_cmd(self, user_id):
        msg = make_msg(user_id)
        await self.status.tasks_count(None, msg)
        text = self.status.sendMessage.await_args.args[1]
        return msg, text

    # ---- counting -------------------------------------------------------
    async def test_no_tasks_shows_zero_and_zero(self):
        _, text = await self.run_cmd(111)
        self.assertIn('Bot Tasks:</b> 0', text)
        self.assertIn('User Tasks:</b> 0', text)

    async def test_matches_the_example_from_the_request(self):
        # 4 bot tasks in total, 1 of them belongs to the caller
        for i, uid in enumerate([111, 222, 222, 333]):
            self.state.download_dict[i] = make_dl(uid)
        _, text = await self.run_cmd(111)
        self.assertIn('Bot Tasks:</b> 4', text)
        self.assertIn('User Tasks:</b> 1', text)

    async def test_user_count_is_per_caller(self):
        for i, uid in enumerate([111, 222, 222, 333]):
            self.state.download_dict[i] = make_dl(uid)
        _, text222 = await self.run_cmd(222)
        _, text999 = await self.run_cmd(999)  # has no tasks
        self.assertIn('User Tasks:</b> 2', text222)
        self.assertIn('Bot Tasks:</b> 4', text222)
        self.assertIn('User Tasks:</b> 0', text999)
        self.assertIn('Bot Tasks:</b> 4', text999)

    async def test_all_tasks_belong_to_caller(self):
        for i in range(3):
            self.state.download_dict[i] = make_dl(111)
        _, text = await self.run_cmd(111)
        self.assertIn('Bot Tasks:</b> 3', text)
        self.assertIn('User Tasks:</b> 3', text)

    async def test_counts_update_when_tasks_finish(self):
        self.state.download_dict.update({1: make_dl(111), 2: make_dl(111)})
        _, before = await self.run_cmd(111)
        del self.state.download_dict[1]
        _, after = await self.run_cmd(111)
        self.assertIn('Bot Tasks:</b> 2', before)
        self.assertIn('Bot Tasks:</b> 1', after)
        self.assertIn('User Tasks:</b> 1', after)

    # ---- edge cases -----------------------------------------------------
    async def test_anonymous_admin_does_not_crash(self):
        # message.from_user is None for anonymous group admins / channels
        self.state.download_dict.update({1: make_dl(111), 2: make_dl(222)})
        _, text = await self.run_cmd(None)
        self.assertIn('Bot Tasks:</b> 2', text)
        self.assertIn('User Tasks:</b> 0', text)

    async def test_task_without_from_user_does_not_crash_or_match(self):
        self.state.download_dict.update({1: make_dl(None), 2: make_dl(111)})
        _, text = await self.run_cmd(111)
        self.assertIn('Bot Tasks:</b> 2', text)
        self.assertIn('User Tasks:</b> 1', text)

    # ---- output / side effects -----------------------------------------
    async def test_output_format(self):
        self.state.download_dict[1] = make_dl(111)
        _, text = await self.run_cmd(111)
        self.assertIn('@testbot', text)  # bot name shown (multi-bot groups)
        plain = re.sub(r'<[^>]+>', '', text).splitlines()
        self.assertEqual(plain[1:], ['┠ Bot Tasks: 1', '┖ User Tasks: 1'])

    async def test_replies_to_command_message_and_schedules_auto_delete(self):
        msg, _ = await self.run_cmd(111)
        self.assertIs(self.status.sendMessage.await_args.args[0], msg)
        self.status.auto_delete_message.assert_awaited_once_with(msg, 'reply_obj')

    async def test_does_not_modify_download_dict(self):
        self.state.download_dict.update({1: make_dl(111), 2: make_dl(222)})
        await self.run_cmd(111)
        self.assertEqual(set(self.state.download_dict), {1, 2})

    async def test_lock_is_released_after_command(self):
        await self.run_cmd(111)
        self.assertFalse(self.state.download_dict_lock.locked())


class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (cls.status, cls.state, cls.cmds_mod,
         cls.handler_cls, cls.command_fn) = build_module_under_test()

    def test_command_name_without_suffix(self):
        self.assertEqual(self.cmds_mod.BotCommands.TasksCommand, ['tasks'])

    def test_handler_registered_for_tasks_command(self):
        self.command_fn.assert_any_call(['tasks'])
        handlers = [c.args[0] for c in self.handler_cls.call_args_list]
        self.assertIn(self.status.tasks_count, handlers)

    def test_tasks_does_not_collide_with_any_other_command(self):
        flat = []
        for v in vars(self.cmds_mod.BotCommands).values():
            flat.extend(v if isinstance(v, list) else [v])
        self.assertEqual(flat.count('tasks'), 1)

    def test_existing_status_command_untouched(self):
        self.assertEqual(self.cmds_mod.BotCommands.StatusCommand, ['status', 's', 'statusall'])


class SuffixTests(unittest.TestCase):
    """Multi-bot setups use CMD_SUFFIX (e.g. /stats3, /log3) - /tasks3 must work too."""

    def test_suffix_3_gives_both_tasks_and_tasks3(self):
        _, _, cmds_mod, handler_cls, command_fn = build_module_under_test(suffix='3')
        self.assertEqual(cmds_mod.BotCommands.TasksCommand, ['tasks', 'tasks3'])
        command_fn.assert_any_call(['tasks', 'tasks3'])

    def test_menu_and_help_use_the_suffixed_name(self):
        _, _, cmds_mod, _, _ = build_module_under_test(suffix='3')
        self.assertEqual(cmds_mod.BotCommands.TasksCommand[-1], 'tasks3')

    def test_suffix_3_does_not_collide_with_other_commands(self):
        _, _, cmds_mod, _, _ = build_module_under_test(suffix='3')
        flat = []
        for v in vars(cmds_mod.BotCommands).values():
            flat.extend(v if isinstance(v, list) else [v])
        self.assertEqual(flat.count('tasks3'), 1)
        self.assertEqual(flat.count('tasks'), 1)


class IntegrationWiringTests(unittest.TestCase):
    """The command must also appear in /help and the Telegram command menu."""

    def test_listed_in_help_message(self):
        src = (ROOT / 'bot/helper/ext_utils/help_messages.py').read_text()
        self.assertIn('BotCommands.TasksCommand', src)

    def test_listed_in_command_menu(self):
        src = (ROOT / 'bot/helper/ext_utils/bot_utils.py').read_text()
        self.assertIn('BotCommands.TasksCommand', src)

    def test_theme_template_has_all_placeholders(self):
        src = (ROOT / 'bot/helper/themes/kpsml_minimal.py').read_text()
        m = re.search(r"TASKS_COUNT = '''(.*?)'''", src, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(set(re.findall(r'{(\w+)}', m.group(1))), {'BOT', 'BT', 'UT'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
