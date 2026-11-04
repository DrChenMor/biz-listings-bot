"""The broker agent: runs the first approach to a broker, and nothing after it.

A person queues a business in the Deal desk app. The agent sends the enquiry, reads the reply, signs and returns a plain
NDA, files the documents that follow, and has them evaluated. Until AGENT_LIVE=yes it stays in test mode: forms are filled
but not sent, and no email leaves.
"""
import os


class AgentError(Exception):
    """Something a person needs to fix, in words they can act on."""


def is_live() -> bool:
    return os.environ.get("AGENT_LIVE", "").strip().lower() == "yes"
