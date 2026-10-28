"""robots.txt rules, following the standard (RFC 9309).

Written by hand because Python's urllib.robotparser ignores the * and $ wildcards that
real sites use, e.g. kumarijob's "Disallow: /jobseeker*" or Gurzu's "Disallow: /*?*".

How a URL is decided:
1. Use the group for our product token ("Lakshya") if there is one, else the "*" group.
2. Of the rules whose pattern matches the URL's path, the longest pattern wins.
3. On a tie, Allow wins. If no rule matches, the URL is allowed.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str  # as written in robots.txt, e.g. "/jobseeker*"
    regex: re.Pattern


@dataclass(frozen=True)
class RobotsRules:
    rules: tuple[Rule, ...] = ()
    crawl_delay: float | None = None

    def allows(self, url: str) -> bool:
        target = _path_and_query(url)
        best: Rule | None = None
        for rule in self.rules:
            if rule.regex.match(target) and (
                best is None or (len(rule.pattern), rule.allow) > (len(best.pattern), best.allow)
            ):
                best = rule
        return best is None or best.allow


ALLOW_ALL = RobotsRules()


def disallow_all() -> RobotsRules:
    return RobotsRules((_rule(allow=False, pattern="/"),))


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def parse_robots(text: str, user_agent: str) -> RobotsRules:
    """The rules that apply to `user_agent` (e.g. "Lakshya/0.1 (...)") in a robots.txt file."""
    groups: list[_Group] = []
    current: _Group | None = None
    in_rules = False  # a user-agent line after rule lines starts a new group

    for line in text.splitlines():
        key, _, value = line.split("#", 1)[0].partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if current is None or in_rules:
                current = _Group()
                groups.append(current)
                in_rules = False
            current.agents.append(value.lower())
        elif key in ("allow", "disallow") and current is not None:
            in_rules = True
            if value:  # an empty "Disallow:" means nothing is disallowed
                current.rules.append(_rule(allow=key == "allow", pattern=value))
        elif key == "crawl-delay" and current is not None:
            in_rules = True
            try:
                current.crawl_delay = float(value)
            except ValueError:
                pass
        # Other lines (Sitemap, Host, Content-Signal, ...) don't affect what we may fetch

    token = user_agent.split("/")[0].strip().lower()  # "Lakshya/0.1 (...)" -> "lakshya"
    chosen = [g for g in groups if token in g.agents] or [g for g in groups if "*" in g.agents]
    delays = [g.crawl_delay for g in chosen if g.crawl_delay is not None]
    return RobotsRules(
        rules=tuple(rule for group in chosen for rule in group.rules),
        crawl_delay=max(delays) if delays else None,
    )


def _rule(allow: bool, pattern: str) -> Rule:
    # "*" matches any characters; a trailing "$" anchors the end; everything else is literal
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*")) + ("$" if anchored else "")
    return Rule(allow, pattern, re.compile(regex))


def _path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
