import os
from pathlib import Path
import types
import unittest
from unittest.mock import patch
from typing import Any, cast

from hermes_xmpp import adapter


def clear_xmpp_env():
    for key in list(os.environ):
        if key.startswith("XMPP_"):
            os.environ.pop(key, None)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        clear_xmpp_env()

    def tearDown(self):
        clear_xmpp_env()

    def test_settings_support_policy_port_and_aliases_from_yaml(self):
        cfg = types.SimpleNamespace(
            extra={
                "jid": "Bot@Example.Org/hermes",
                "server": "chat.example.org",
                "port": 5223,
                "password": "secret",
                "dm_policy": "open",
                "group_policy": "allowlist",
                "rooms": ["room@conference.example.org"],
                "groups": ["other@conference.example.org"],
                "allow_from": ["*@example.org"],
                "dm_allowlist": ["friend@example.org"],
                "group_allow_from": ["mod@example.org"],
                "allowed_rooms": ["room@conference.example.org"],
            }
        )
        settings = adapter.XmppSettings.from_config(cfg)
        self.assertEqual(settings.jid, "Bot@Example.Org/hermes")
        self.assertEqual(settings.server, "chat.example.org")
        self.assertEqual(settings.port, 5223)
        self.assertEqual(settings.dm_policy, "open")
        self.assertEqual(settings.group_policy, "allowlist")
        self.assertIn("room@conference.example.org", settings.rooms)
        self.assertIn("other@conference.example.org", settings.rooms)
        self.assertIn("*@example.org", settings.allowed_users)
        self.assertIn("friend@example.org", settings.allowed_users)
        self.assertIn("mod@example.org", settings.group_allow_from)
        self.assertIn("room@conference.example.org", settings.allowed_rooms)

    def test_env_overrides_yaml_and_password_command(self):
        os.environ["XMPP_JID"] = "env@example.org"
        os.environ["XMPP_SERVER"] = "env-server.example.org"
        os.environ["XMPP_PORT"] = "5224"
        os.environ["XMPP_PASSWORD_COMMAND"] = "pass show xmpp/emma"
        with patch.object(adapter, "_read_secret_command", return_value="from-pass") as read_cmd:
            settings = adapter.XmppSettings.from_config(
                types.SimpleNamespace(extra={"jid": "yaml@example.org", "server": "yaml", "password": "yaml"})
            )
        read_cmd.assert_called_once_with("pass show xmpp/emma")
        self.assertEqual(settings.jid, "env@example.org")
        self.assertEqual(settings.server, "env-server.example.org")
        self.assertEqual(settings.port, 5224)
        self.assertEqual(settings.password, "from-pass")


class HelperTests(unittest.TestCase):
    def setUp(self):
        clear_xmpp_env()

    def tearDown(self):
        clear_xmpp_env()

    def test_jid_matching_supports_exact_wildcard_and_domain(self):
        self.assertTrue(adapter._matches_jid("user@example.org", {"user@example.org"}))
        self.assertTrue(adapter._matches_jid("user@example.org/resource", {"*@example.org"}))
        self.assertTrue(adapter._matches_jid("anywhere@example.net", {"*"}))
        self.assertFalse(adapter._matches_jid("user@evil.org", {"*@example.org"}))

    def test_target_normalization_and_group_detection(self):
        self.assertEqual(adapter._normalize_target("xmpp:user@example.org"), "user@example.org")
        self.assertEqual(adapter._normalize_target("xmpp:group:room@conference.example.org"), "room@conference.example.org")
        self.assertTrue(adapter._is_group_jid("room@conference.example.org"))
        self.assertTrue(adapter._is_group_jid("room@muc.example.org"))
        self.assertFalse(adapter._is_group_jid("user@example.org"))

    def test_mention_stripping_accepts_colon_comma_and_at_forms(self):
        cfg = types.SimpleNamespace(extra={"jid": "bot@example.org", "server": "s", "password": "p", "nickname": "Emma"})
        xmpp = adapter.XMPPAdapter(cfg)
        self.assertEqual(xmpp._strip_muc_mention("Emma: hello"), "hello")
        self.assertEqual(xmpp._strip_muc_mention("@Emma hello"), "hello")
        self.assertEqual(xmpp._strip_muc_mention("Emma, hello"), "hello")


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        clear_xmpp_env()

    def tearDown(self):
        clear_xmpp_env()

    def test_direct_policy_disabled_open_and_allowlist(self):
        disabled = adapter.XMPPAdapter(types.SimpleNamespace(extra={"jid": "b@e", "server": "s", "password": "p", "dm_policy": "disabled"}))
        self.assertFalse(disabled._authorized_direct_message("friend@example.org"))
        open_adapter = adapter.XMPPAdapter(types.SimpleNamespace(extra={"jid": "b@e", "server": "s", "password": "p", "dm_policy": "open"}))
        self.assertTrue(open_adapter._authorized_direct_message("anyone@example.org"))
        allow = adapter.XMPPAdapter(types.SimpleNamespace(extra={"jid": "b@e", "server": "s", "password": "p", "allowed_users": ["*@example.org"]}))
        self.assertTrue(allow._authorized_direct_message("friend@example.org/resource"))
        self.assertFalse(allow._authorized_direct_message("friend@evil.org"))

    def test_group_policy_room_allowlist_sender_allowlist_and_mention(self):
        xmpp = adapter.XMPPAdapter(types.SimpleNamespace(extra={
            "jid": "emma@example.org",
            "server": "s",
            "password": "p",
            "nickname": "Emma",
            "group_policy": "allowlist",
            "allowed_rooms": ["room@conference.example.org"],
            "group_allow_from": ["*@example.org"],
            "muc_require_mention": True,
        }))
        self.assertTrue(xmpp._authorized_group_message("friend@example.org", "Emma: hi", room_jid="room@conference.example.org"))
        self.assertFalse(xmpp._authorized_group_message("friend@evil.org", "Emma: hi", room_jid="room@conference.example.org"))
        self.assertFalse(xmpp._authorized_group_message("friend@example.org", "hi", room_jid="room@conference.example.org"))
        self.assertFalse(xmpp._authorized_group_message("friend@example.org", "Emma: hi", room_jid="other@conference.example.org"))


class FakeMessage:
    def __init__(self, **values):
        self.values = values
        self.muc = values.get("muc", {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def __getitem__(self, key):
        return self.values.get(key, "")

    def get_mucnick(self):
        return self.values.get("mucnick", "")

    def get_child(self, name, namespace=None):
        return self.values.get((namespace, name))


class ParseAndReceiptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_xmpp_env()

    def tearDown(self):
        clear_xmpp_env()

    def _settings(self, **extra):
        base = {
            "jid": "emma@example.org",
            "server": "chat.example.org",
            "password": "secret",
            "allowed_users": ["thanos@example.org"],
            "nickname": "Emma",
        }
        base.update(extra)
        return adapter.XmppSettings.from_config(types.SimpleNamespace(extra=base))

    def test_parse_authorize_and_event_text_are_pure_steps(self):
        settings = self._settings()
        msg = FakeMessage(
            body="hello",
            **{"from": "thanos@example.org/dino"},
            type="chat",
            id="m1",
        )
        parsed = adapter.parse_xmpp_message(msg, settings)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.text, "hello")
        self.assertEqual(parsed.chat_type, "dm")
        self.assertEqual(parsed.receipt_target, "thanos@example.org/dino")
        self.assertTrue(adapter.authorized_xmpp_message(parsed, settings))
        self.assertEqual(adapter.event_text_for(parsed, settings), "hello")

    def test_unauthorized_messages_do_not_get_receipt_actions(self):
        settings = self._settings()
        msg = FakeMessage(
            body="hello",
            **{"from": "intruder@example.net/laptop"},
            type="chat",
            id="m2",
            request_receipt=True,
            markable=True,
        )
        parsed = adapter.parse_xmpp_message(msg, settings)
        self.assertFalse(adapter.authorized_xmpp_message(parsed, settings))
        # Caller sends actions only after authorization; helper remains data-only.
        self.assertEqual(
            [a.kind for a in adapter.receipt_actions_for(parsed, settings)],
            [adapter.XmppReceiptKind.DELIVERY_RECEIPT, adapter.XmppReceiptKind.RECEIVED_MARKER],
        )

    def test_receipt_actions_follow_xep_0184_and_xep_0333_settings(self):
        settings = self._settings(send_read_receipts=True)
        msg = FakeMessage(
            body="hello",
            **{"from": "thanos@example.org/dino"},
            type="chat",
            id="m3",
            request_receipt=True,
            markable=True,
        )
        parsed = adapter.parse_xmpp_message(msg, settings)
        self.assertTrue(adapter.authorized_xmpp_message(parsed, settings))
        actions = adapter.receipt_actions_for(parsed, settings)
        self.assertEqual(
            [a.kind for a in actions],
            [
                adapter.XmppReceiptKind.DELIVERY_RECEIPT,
                adapter.XmppReceiptKind.RECEIVED_MARKER,
                adapter.XmppReceiptKind.DISPLAYED_MARKER,
            ],
        )
        self.assertTrue(all(a.to_jid == "thanos@example.org/dino" for a in actions))
        self.assertTrue(all(a.message_id == "m3" for a in actions))

    def test_no_marker_loops_or_groupchat_marker_sends(self):
        settings = self._settings(send_read_receipts=True)
        marker_msg = FakeMessage(
            body="",
            **{"from": "thanos@example.org/dino"},
            type="chat",
            id="marker1",
            received={"id": "m3"},
        )
        self.assertIsNone(adapter.parse_xmpp_message(marker_msg, settings))

        group_msg = FakeMessage(
            body="Emma: hello",
            **{"from": "room@muc.example.org/thanos"},
            type="groupchat",
            id="g1",
            request_receipt=True,
            markable=True,
            muc={"jid": "thanos@example.org"},
            mucnick="thanos",
        )
        parsed = adapter.parse_xmpp_message(group_msg, settings)
        self.assertEqual(adapter.receipt_actions_for(parsed, settings), [])
        self.assertEqual(adapter.event_text_for(parsed, settings), "hello")

    async def test_adapter_sends_receipts_before_dispatch_for_authorized_dm(self):
        cfg = types.SimpleNamespace(extra={
            "jid": "emma@example.org",
            "server": "chat.example.org",
            "password": "secret",
            "allowed_users": ["thanos@example.org"],
            "send_read_receipts": True,
        })
        xmpp = adapter.XMPPAdapter(cfg)

        class FakeClient:
            def __init__(self):
                self.calls = []

            async def send_delivery_receipt(self, to_jid, receipt_id, message_type="chat"):
                self.calls.append(("receipt", to_jid, receipt_id, message_type))

            async def send_chat_marker(self, to_jid, marker_id, marker, message_type="chat"):
                self.calls.append((marker, to_jid, marker_id, message_type))

        fake_client = FakeClient()
        xmpp._client = fake_client
        handled_events = []

        async def capture_event(event):
            handled_events.append(event)

        xmpp.handle_message = capture_event
        msg = FakeMessage(
            body="ping",
            **{"from": "thanos@example.org/dino"},
            type="chat",
            id="m4",
            request_receipt=True,
            markable=True,
        )
        await xmpp.on_xmpp_message(msg)
        self.assertEqual(fake_client.calls, [
            ("receipt", "thanos@example.org/dino", "m4", "chat"),
            ("received", "thanos@example.org/dino", "m4", "chat"),
            ("displayed", "thanos@example.org/dino", "m4", "chat"),
        ])
        self.assertEqual(len(handled_events), 1)
        self.assertEqual(handled_events[0].text, "ping")

    async def test_adapter_sends_composing_to_last_full_dm_resource_and_active_on_stop(self):
        cfg = types.SimpleNamespace(extra={
            "jid": "emma@example.org",
            "server": "chat.example.org",
            "password": "secret",
            "allowed_users": ["thanos@example.org"],
        })
        xmpp = adapter.XMPPAdapter(cfg)

        class FakeClient:
            def __init__(self):
                self.calls = []

            async def send_chat_state(self, to_jid, state, message_type="chat"):
                self.calls.append((state, to_jid, message_type))

        fake_client = FakeClient()
        xmpp._client = fake_client
        async def ignore_event(event):
            return None

        xmpp.handle_message = ignore_event
        msg = FakeMessage(
            body="ping",
            **{"from": "thanos@example.org/dino"},
            type="chat",
            id="m5",
        )
        await xmpp.on_xmpp_message(msg)

        await xmpp.send_typing("thanos@example.org")
        await xmpp.stop_typing("thanos@example.org")

        self.assertEqual(fake_client.calls, [
            ("composing", "thanos@example.org/dino", "chat"),
            ("active", "thanos@example.org/dino", "chat"),
        ])

    async def test_adapter_does_not_send_chat_state_when_disconnected(self):
        cfg = types.SimpleNamespace(extra={"jid": "emma@example.org", "server": "chat.example.org", "password": "secret"})
        xmpp = adapter.XMPPAdapter(cfg)
        await xmpp.send_typing("thanos@example.org")
        await xmpp.stop_typing("thanos@example.org")

    async def test_slixmpp_upload_uses_plugin_indexing_not_dict_get(self):
        class FakeUploadPlugin:
            def __init__(self):
                self.calls = []

            async def upload_file(self, file_path, content_type=None):
                self.calls.append((str(file_path), content_type))
                return "https://upload.example.org/file.bin"

        class FakePluginManager:
            def __init__(self, upload):
                self.upload = upload

            def __getitem__(self, key):
                if key != "xep_0363":
                    raise KeyError(key)
                return self.upload

            def get(self, *args, **kwargs):
                raise TypeError("PluginManager.get() missing 1 required positional argument: 'default'")

        upload = FakeUploadPlugin()
        thin = cast(Any, object.__new__(adapter._SlixmppClient))
        thin.client = types.SimpleNamespace(plugin=FakePluginManager(upload))
        result = await thin.upload_file("/tmp/file.bin", "application/octet-stream")
        self.assertEqual(result, "https://upload.example.org/file.bin")
        self.assertEqual(upload.calls, [("/tmp/file.bin", "application/octet-stream")])

    async def test_slixmpp_send_message_puts_oob_on_same_stanza(self):
        class FakeMessage:
            def __init__(self):
                self.values = {"oob": {}}
                self.sent = False

            def __setitem__(self, key, value):
                self.values[key] = value

            def __getitem__(self, key):
                return self.values.setdefault(key, {})

            def send(self):
                self.sent = True

        class FakeClient:
            def __init__(self):
                self.messages = []
                self.send_message_calls = []

            def make_message(self, mto, mbody, mtype):
                msg = FakeMessage()
                msg.values.update({"to": mto, "body": mbody, "type": mtype})
                self.messages.append(msg)
                return msg

            def send_message(self, **kwargs):
                self.send_message_calls.append(kwargs)

        thin = cast(Any, object.__new__(adapter._SlixmppClient))
        thin.client = FakeClient()
        thin.adapter = types.SimpleNamespace(settings=types.SimpleNamespace(send_chat_states=True))

        message_id = await thin.send_message(
            "thanos@example.org",
            "caption\nhttps://upload.example.org/image.png",
            "chat",
            oob_url="https://upload.example.org/image.png",
        )

        self.assertTrue(message_id.startswith("hermes-"))
        self.assertEqual(len(thin.client.messages), 1)
        msg = thin.client.messages[0]
        self.assertTrue(msg.sent)
        self.assertEqual(msg.values["oob"]["url"], "https://upload.example.org/image.png")
        self.assertEqual(msg.values["chat_state"], "active")
        self.assertEqual(thin.client.send_message_calls, [])

    async def test_media_upload_deterministic_failures_are_not_retryable(self):
        cfg = types.SimpleNamespace(extra={"jid": "emma@example.org", "server": "chat.example.org", "password": "secret"})
        xmpp = adapter.XMPPAdapter(cfg)

        class UploadServiceNotFound(Exception):
            pass

        class FakeClient:
            async def upload_file(self, file_path, content_type=None):
                raise UploadServiceNotFound("HTTP Upload service not found")

        image_path = "/tmp/hermes-test-image-upload-failure.png"
        Path(image_path).write_bytes(b"fake png")
        xmpp._client = cast(Any, FakeClient())

        result = await xmpp.send_image_file("thanos@example.org", image_path)

        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertIn("HTTP Upload service not found", result.error or "")

    async def test_adapter_sends_local_image_via_http_upload_with_oob_url(self):
        cfg = types.SimpleNamespace(extra={"jid": "emma@example.org", "server": "chat.example.org", "password": "secret"})
        xmpp = adapter.XMPPAdapter(cfg)

        class FakeClient:
            def __init__(self):
                self.uploads = []
                self.messages = []

            async def upload_file(self, file_path, content_type=None):
                self.uploads.append((file_path, content_type))
                return "https://upload.example.org/image.png"

            async def send_message(self, to_jid, text, message_type, *, thread_id=None, oob_url=None):
                self.messages.append((to_jid, text, message_type, thread_id, oob_url))
                return "msg-image"

        image_path = "/tmp/hermes-test-image.png"
        Path(image_path).write_bytes(b"fake png")
        fake_client = FakeClient()
        xmpp._client = fake_client

        result = await xmpp.send_image_file("thanos@example.org", image_path, caption="A tiny test")

        self.assertTrue(result.success)
        self.assertEqual(fake_client.uploads, [(image_path, "image/png")])
        self.assertEqual(fake_client.messages, [
            ("thanos@example.org", "A tiny test\nhttps://upload.example.org/image.png", "chat", None, "https://upload.example.org/image.png")
        ])

    def test_declared_media_kinds_tracks_future_fail_closed_gateway_api(self):
        old_media_kind = adapter.MediaKind
        try:
            adapter.MediaKind = types.SimpleNamespace(
                IMAGE="image",
                VIDEO="video",
                VOICE="voice",
                DOCUMENT="document",
            )
            self.assertEqual(
                adapter._declared_media_kinds(),
                frozenset({"image", "video", "voice", "document"}),
            )
        finally:
            adapter.MediaKind = old_media_kind

    async def test_standalone_sender_routes_video_to_send_video(self):
        cfg = types.SimpleNamespace(extra={"jid": "emma@example.org", "server": "chat.example.org", "password": "secret"})

        class FakeAdapter:
            def __init__(self, pconfig):
                self.sent = []

            async def connect(self):
                return True

            async def send_video(self, chat_id, video_path, caption=None, reply_to=None):
                self.sent.append((chat_id, video_path, caption, reply_to))
                return adapter.SendResult(success=True, message_id="video-msg")

            async def disconnect(self):
                return None

        old = adapter.XMPPAdapter
        try:
            adapter.XMPPAdapter = FakeAdapter
            video_path = "/tmp/hermes-standalone-video.mp4"
            Path(video_path).write_bytes(b"fake mp4")
            result = await adapter._standalone_send(cfg, "thanos@example.org", "caption", media_files=[video_path])
        finally:
            adapter.XMPPAdapter = old

        self.assertEqual(result, {"success": True, "message_id": "video-msg"})

    async def test_standalone_sender_uploads_media_files(self):
        cfg = types.SimpleNamespace(extra={"jid": "emma@example.org", "server": "chat.example.org", "password": "secret"})

        class FakeAdapter:
            def __init__(self, pconfig):
                self.sent = []
                self.disconnected = False

            async def connect(self):
                return True

            async def send_image_file(self, chat_id, image_path, caption=None, reply_to=None):
                self.sent.append((chat_id, image_path, caption, reply_to))
                return adapter.SendResult(success=True, message_id="media-msg")

            async def disconnect(self):
                self.disconnected = True

        old = adapter.XMPPAdapter
        try:
            adapter.XMPPAdapter = FakeAdapter
            image_path = "/tmp/hermes-standalone-image.jpg"
            Path(image_path).write_bytes(b"fake jpg")
            result = await adapter._standalone_send(cfg, "thanos@example.org", "caption", media_files=[image_path])
        finally:
            adapter.XMPPAdapter = old

        self.assertEqual(result, {"success": True, "message_id": "media-msg"})


if __name__ == "__main__":
    unittest.main()
