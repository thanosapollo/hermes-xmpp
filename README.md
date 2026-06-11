# hermes-xmpp

Hermes Agent XMPP platform adapter, modeled conceptually after `openclaw-xmpp` but implemented against Hermes gateway plugin abstractions.

Status: Hermes-native adapter implementation in progress. It remains isolated from OpenClaw and is designed for local Hermes plugin installation after tests pass.

## Goals

- Direct XMPP chats first.
- MUC room support second, with conservative mention/allowlist defaults.
- Hermes-native platform registration through `ctx.register_platform()`.
- Secret handling through env vars, password files, or password commands.
- Clear separation from OpenClaw runtime state.

## Hermes Plugin Shape

Hermes community platform plugins use:

- `plugin.yaml` for metadata and setup UI env prompts.
- `adapter.py` with a `BasePlatformAdapter` subclass.
- `register(ctx)` to call `ctx.register_platform(...)`.

This repository keeps the adapter in `hermes_xmpp/adapter.py`. For local Hermes plugin discovery, symlink or copy the package directory into the operator's Hermes plugin directory only after review.

## Configuration

Environment variables:

- `XMPP_JID`: account JID, for example `bot@example.org`.
- `XMPP_SERVER`: XMPP server hostname, `host:port`, or URL such as `xmpp://chat.example.org:5222`.
- `XMPP_PORT`: optional TCP port override.
- `XMPP_PASSWORD`: account password. Prefer `XMPP_PASSWORD_FILE` or `XMPP_PASSWORD_COMMAND`.
- `XMPP_PASSWORD_FILE`: file containing the password.
- `XMPP_PASSWORD_COMMAND`: command that prints the password to stdout, for example `pass show xmpp/bot@example.org`.
- `XMPP_RESOURCE`: resource name, default `hermes`.
- `XMPP_NICKNAME`: MUC nickname, default localpart from `XMPP_JID`.
- `XMPP_ROOMS`: comma-separated MUC JIDs to join.
- `XMPP_ALLOWED_USERS`: comma-separated bare JIDs or patterns allowed to use direct chat. Supports exact JIDs, `*@domain`, and `*`.
- `XMPP_DM_POLICY`: `allowlist` (default), `open`, `disabled`, or `pairing` (treated as allowlist unless Hermes pairing is configured separately).
- `XMPP_ALLOW_ALL_USERS`: allow all direct-chat senders. Use only for trusted/dev environments.
- `XMPP_GROUP_POLICY`: `allowlist` (default), `open`, or `disabled`.
- `XMPP_ALLOWED_ROOMS`: comma-separated MUC room JIDs allowed when group policy is `allowlist`.
- `XMPP_GROUP_ALLOW_FROM`: comma-separated bare JIDs or patterns allowed inside MUCs.
- `XMPP_MUC_REQUIRE_MENTION`: default `true`.
- `XMPP_HOME_CHAT`: default destination for cron/notification delivery.
- `XMPP_SEND_DELIVERY_RECEIPTS`: send XEP-0184 `<received xmlns='urn:xmpp:receipts'/>` replies to authorized direct-chat messages that request them. Default `true`.
- `XMPP_SEND_RECEIVED_MARKERS`: send XEP-0333 `<received xmlns='urn:xmpp:chat-markers:0'/>` markers to authorized direct-chat messages marked `<markable/>`. Default `true`.
- `XMPP_SEND_READ_RECEIPTS`: send XEP-0333 `<displayed/>` read/display markers to authorized direct-chat messages marked `<markable/>`. Default `false` for privacy.

Receipt/marker behavior is conservative: replies are only sent after allowlist authorization, marker/receipt stanzas do not get marker replies, and groupchat marker/receipt sending is disabled for now because XEP-0333 requires extra care around MUC stanza IDs (XEP-0359).

Equivalent YAML values should live under `gateway.platforms.xmpp.extra` when Hermes loads the plugin:

```yaml
gateway:
  platforms:
    xmpp:
      enabled: true
      extra:
        jid: bot@example.org
        server: chat.example.org
        password_file: /run/secrets/hermes-xmpp-password
        resource: hermes
        rooms:
          - room@muc.example.org
        allowed_users:
          - user@example.org
        muc_require_mention: true
```

## Rollback

This repo is isolated. Rollback is:

1. Disable `gateway.platforms.xmpp.enabled` in Hermes config if it was enabled.
2. Remove any symlink/copy from `~/.hermes/plugins/`.
3. Stop/restart only the Hermes gateway if a live Hermes gateway was running.
4. Delete or archive this repository if no longer needed.

No OpenClaw state or service should be touched.
