# coda-bot

A Discord bot for [Arcaea](https://arcaea.lowiro.com/) that can track scores in semi-realtime,
view song info, and mini games.

Arcaea has no public API. coda-bot works the way a friend would: it runs a small pool
of dedicated in-game accounts, friends you when you register, and reads your recent
plays from the friends list. See **[How it works, and what it stores](#how-it-works-and-what-it-stores)**
below.

Because it keeps every play it sees, it also builds a **b50** and a **PTT** for you over
time, using the game's own formula and shown to more decimal places than the game gives
you — exactly with a linked Arcaea login, and from a disclosed estimate of each play's
clear status without one. It's a tracker rather than a copy of lowiro's number: it knows
the plays it has watched, so it starts empty and fills in as you play.

Built on [hikari](https://github.com/hikari-py/hikari) +
[lightbulb v3](https://github.com/tandemdude/hikari-lightbulb), Python 3.14,
Postgres, SQLAlchemy 2.0, Alembic.

## Public instance

COMING SOON!

<!-- **[Invite coda-bot to your server](TODO-INVITE-URL)** -->

<!-- TODO: fill in invite URL, hosting region, uptime expectations, support server link,
     and who to contact for a manual data purge. -->

<!-- Run by the maintainer. See **[How it works, and what it stores](#how-it-works-and-what-it-stores)**
for more details. If you want to use the full functionality of the bot but don't want
to risk sending your logins to someone else, you might want to try
[self-hosting](#self-hosting) it. -->

## Commands

| Command                                            | What it does                                                                              |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `/register`                                        | Links your Arcaea account. Use a friend code (recommended) or an Arcaea login (optional). |
| `/unregister`                                      | Stop tracking your Arcaea account. Your stored plays are kept.                            |
| `/recent`                                          | Show your most recent play.                                                               |
| `/potential`                                       | Show the plays your potential is averaged from, and review any assumed clears.            |
| `/song`                                            | Look up a song, a chart, or browse by level or by CC.                                     |
| `/calc`                                            | Calculates the play rating for a score.                                                   |
| `/linkinfo`                                        | Explains what an Arcaea login link does, and why the link is optional.                    |
| `/unlink`                                          | Deletes your stored Arcaea login. Your scores continue to track through your friend code. |
| `/liveupdates` `allow` / `disallow`                | Allows or blocks live score updates in a channel. Admin only.                             |
| `/liveupdates` `channel`                           | Sets the destination for your live score updates.                                         |
| `/liveupdates` `on` / `off`                        | Starts or stops your live score updates.                                                  |
| `/liveupdates` `status`                            | Show where your live updates currently go.                                                |
| `/config` `user` / `channel` / `server`            | Scoped bot configuration.                                                                 |
| `/config` `view`                                   | Show the resolved config for this context.                                                |
| `/tracking` `on` / `off`                           | Starts or stops recording your plays. Owner only. Doesn't unregister or delete history.    |
| `/ping`                                            | Check if the bot is alive.                                                                |

Since friend codes are public data. If you claim a friend code that another person already
registered, coda-bot asks the current owner for approval. It sends this request
by direct message (DM) and will not accept the code without approval. Only a
login is real proof of account ownership.

## Status

This project is under active development.

- [x] Registration (`/register`) with both tiers: friend code and full login
- [x] Owner-approval flow for contested friend codes
- [x] Bot-account session pool against lowiro's private web API
- [x] Song/chart catalog with aliases and tags, plus a local web admin editor
- [x] Scoped settings system (`/config`)
- [x] Live-update configuration (`/liveupdates`)
- [x] Score polling and storage
- [x] Score-to-chart resolution, with a backfill pass for charts the catalog learns later
- [x] Recent play display (`/recent`) and play-rating maths (`/calc`)
- [x] Song and chart lookup (`/song`)
- [x] Live score posting to DMs or channels with filters
- [x] b50 / PTT tracking and display (works on both tiers)
- [x] Mini games (Chardle!)
- [ ] Reviewing the bot's clear-status guesses (friend-code tier)
- [ ] t0: manual score entry
- [ ] Profile / best-scores commands
- [ ] Tournament module
- [ ] Artist and charter lookup
- [ ] Context-menu commands

## How it works, and what it stores

### Tiers

Arcaea has no public API. coda-bot reads score through a player's own account.
It uses 2 methods, called tiers, plus a third, automatic tier for Arcaea Online
subscribers.

Additionally, manual score input just for b50 tracking is supported. This does not touch the API.

| Tier                          | How it reads                                                                                                                                                                                                                                                                                                                       | What it stores                                                                                                               |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| None                          | Nothing is read from Arcaea at all. Feeds b50 from what you type in.                                                                                                                                                                                                                                                                 | Only the song/chart and score values you type in. No friend code, no login, no in-game identity at all.                      |
| **Friend code** (default)     | One of the bot's dedicated in-game accounts friends you, and your recent plays are read off its friends list. No password. **Enough for ~90% of the bot** — tracking, live updates, b50, tournaments.                                                                                                                              | Your 9-digit friend code, in-game user id, display name, which bot account friended you, and every play the poller observes. |
| **Arcaea login** (optional)   | coda-bot logs in and requests scores on your behalf. This method returns more data: full note counts (pure, far, and lost notes), and the clear and gauge data. Only this tier knows whether a play cleared, so only it computes PTT exactly rather than from an estimate. Delete this link at any time with `/unlink`; your scores then continue to track through your friend code. | The above, plus your Arcaea **email and password**, the session cookie, and your Arcaea Online expiry.                       |
| **Arcaea Online** (automatic) | If your linked login has an active Arcaea Online subscription, coda-bot also reads your best scores, and lowiro's own play-rating numbers.                                                                                                                                                                                         | Same as above.                                                                                                               |

Discord side: your user id, your `/liveupdates` destination choice, and any `/config`
values you set. No message content is stored.

**Tracking can be switched off** anytime with `/tracking off` (per Arcaea account, owner
only) without unregistering — it stops new plays being recorded, but keeps everything
already stored and keeps `/recent` working. `/tracking on` resumes it.

### Credentials

Email and password are encrypted at rest with
[Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + HMAC) under a single
key held in the host's environment. The key is never stored in the database, never in the repo, no
rotation path.

coda-bot must store your password in a reversible form. This is necessary, not a
choice: lowiro's private API has no tokens, no OAuth function, and no refresh function.
When your session expires, coda-bot must send your real password again. Hashing function
cannot be used for this reason.

> [!warning]
> A person who holds both the database and the key can read your Arcaea password as
> plain text. For this reason, link your Arcaea login only on a host that you trust. The
> friend-code tier needs no password. The `/unlink` command deletes your stored
> credential permanently. coda-bot never logs passwords or any error
> details from credential-related code.

### Sessions

coda-bot stores sessions in a Postgres database. Each bot account sends
one fixed browser fingerprint. All values in this fingerprint stay consistent with each
other. This method protects the hand-made, unreplaceable bot accounts from
Cloudflare's automatic security checks. This method is not an attempt to hide
coda-bot's activity from lowiro.

### Data retention

**coda-bot keeps your plays on purpose.** Arcaea's API shows only your latest play.
Arcaea has no history function and no backfill function. For this reason, each stored
play is a single, unrepeatable record. If a stored play is deleted, coda-bot cannot get
that play again.

For this reason, the `/unregister` command does not delete your scores. The
`/unregister` command removes only your link. If your link is the account's last
active link, `/unregister` also deletes the stored credentials, ends the bot's friend
connection with you in the game, marks the account as inactive, and stops the poll
process for that account.

The account record and its plays remain in the database in all cases. If you register
the same friend code again, coda-bot reattaches the record to your new link. A
`RESTRICT` rule on the foreign key blocks any action that could delete this play
history through a linked record.

If another person is still linked to the same account, your `/unregister` command
removes only your link. Your `/unregister` command does not affect the other person's
link.

To delete your stored plays completely, contact the instance host. The host must purge
the records manually. coda-bot has no self-service function for permanent deletion
today.

### Unofficial, and ToS

**Unofficial.** coda-bot is not affiliated with, endorsed by, or supported by lowiro. It
reads an undocumented, private web API. lowiro can change or close this API at any
time. coda-bot uses the game's normal friend function to read this API. If you
self-host coda-bot, you are responsible for your use of coda-bot and for the accounts
that you connect to it.

**coda-bot breaks Arcaea's Terms of Service (ToS), for two reasons.**

Reason one: coda-bot reads data from `webapi.lowiro.com`. This web address is private
and undocumented. lowiro has not granted public access to this address.

Reason two: most such rules limit each person to one game account. coda-bot enforces
one Arcaea account per Discord user. However, the bot-account pool itself contains
several game accounts. One operator, the host, controls all these accounts to read
data for other people's friend lists. By the letter of most such rules, this is
multiple accounts under the control of one person, even though no single end user
holds multiple linked accounts.

These risks fall mainly on the host, for both reasons above. **If you host or use this
bot, you accept these risks.**

## Self-hosting

You'll need Python 3.14 + [`uv`](https://docs.astral.sh/uv/), Postgres, a Discord bot
token, and at least one Arcaea account to act as the bot's in-game account.

For the full guide, read **[self-hosting.md](self-hosting.md)**. This guide
covers the configuration reference, catalog seed procedures, bot-account setup, the
admin editor, and notes about the lowiro API layer.

## License

[MIT](LICENSE). Arcaea and its assets are the property of lowiro. This repo contains no
game art or song data.

## AI usage

Most of the code here was written by [Claude Code](https://claude.com/claude-code) under
human direction. The architecture, the domain decisions, the security trade-offs above and
the review of what landed are mine; the typing was largely not.

If you want to read or self-host coda-bot, note this: the design intent is recorded in three
places: `CLAUDE.md`, `CODING_STYLE.md`, and the `wiki/` directory. Humans and AI
models can both read these files. These files record the reason for each decision, and
usually give more detail than the code comments give. Treat the AI-written code here as
reviewed code, not as unsupervised code.
