"""Registration failures, phrased as things a user or an admin can act on."""

from __future__ import annotations


class RegistrationError(Exception):
    """Base for registration failures."""


class PlayerUnreachable(RegistrationError):
    """No such player -- the code is well-formed but lowiro does not know it.

    Distinct from an invalid *shape* (which never reaches the network) and from
    an account problem. Trying another bot account would be pointless: every
    account returns 401 for the same code.
    """


class AmbiguousFriend(RegistrationError):
    """Could not tell which friend is the new one -- needs a human.

    Raised when a 602 recovery finds zero or several unknown friends on the
    account. Guessing here would attribute a stranger's scores to a Discord
    user, so the code refuses rather than picking.
    """


class AlreadyRegistered(RegistrationError):
    """This Discord user already has this Arcaea account linked."""


class AlreadyLinkedElsewhere(RegistrationError):
    """This Discord user is already linked to a *different* Arcaea account.

    One account per Discord user, and no switching: changing accounts means
    ``/unregister`` first. Carries the current account's identity so the message
    can name it. Raised before any friend slot is consumed.
    """

    def __init__(self, friend_code: str, display_name: str | None) -> None:
        self.friend_code = friend_code
        self.display_name = display_name
        super().__init__(f"already linked to {friend_code}")


class ReservedCodeError(RegistrationError):
    """A well-formed code that must not be registered (see ``reserved.py``).

    Carries its own user-facing message, because the useful thing to say differs
    per code -- an easter egg and the owner's code are refused for unrelated
    reasons.
    """

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        self.user_message = message
        super().__init__(f"reserved friend code ({reason})")


class AccountClaimed(RegistrationError):
    """The account's owner was asked to approve a second link, and said **no**.

    Narrowed from its original meaning (a blanket refusal of any second claim).
    The blanket refusal is gone: a code claim on an owned account now asks the
    owner via the durable approval flow (``coda.approvals`` + the ``link_approval``
    handler) rather than refusing on sight, because a public friend code can be an
    alt of the owner as easily as a stranger, and only the owner can tell them
    apart. This exception is the *denied* outcome of that ask -- the owner is the
    one person entitled to make the call, and they declined.
    """

    def __init__(self, friend_code: str, claimed_by: int) -> None:
        self.friend_code = friend_code
        self.claimed_by = claimed_by
        super().__init__(f"{friend_code} link to {claimed_by} was denied by the owner")
