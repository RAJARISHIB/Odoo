# Realtime hub

The Express service is a message relay, nothing more. It holds no business logic
and touches no database: Django decides what happened, the hub decides who is
listening.

```
Angular  ──ws://localhost:4000/ws?token=<access>&panel=admin──►  Express
                                                                    ▲
Django   ──POST /internal/publish  (header: x-internal-key)─────────┘
```

Why a separate service: Django stays synchronous and simple, the socket layer
scales on its own, and the browser keeps one long-lived connection instead of
polling.

---

## Authentication

The hub verifies the **same access token** Django issues — same `JWT_SECRET`,
same `JWT_ISSUER`, and the `typ` claim must be `access` (a refresh token is
rejected). Nothing else is trusted: the user id, role and organization all come
from the token's claims, never from anything the client says.

Two ways in:

1. **Handshake** — `ws://localhost:4000/ws?token=<accessToken>&panel=admin`.
   A bad token is refused with `401` *before* the upgrade completes. This is what
   the Angular client uses, since browsers cannot set headers on a WebSocket.
2. **First message** — connect without a token, then send
   `{ "type": "auth", "token": "…" }` within `WS_AUTH_GRACE_MS` (default 5s).
   For clients that cannot put a token in the URL. Missing the window closes the
   socket with `4401`.

`Authorization: Bearer …` and `Sec-WebSocket-Protocol: bearer, <token>` also work
for server-side clients.

Close codes: `4401` authentication failed (do **not** retry with the same token —
refresh first), `1013` too many connections for this user, `1001` server shutting
down.

---

## Channels

A channel is a plain string. On connect the hub subscribes the socket to
everything the token entitles it to, so a normal client never has to ask.

| Channel                          | Who receives it                        |
| -------------------------------- | -------------------------------------- |
| `user:<userId>`                  | One person, every tab they have open   |
| `org:<orgId>`                    | Everyone in the organization           |
| `org:<orgId>:panel:admin`        | Admin-panel screens of that org        |
| `org:<orgId>:panel:user`         | Employee-panel screens of that org     |
| `org:<orgId>:role:<role>`        | One role within an org                 |
| `broadcast`                      | Every connected client                 |

Names are defined in **two** places and must stay in step:
`backend/core/realtime.py` and `realtime/src/lib/channels.js`.

**Subscription rules** (`canSubscribe`) — a client may only reach its own
`user:` channel and channels inside its own `org:`; only admin-panel roles may
join an admin channel. A `subscribe` request for anything else comes back in the
`rejected` list rather than being silently ignored. This is what stops one
tenant's browser from listening to another's.

---

## Protocol

### Client → server

| Message                                                            | Purpose                          |
| ------------------------------------------------------------------ | -------------------------------- |
| `{ type: "auth", token }`                                          | Authenticate after connecting    |
| `{ type: "subscribe", channels: [] }`                              | Join extra channels              |
| `{ type: "unsubscribe", channels: [] }`                            | Leave channels                   |
| `{ type: "ui.context", payload: { panel, route, view, params } }`  | Report the screen being shown    |
| `{ type: "ping" }`                                                 | Liveness                         |

### Server → client

| Message                                                    | When                              |
| ---------------------------------------------------------- | --------------------------------- |
| `{ type: "connected", payload: { connectionId, identity, channels } }` | Right after auth       |
| `{ type: "event", event, channel, payload, emittedAt }`    | A domain event was published      |
| `{ type: "subscribed" \| "unsubscribed", payload: { channels, active, rejected } }` | Ack |
| `{ type: "ui.context.ack", payload: { context } }`         | Context stored                    |
| `{ type: "pong", payload: { serverTime } }`                | Reply to ping                     |
| `{ type: "error", payload: { code, message } }`            | Anything rejected                 |

Frames over 64KB are rejected. The server pings every `WS_HEARTBEAT_INTERVAL_MS`
(30s) and terminates a socket that misses two rounds, so dead tabs free their slot.

### UI metadata

`ui.context` is how the UI tells the backend what it is currently doing:

```json
{ "type": "ui.context",
  "payload": { "panel": "admin", "route": "/admin/attendance", "view": "attendance-board" } }
```

The Angular root component sends this on every navigation, and re-sends it after
a reconnect. The hub stores it on the connection, so
`GET /internal/connections` shows not just who is online but which screen each
person is on — the basis for targeting a message at only the screens that care.

---

## Domain events

Published by Django, consumed by Angular. Names live in
`backend/core/constants.py::RealtimeEvent` and `realtime/src/lib/events.js`.

| Event                      | Emitted when                     | Channels                          |
| -------------------------- | -------------------------------- | --------------------------------- |
| `attendance.checked_in`    | Employee checks in               | admin panel + that user           |
| `attendance.checked_out`   | Employee checks out              | admin panel + that user           |
| `attendance.updated`       | Admin corrects a record          | admin panel + affected user       |
| `user.created`             | Employee added                   | admin panel                       |
| `user.updated`             | Profile or role changed          | admin panel + that user           |
| `user.status_changed`      | Suspended, activated, removed    | admin panel                       |
| `organization.updated`     | Org or department changed        | whole org                         |
| `notification`             | Directed message to one user     | that user                         |
| `system.announcement`      | Org-wide or global notice        | org or `broadcast`                |

Emitting from a controller is one line:

```python
self.emit_to_admins(RealtimeEvent.ATTENDANCE_CHECKED_IN, payload)
self.emit_to_user(user.id, RealtimeEvent.NOTIFICATION, {"title": "…", "body": "…"})
self.emit_to_org(RealtimeEvent.ORG_UPDATED, payload)
```

Delivery is **best-effort by design**: if the hub is down the API call still
succeeds and the failure is logged. A notification must never break a write.

Consuming in Angular is one line too:

```ts
this.realtime.on('attendance.checked_in')
  .pipe(takeUntilDestroyed())
  .subscribe((message) => this.refresh());
```

---

## Internal HTTP API

Guarded by `x-internal-key` (constant-time compared). Never expose these routes
publicly.

| Route                       | Purpose                                             |
| --------------------------- | --------------------------------------------------- |
| `POST /internal/publish`    | Fan an event out to channels — the main path        |
| `POST /internal/broadcast`  | Shorthand for the `broadcast` channel               |
| `GET  /internal/connections`| Connected clients, their channels and UI context    |
| `GET  /internal/stats`      | Hub counters                                        |
| `POST /internal/disconnect` | Force-close a user's sockets (ban, forced sign-out) |

`POST /internal/publish` body:

```json
{
  "event": "attendance.checked_in",
  "channels": ["org:<orgId>:panel:admin"],
  "payload": { "user": { "id": "…", "name": "…" }, "attendance": { … } },
  "actor_id": "…",
  "emitted_at": "2026-08-22T04:22:43Z",
  "source": "django"
}
```

Returns `{ delivered, recipients }`. A socket subscribed to two of the listed
channels still receives the message once.

Public routes: `GET /health` (status + counters) and `GET /` (this protocol, as
JSON).

### Presence callback

When a socket connects or disconnects, the hub POSTs to Django's
`/api/v1/internal/realtime/presence` with the user, panel and current connection
count. Today Django just logs it; `core/views.py::realtime_presence` is the hook
to persist it when presence needs to be queryable.

---

## Planned messaging paths

The channels and events above already cover more than the current screens use.
The intended next steps, in order:

1. **Directed notifications** — `notification` on `user:<id>` for approvals,
   reminders and admin messages, with a bell in both shells. The event and the
   channel exist; only the UI surface is missing.
2. **Presence-aware admin board** — the admin attendance board reads
   `GET /internal/connections` to show who is actually online, not just who has
   punched in.
3. **Targeted refresh** — use the stored `ui.context` to publish only to the
   screens that show the affected data, instead of every admin socket.
4. **Announcements** — `system.announcement` on `org:<orgId>` or `broadcast`,
   sent from an admin composer.
5. **Horizontal scale** — the hub is in-process today. `Hub.publish()` is the
   single seam: put Redis pub/sub behind it and several nodes can share fan-out.
