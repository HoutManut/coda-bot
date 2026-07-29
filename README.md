# coda-bot

A Discord bot for [Arcaea](https://arcaea.lowiro.com/) that can track scores in semi-realtime,
view song info, and mini games.

Arcaea has no public API. coda-bot works the way a friend would: it runs a small pool
of dedicated in-game accounts, friends you when you register, and reads your recent
plays from the friends list. See **[How it works, and what it stores](#how-it-works-and-what-it-stores)**
below for how it connects to an account and what it keeps.

Because it keeps every play it sees, it also builds a **b30** for you over time — and,
with a linked Arcaea login, an **r10** and a full **PTT**, using the game's own formula
and shown to more decimal places than the game gives you. It's a tracker rather than a
copy of lowiro's number: it knows the plays it has watched, so it starts empty and fills
in as you play.

Built on [hikari](https://github.com/hikari-py/hikari) +
[lightbulb v3](https://github.com/tandemdude/hikari-lightbulb), Python 3.14,
Postgres, SQLAlchemy 2.0, Alembic.

## Public instance

**[Invite coda-bot to your server](TODO-INVITE-URL)**

<!-- TODO: fill in invite URL, hosting region, uptime expectations, support server link,
     and who to contact for a manual data purge. -->

Run by the maintainer. See **[How it works, and what it stores](#how-it-works-and-what-it-stores)**
for more details. If you want to use the full functionality of the bot but don't want
to risk sending your logins to someone else, you might want to try
[self-hosting](#self-hosting) it.

## Commands

| Command | What it does |
|---|---|
| `/register` | Link your Arcaea account — by friend code (recommended) or Arcaea login (optional, richer data) |
| `/unregister` | Stop tracking your Arcaea account entirely (your stored plays are kept) |
| `/recent` | Show your most recent play |
| `/song` | Look up a song, a chart, or browse by level/CC |
| `/calc` | Work out the play rating a score would earn |
| `/linkinfo` | What linking your Arcaea login does, and why it's optional |
| `/unlink` | Remove your stored Arcaea login (your scores keep tracking via friend code) |
| `/liveupdates` `allow` / `disallow` | Allow live score updates in a channel (admin) |
| `/liveupdates` `channel` | Choose where your live score updates go |
| `/liveupdates` `on` / `off` | Start / stop your live score updates |
| `/liveupdates` `status` | Show where your live updates currently go |
| `/config` `user` / `channel` / `server` / `global` | Scoped bot configuration (each scope gated by the matching permission) |
| `/config` `view` | Show resolved config for this context |
| `/reconcile` | Backfill chart resolution on stored plays (bot owner only) |
| `/ping` | Check if the bot is alive |

Registration is consent-aware: friend codes are public, so claiming a code someone
else already registered asks the current owner for approval via DM rather than
silently transferring anything. Logging in is the only real proof of ownership.

## Status

Under active development. The account plumbing, the catalog and score tracking are
done; live posting and tournaments are not.

- [x] Registration (`/register`) with both tiers: friend code and full login
- [x] Owner-approval flow for contested friend codes
- [x] Bot-account session pool against lowiro's private web API
- [x] Song/chart catalog with aliases and tags, plus a local web admin editor
- [x] Scoped settings system (`/config`)
- [x] Live-update configuration (`/liveupdates`)
- [x] Score polling and storage
- [x] Score → chart resolution, with a `/reconcile` backfill pass
- [x] Recent play display (`/recent`) and play-rating maths (`/calc`)
- [x] Song and chart lookup (`/song`)
- [ ] Live score posting to channels/DMs
- [ ] b30 tracking and display (works on both tiers)
- [ ] r10 and computed PTT (needs a linked Arcaea login)
- [ ] Profile / best-scores commands
- [ ] Mini games
- [ ] Tournament module
- [ ] Artist and charter lookup
- [ ] Context-menu commands

## How it works, and what it stores

Arcaea exposes no public API, so the bot reads scores through a player's own account.
Two methods (tier), plus an automatic third for Arcaea Online subscribers.

| Tier | How it reads | What it stores |
|---|---|---|
| **Friend code** (default) | One of the bot's dedicated in-game accounts friends you, and your recent plays are read off its friends list — exactly what another player sees. No password. **Enough for ~90% of the bot** — tracking, live updates, b30, tournaments. | Your 9-digit friend code, in-game user id, display name, which bot account friended you, and every play the poller observes |
| **Arcaea login** (optional) | The bot logs in and requests scores **on your behalf**, which returns richer data — full note breakdowns (pure / far / lost), and the clear/gauge fields the recent-10 pool needs, so **r10 and PTT are computable on this tier only**. Removable anytime with `/unlink`; scores keep tracking via friend code afterward. | The above, plus your Arcaea **email and password**, the session cookie, and your Arcaea Online expiry |
| **Arcaea Online** (automatic) | If a linked login has an active subscription, the same on-behalf path also reaches best scores, full play history, and lowiro's own play-rating figures. | Same as above |

Discord side: your user id, your `/liveupdates` destination choice, and any `/config`
values you set. No message content is stored.

**Credentials.** Email and password are encrypted at rest with
[Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + HMAC) under a single
key held in the host's environment — never in the database, never in the repo, no
rotation path. They are stored **reversibly by necessity, not by choice**: lowiro's
private API has no tokens, no OAuth and no refresh flow, so the bot must replay the real
password when a session expires. Hashing is not an option. Anyone holding both the
database and the key can read your Arcaea password in plaintext, so **link a login only
on a host you trust** — the friend-code tier needs no password, and `/unlink` deletes the
credential row outright. Passwords, and exception context from credential paths, are
never logged.

**Sessions** live in Postgres. Each account sends one fixed, internally consistent
browser fingerprint — Cloudflare insurance for hand-made, unreplaceable accounts, not an
attempt to hide from lowiro.

**Your plays are kept on purpose.** Arcaea exposes only your *latest* play — no history
endpoint, no backfill — so every stored play is a one-shot capture that cannot be
re-fetched if deleted. So **`/unregister` does not delete your scores.** It removes your
link, and if that was the account's last one it also deletes stored credentials, releases
the bot's friend slot (unfriending you in-game), marks the account inactive and stops
polling. The account row and its plays survive either way and reattach if you register
the same friend code again; the foreign key is `RESTRICT` so no future deletion can
cascade that history away. If someone else is still linked to the same account, your
`/unregister` removes only *your* link. To erase stored plays, ask the instance host to
purge the rows — there is no self-serve hard delete today.

**Unofficial.** coda-bot is not affiliated with, endorsed by, or supported by lowiro. It
reads an undocumented private web API that can change or close at any time, using
ordinary in-game friending. Self-hosters are responsible for their own use of it and for
the accounts they point it at.

**Likely breaks Arcaea's ToS, two ways.** (1) Scraping `webapi.lowiro.com` — private,
undocumented, no public API grant. (2) One-account-per-person: the app enforces one
Arcaea account per Discord user, but the bot-account pool itself is several in-game
accounts controlled by one operator (the host) to serve strangers' friend-list reads —
that's multiple accounts under one person by the letter of most such rules, even though
no single *user* ends up multi-linked. Real-world risk is bot-account bans, not legal
exposure; scale here is small (a handful of accounts, a private-use instance) but this is
not a sanctioned integration and could be shut off or enforced against without notice.

## Self-hosting

You'll need Python 3.14 + [`uv`](https://docs.astral.sh/uv/), Postgres, a Discord bot
token, and at least one Arcaea account to act as the bot's in-game account.

See **[docs/self-hosting.md](docs/self-hosting.md)** for the full guide: configuration
reference, catalog seeding, bot-account setup, the admin editor, and notes on the
lowiro API layer.

## License

[MIT](LICENSE). Arcaea and its assets are the property of lowiro — this repo ships no
game art or song data.

## AI usage

Most of the code here was written by [Claude Code](https://claude.com/claude-code) under
human direction. The architecture, the domain decisions, the security trade-offs above and
the review of what landed are mine; the typing was largely not.

Worth knowing if you're reading or self-hosting this: design intent lives in `CLAUDE.md`,
`CODING_STYLE.md` and `wiki/`, which are written to be read by both humans and the
model — that's where a decision's *why* is recorded, and it's usually more detailed than
the code comments. Treat AI-written code here as reviewed, not as unattended.
