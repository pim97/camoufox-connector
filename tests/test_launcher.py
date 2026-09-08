"""The generated launcher source must never let a config string inject code."""

from __future__ import annotations

from conftest import make_pool


def test_launcher_repr_quotes_proxy_and_stays_valid_python():
    pool = make_pool(n=1)
    # A malicious payload that would break out of a naive '{value}' wrapping and
    # execute code. We call the generator directly (bypassing Settings validation)
    # to prove the launcher itself is safe even if such a string reached it.
    payload = "http://x'); import os; os.system('PWNED'); ('"
    script = pool._generate_launcher_script(9222, payload)

    # 1) The generated source must be syntactically valid: the payload did NOT
    #    break out of its string literal.
    compile(script, "<launcher>", "exec")

    # 2) The payload is carried as a repr()-escaped string literal, not code.
    assert repr(payload) in script
    # The dangerous sequence never appears as bare, executable source.
    assert "; import os; os.system('PWNED')" not in script.replace(repr(payload), "")


def test_launcher_normal_proxy_is_present():
    pool = make_pool(n=1)
    script = pool._generate_launcher_script(9222, "http://user:pass@host:8080")
    assert "proxy=" in script
    assert repr("http://user:pass@host:8080") in script


def test_launcher_keeps_config_pipe_open():
    pool = make_pool(n=1)
    script = pool._generate_launcher_script(9222)

    assert 'base64.b64encode(data).decode() + "\\n"' in script
    assert "process.stdin.close()" not in script
