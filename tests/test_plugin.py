import asyncio
import os
import types
import unittest

from hermes_xmpp import adapter


def clear_xmpp_env():
    for key in list(os.environ):
        if key.startswith("XMPP_"):
            os.environ.pop(key, None)


class FakeContext:
    def __init__(self):
        self.calls = []

    def register_platform(self, **kwargs):
        self.calls.append(kwargs)


class PluginRegistrationTests(unittest.TestCase):
    def setUp(self):
        clear_xmpp_env()

    def tearDown(self):
        clear_xmpp_env()

    def test_register_exposes_hermes_platform_hooks(self):
        ctx = FakeContext()
        adapter.register(ctx)
        self.assertEqual(len(ctx.calls), 1)
        entry = ctx.calls[0]
        self.assertEqual(entry["name"], "xmpp")
        self.assertEqual(entry["label"], "XMPP")
        self.assertEqual(entry["cron_deliver_env_var"], "XMPP_HOME_CHAT")
        self.assertEqual(entry["allowed_users_env"], "XMPP_ALLOWED_USERS")
        self.assertEqual(entry["allow_all_env"], "XMPP_ALLOW_ALL_USERS")
        self.assertTrue(callable(entry["adapter_factory"]))
        self.assertTrue(callable(entry["standalone_sender_fn"]))
        self.assertIn("XMPP", entry["platform_hint"])
        self.assertEqual(entry["max_message_length"], adapter.DEFAULT_TEXT_CHUNK_LIMIT)
        self.assertTrue(entry["adapter_factory"](types.SimpleNamespace(extra={})).splits_long_messages)

    def test_validate_config_accepts_password_file_or_command_resolution(self):
        cfg = types.SimpleNamespace(extra={"jid": "bot@example.org", "server": "chat.example.org", "password": "secret"})
        self.assertTrue(adapter.validate_config(cfg))
        missing = types.SimpleNamespace(extra={"jid": "bot@example.org", "server": "chat.example.org"})
        self.assertFalse(adapter.validate_config(missing))

    def test_env_enablement_accepts_compatibility_aliases(self):
        os.environ["XMPP_JID"] = "bot@example.org"
        os.environ["XMPP_HOST"] = "chat.example.org"
        os.environ["XMPP_PASSWORD"] = "secret"
        os.environ["XMPP_MUC_ROOMS"] = "room@muc.example.org"
        os.environ["XMPP_HOME_CHANNEL"] = "home@example.org"
        os.environ["XMPP_REACTION_START_CHOICES"] = "👀,😘"
        os.environ["XMPP_ANONYMOUS_MUC_POLICY"] = "deny"
        os.environ["XMPP_TOOL_PROGRESS_BUBBLE_LIMIT"] = "17"
        os.environ["XMPP_EDITABLE_PROGRESS"] = "disabled"

        enabled = adapter._env_enablement()

        if enabled is None:
            self.fail("expected XMPP aliases to enable platform config")
        self.assertNotIn("extra", enabled)
        self.assertEqual(enabled["jid"], "bot@example.org")
        self.assertEqual(enabled["server"], "chat.example.org")
        self.assertEqual(enabled["rooms"], ["room@muc.example.org"])
        self.assertEqual(enabled["home_chat"], "home@example.org")
        self.assertEqual(enabled["reaction_start_choices"], ["👀", "😘"])
        self.assertEqual(enabled["anonymous_muc_policy"], "deny")
        self.assertEqual(enabled["tool_progress_bubble_limit"], 17)
        self.assertEqual(enabled["editable_progress_policy"], "disabled")
        self.assertEqual(enabled["home_channel"]["chat_id"], "home@example.org")

        seed = dict(enabled)
        seed.pop("home_channel")
        platform_extra = {}
        platform_extra.update(seed)
        self.assertEqual(platform_extra["jid"], "bot@example.org")
        self.assertEqual(platform_extra["rooms"], ["room@muc.example.org"])
        self.assertEqual(platform_extra["anonymous_muc_policy"], "deny")
        self.assertEqual(platform_extra["tool_progress_bubble_limit"], 17)
        self.assertEqual(platform_extra["editable_progress_policy"], "disabled")

    def test_standalone_sender_reports_unconfigured_without_crashing(self):
        cfg = types.SimpleNamespace(extra={})
        result = asyncio.run(adapter._standalone_send(cfg, "user@example.org", "hello"))
        self.assertIn("error", result)
        self.assertIn("required", result["error"])


if __name__ == "__main__":
    unittest.main()
