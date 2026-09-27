#!/usr/bin/env python3
"""Where did the tokens go? Audit Claude Code session transcripts. Stdlib only.

    python3 audit.py                      # ~/.claude/projects, last 7 days
    python3 audit.py --days 30 --top 15
    python3 audit.py path/to/session.jsonl

Costs are list-price estimates (subscriptions don't bill per token, but limits track the same tokens).
"Context tax" = what a tool result costs after it arrives: written to the cache once, then re-read by
every later API call of that session. It is the number to shrink.
"""
import argparse, json, os, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

# $ per million tokens: input, output, cache write 5m, cache write 1h, cache read (platform.claude.com pricing, Sep 2026)
PRICES = {
    "opus-5-5": (4, 20, 5, 8, 0.20), "opus-5": (5, 25, 6.25, 10, 0.50), "opus-4": (5, 25, 6.25, 10, 0.50),
    "sonnet-5": (2, 10, 2.50, 4, 0.20), "sonnet-4": (3, 15, 3.75, 6, 0.30), "haiku-4-5": (1, 5, 1.25, 2, 0.10),
    "fable-5-1": (10, 50, 12.50, 20, 0.25), "mythos-5-1": (10, 50, 12.50, 20, 0.25),
}
CHARS_PER_TOKEN = 3.7
INSTALL = re.compile(r"\b(pip3?|npm|pnpm|yarn|cargo|apt(-get)?|brew|gem|go)\b.*\b(install|add|ci|get)\b")


def price(model):
    m = (model or "").removeprefix("claude-")
    return next((p for k, p in sorted(PRICES.items(), key=lambda kv: -len(kv[0])) if m.startswith(k)), PRICES["opus-5-5"])


def text_len(content):
    if isinstance(content, str):
        return len(content)
    return sum(len(c.get("text", "")) for c in content or [] if isinstance(c, dict))


def describe(name, inp):
    for key in ("command", "file_path", "pattern", "url", "query", "description", "prompt"):
        if key in inp:
            return re.sub(r"\s+", " ", str(inp[key]))[:70]
    return ""


def audit_file(path):
    calls, tools, results = {}, {}, []  # results: (tool_use_id, chars, call_index_when_seen)
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        msg = e.get("message") or {}
        if e.get("type") == "assistant":
            if msg.get("usage") and msg.get("model") != "<synthetic>":
                calls.setdefault(msg.get("id") or e.get("uuid"), (e.get("timestamp", ""), msg["model"], msg["usage"]))
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tools[c["id"]] = (c["name"], c.get("input") or {})
        elif e.get("type") == "user" and isinstance(msg.get("content"), list):
            for c in msg["content"]:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    results.append((c.get("tool_use_id"), text_len(c.get("content")), len(calls)))
    if not calls:
        return None
    s = {"file": str(path), "calls": len(calls), "cost": 0.0, "tok": Counter(), "cost_by": Counter(), "taxes": [],
         "models": Counter(), "first": min(v[0] for v in calls.values()), "max_ctx": 0}
    for ts, model, u in calls.values():
        p = price(model)
        cc = u.get("cache_creation") or {}
        w1h = cc.get("ephemeral_1h_input_tokens", 0)
        w5m = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0) - w1h)
        think = (u.get("output_tokens_details") or {}).get("thinking_tokens", 0)
        parts = {"input": u.get("input_tokens", 0) * p[0], "output (text+tools)": (u.get("output_tokens", 0) - think) * p[1],
                 "output (thinking)": think * p[1], "cache write": w5m * p[2] + w1h * p[3],
                 "cache read": u.get("cache_read_input_tokens", 0) * p[4]}
        for k, v in parts.items():
            s["cost_by"][k] += v / 1e6
        s["cost"] += sum(parts.values()) / 1e6
        s["tok"].update(output=u.get("output_tokens", 0), thinking=think, cache_read=u.get("cache_read_input_tokens", 0),
                        cache_write=w5m + w1h, input=u.get("input_tokens", 0))
        s["models"][model] += 1
        s["max_ctx"] = max(s["max_ctx"], u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0))
        s["write_price"] = p[3] if w1h >= w5m else p[2]
        s["read_price"] = p[4]
    n = len(calls)
    for tid, chars, seen_at in results:
        name, inp = tools.get(tid, ("?", {}))
        tokens = chars / CHARS_PER_TOKEN
        rides = max(0, n - seen_at - 1)  # later calls that re-read it
        tax = tokens * (s["write_price"] + rides * s["read_price"]) / 1e6
        s["taxes"].append({"tool": name, "what": describe(name, inp), "tokens": int(tokens), "rides": rides, "tax": tax,
                           "full_read": name == "Read" and "limit" not in inp and tokens > 8000,
                           "install": name == "Bash" and bool(INSTALL.search(str(inp.get("command", "")))) and tokens > 1500,
                           "path": inp.get("file_path") if name == "Read" else None})
    s["reread"] = sum(c - 1 for c in Counter(t["path"] for t in s["taxes"] if t["path"]).values() if c > 1)
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
    files = [Path(p) for p in a.paths] or [f for f in root.rglob("*.jsonl") if f.stat().st_mtime > time.time() - a.days * 86400]
    files = [f for p in files for f in ([p] if p.is_file() else sorted(p.rglob("*.jsonl")))]
    sessions = [s for s in map(audit_file, files) if s]
    if not sessions:
        sys.exit(f"no transcripts with usage found ({root})")
    total = sum(s["cost"] for s in sessions)
    by, tok = Counter(), Counter()
    for s in sessions:
        by.update(s["cost_by"]); tok.update(s["tok"])
    taxes = [dict(t, session=Path(s["file"]).stem[:8]) for s in sessions for t in s["taxes"]]
    tax_total = sum(t["tax"] for t in taxes)
    print(f"{len(sessions)} transcripts, {sum(s['calls'] for s in sessions)} API calls, est. ${total:.2f} at list price\n")
    print("Cost by token type:")
    for k, v in by.most_common():
        print(f"  {k:22} ${v:8.2f}  {v / total:5.1%}")
    print(f"  thinking = {tok['thinking'] / max(1, tok['output']):.0%} of output tokens; "
          f"tool results carry ~${tax_total:.2f} ({tax_total / total:.0%}) as context tax\n")
    per_tool = defaultdict(lambda: [0, 0, 0.0])
    for t in taxes:
        per_tool[t["tool"]][0] += 1; per_tool[t["tool"]][1] += t["tokens"]; per_tool[t["tool"]][2] += t["tax"]
    print("Context tax by tool:            calls   ~tokens      tax")
    for name, (c, tk, tx) in sorted(per_tool.items(), key=lambda kv: -kv[1][2])[:8]:
        print(f"  {name:28} {c:6} {tk:9,} ${tx:8.2f}")
    print(f"\nTop {a.top} tool results by context tax:")
    for t in sorted(taxes, key=lambda t: -t["tax"])[:a.top]:
        print(f"  ${t['tax']:6.3f} {t['tokens']:7,} tok x{t['rides']:<3} {t['tool']:6} {t['what']}  [{t['session']}]")
    flags = {"Read of a whole large file (>8k tokens, no limit)": [t for t in taxes if t["full_read"]],
             "Noisy install output (>1.5k tokens)": [t for t in taxes if t["install"]]}
    print("\nPatterns:")
    for label, ts in flags.items():
        print(f"  {label:52} {len(ts):4}x  ${sum(t['tax'] for t in ts):.2f}")
    print(f"  {'Same file read again in a session':52} {sum(s['reread'] for s in sessions):4}x")
    print("\nMost expensive sessions:")
    for s in sorted(sessions, key=lambda s: -s["cost"])[:5]:
        model = s["models"].most_common(1)[0][0]
        print(f"  ${s['cost']:7.2f} {s['calls']:4} calls, max context {s['max_ctx']:,} tok, {model}  {s['first'][:16]}  {Path(s['file']).parent.name[-40:]}")


if __name__ == "__main__":
    main()
