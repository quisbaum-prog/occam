"""Procedural benchmark scenarios. Stdlib only.

Each scenario is `make(seed, ws) -> Task`: it writes a workspace into `ws` (a fresh directory)
and returns the user prompt plus a hidden `verify(ws, final_text, py) -> {"pass", "score", "notes"}`.
Same seed -> byte-identical workspace, so every arm gets exactly the same task.
"""
import ast, csv, io, json, random, re, socket, struct, subprocess, sys, time, zlib
from collections import namedtuple
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

Task = namedtuple("Task", "prompt verify")
SCENARIOS = {}


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


def tpl(text, **kw):
    """Fill @key@ placeholders (code templates are full of braces, so no str.format)."""
    for k, v in kw.items():
        text = text.replace(f"@{k}@", str(v))
    return text


def put(ws, rel, text):
    p = Path(ws) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def run(cmd, cwd, timeout=120, env=None, stdin=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env, input=stdin)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -9, "", "timeout"


CHECK_RUNNER = r'''
import json, sys
sys.path.insert(0, ".")
res = {}
def check(name, fn):
    try:
        res[name] = bool(fn())
    except BaseException as e:
        res[name] = False
        res["!" + name] = repr(e)[:160]
@BODY@
print(json.dumps(res))
'''


def run_checks(py, ws, body, timeout=120):
    """Execute check(...) calls with the agent's interpreter inside the workspace."""
    rc, out, err = run([py, "-c", tpl(CHECK_RUNNER, BODY=body)], ws, timeout)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"harness": False, "!harness": (err or out)[-300:]}


def verdict(res, extra_notes=""):
    names = [k for k in res if not k.startswith("!")]
    ok = [k for k in names if res[k]]
    failed = [k for k in names if not res[k]]
    notes = "; ".join([f"FAIL {k} {res.get('!' + k, '')}".strip() for k in failed] + ([extra_notes] if extra_notes else []))
    return {"pass": bool(names) and not failed, "score": round(len(ok) / max(1, len(names)), 3), "notes": notes[:600]}


def unittest_ok(py, ws, args=("-m", "unittest", "-q")):
    rc, out, err = run([py, *args], ws, 300)
    return rc == 0 and "Ran 0 tests" not in err


# ---------------------------------------------------------------- shared codebase (rootcause, question)

PKGS = ["ledger", "billing", "tally", "bookkeep", "invoicer"]
TOPICS = ["customers", "products", "tax", "shipping", "notifications", "audit", "discounts", "inventory",
          "suppliers", "payments", "exports", "scheduling", "users", "permissions", "search", "metrics",
          "webhooks", "archive", "vouchers", "contracts"]

FILLER = [
    '''def @p@_find(records, key):
    """Return the @e@ with the given id, or None."""
    for r in records:
        if r.get("id") == key:
            return r
    return None
''',
    '''def @p@_active(records):
    """Only @e@ records that are neither archived nor blocked."""
    return [r for r in records if not r.get("archived") and not r.get("blocked")]
''',
    '''def @p@_summary(records):
    """Count @e@ records per status."""
    counts = {}
    for r in records:
        counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1
    return counts
''',
    '''def @p@_total(records):
    """Sum the '@k@' field of all @e@ records, formatted for display."""
    total = Decimal("0")
    for r in records:
        total += Decimal(str(r.get("@k@", 0)))
    return format_amount(total)
''',
    '''def @p@_validate(record):
    """Raise ValueError if a @e@ record misses required fields."""
    missing = [f for f in ("id", "@k@", "created") if f not in record]
    if missing:
        raise ValueError("@e@ record misses " + ", ".join(missing))
    if len(str(record["id"])) > @n@:
        raise ValueError("@e@ id too long")
    return record
''',
    '''def @p@_sorted(records, newest_first=True):
    """Sort @e@ records by creation date."""
    return sorted(records, key=lambda r: r.get("created", ""), reverse=newest_first)
''',
    '''def @p@_page(records, page, size=@n@):
    """Return one page of @e@ records (pages start at 1)."""
    if page < 1:
        raise ValueError("page starts at 1")
    start = (page - 1) * size
    return records[start:start + size]
''',
    '''def @p@_group(records, field="@k@"):
    """Group @e@ records by a field value."""
    groups = {}
    for r in records:
        groups.setdefault(r.get(field), []).append(r)
    return groups
''',
    '''def @p@_row(record):
    """Flatten a @e@ record for CSV export."""
    return (record.get("id"), record.get("@k@"), record.get("status", ""), record.get("created", "")[:10])
''',
    '''def @p@_merge(old, new):
    """Merge updated fields into a @e@ record, never overwriting the id."""
    merged = dict(old)
    for k, v in new.items():
        if k != "id" and v is not None:
            merged[k] = v
    return merged
''',
    '''def @p@_changed(before, after):
    """Names of fields that differ between two versions of a @e@ record."""
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))
''',
    '''def @p@_over_limit(records, limit=@n@):
    """True if more than `limit` @e@ records are open."""
    return sum(1 for r in records if r.get("status") == "open") > limit
''',
]

MONEY = '''"""Money helpers shared across @pkg@."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def parse_amount(text):
    """Parse an amount such as '12.50', '12,50' or '-3' into a Decimal with two places."""
    s = str(text).strip().replace(",", ".")
    return Decimal(s).quantize(CENT, ROUND_HALF_UP)


def format_amount(value):
    """Format a number for display, e.g. Decimal('3.5') -> '3.50'."""
    return f"{Decimal(value).quantize(CENT, ROUND_HALF_UP):.2f}"
'''

INVOICE = '''"""Invoice totals. Line prices arrive as text from the nightly import."""
from decimal import Decimal
from .money import parse_amount


def invoice_total(lines):
    """Sum qty * price over the invoice lines."""
    total = Decimal("0.00")
    for line in lines:
        total += int(line["qty"]) * parse_amount(line["price"])
    return total
'''

REFUNDS = '''"""Refund requests."""
from decimal import Decimal
from .money import parse_amount

MAX_REFUND = Decimal("5000.00")


def refund_amount(request):
    """Validated refund amount of a request."""
    amount = parse_amount(request["amount"])
    if amount > MAX_REFUND:
        raise ValueError("refund exceeds limit")
    return amount
'''

REPORTS = '''"""Category reports."""
from collections import defaultdict
from decimal import Decimal
from .money import parse_amount


def category_totals(entries):
    """Total amount per category."""
    totals = defaultdict(Decimal)
    for e in entries:
        totals[e["category"]] += parse_amount(e["amount"])
    return dict(totals)
'''

IMPORTER = '''"""Import of bank transaction exports ('date;account;amount' per line)."""
import csv
import io
from decimal import Decimal


def _to_decimal(cell):
    # local helper, older than money.parse_amount
    return Decimal(cell.strip().replace(",", ".")).quantize(Decimal("0.01"))


def import_rows(text):
    """Parse the export into (date, account, Decimal amount) tuples."""
    rows = []
    for rec in csv.reader(io.StringIO(text), delimiter=";"):
        if not rec or rec[0].startswith("#"):
            continue
        day, account, amount = rec
        rows.append((day, account, _to_decimal(amount)))
    return rows
'''

FEES = '''"""@title@ for overdue invoices."""
from decimal import Decimal, ROUND_HALF_UP

LATE_FEE_RATE = Decimal("@rate@")  # per started month overdue
GRACE_DAYS = @grace@


def @fn@(amount, days_late):
    """Amount plus late fee: LATE_FEE_RATE per started month after GRACE_DAYS."""
    if days_late <= GRACE_DAYS:
        return amount
    months = -(-(days_late - GRACE_DAYS) // 30)
    return (amount * (1 + LATE_FEE_RATE * months)).quantize(Decimal("0.01"), ROUND_HALF_UP)
'''

MONEY_TESTS = '''import unittest
from decimal import Decimal

from @pkg@.money import format_amount, parse_amount


class MoneyTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_amount("12.50"), Decimal("12.50"))

    def test_decimal_comma(self):
        self.assertEqual(parse_amount("12,50"), Decimal("12.50"))

    def test_negative(self):
        self.assertEqual(parse_amount("-3"), Decimal("-3.00"))

    def test_whitespace(self):
        self.assertEqual(parse_amount(" 7 "), Decimal("7.00"))

    def test_format(self):
        self.assertEqual(format_amount(Decimal("3.5")), "3.50")


if __name__ == "__main__":
    unittest.main()
'''

# Bug variants: values that crash parse_amount, and the checks a real fix must pass.
BUGS = {
    "thousands": {
        "log_values": ["1,234.50", "12.345,00", "1,204,330.10"],
        "parse": {"1,234.50": "1234.50", "12.345,00": "12345.00", "1,204,330.10": "1204330.10", "2.000.000,00": "2000000.00"},
        "invoice": ([("2", "1,234.50"), ("1", "10,00")], "2479.00"),
        "refund": ("1,234.50", "1234.50"),
        "importer": ("2026-09-01;ACC-1;1,204,330.10\n2026-09-02;ACC-2;12,50\n", ["1204330.10", "12.50"]),
        "report": (["1.234,50", "0,50"], "1235.00"),
    },
    "currency": {
        "log_values": ["€ 1234.50", "89.90 EUR", "$12"],
        "parse": {"€ 1234.50": "1234.50", "89.90 EUR": "89.90", "$12": "12.00", "EUR 5,50": "5.50", "12.50 €": "12.50"},
        "invoice": ([("2", "€ 10.25"), ("1", "89.90 EUR")], "110.40"),
        "refund": ("$12", "12.00"),
        "importer": ("2026-09-01;ACC-1;€ 1234.50\n2026-09-02;ACC-2;12,50\n", ["1234.50", "12.50"]),
        "report": (["EUR 5,50", "$1"], "6.50"),
    },
    "parens": {
        "log_values": ["(45.00)", "(1234,5)", "(0.99)"],
        "parse": {"(45.00)": "-45.00", "(1234,5)": "-1234.50", "(0.99)": "-0.99", "(7)": "-7.00"},
        "invoice": ([("1", "100.00"), ("1", "(45.00)")], "55.00"),
        "refund": ("45.00", "45.00"),
        "importer": ("2026-09-01;ACC-1;(1234,5)\n2026-09-02;ACC-2;12,50\n", ["-1234.50", "12.50"]),
        "report": (["(0.99)", "1"], "0.01"),
    },
}

LOG_LINES = [
    'INFO @pkg@.api: GET /api/invoices/@id@ 200 @ms@ms',
    'INFO @pkg@.api: GET /api/customers/@id@ 200 @ms@ms',
    'INFO @pkg@.api: POST /api/payments 201 @ms@ms',
    'DEBUG @pkg@.cache: hit ratio 0.@n@',
    'INFO @pkg@.auth: user u@id@ logged in',
    'INFO @pkg@.jobs: job sync-@n@ finished in @ms@ms',
    'WARNING @pkg@.webhooks: retrying webhook wh-@id@ (attempt @d@)',
    'INFO @pkg@.notifications: sent reminder r-@id@',
    'DEBUG @pkg@.db: pool size @d@, waiting 0',
]


def _line_of(src, needle):
    return next(i for i, l in enumerate(src.splitlines(), 1) if needle in l)


def _traceback(pkg, frames, value):
    out = ["Traceback (most recent call last):"]
    for mod, src, func, needle in frames:
        out += [f'  File "{pkg}/{mod}.py", line {_line_of(src, needle)}, in {func}', f"    {needle.strip()}"]
    out.append("decimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]")
    return out


def _codebase(seed, ws):
    """Shared generated package. Returns facts the scenarios need."""
    rng = random.Random(seed)
    pkg = rng.choice(PKGS)
    bug = ["thousands", "currency", "parens"][seed % 3]
    fee_mod, fee_title = rng.choice([("fees", "Fee rules"), ("dunning", "Dunning rules"), ("overdue", "Overdue handling")])
    fee_fn = rng.choice(["apply_late_fee", "add_overdue_charge", "late_payment_surcharge"])
    rate = rng.choice(["0.025", "0.03", "0.035", "0.04", "0.045"])
    core = {"money": tpl(MONEY, pkg=pkg), "invoice": INVOICE, "refunds": REFUNDS, "reports": REPORTS,
            "importer": IMPORTER, fee_mod: tpl(FEES, title=fee_title, rate=rate, grace=rng.choice([7, 10, 14]), fn=fee_fn)}
    put(ws, f"{pkg}/__init__.py", "")
    for mod, src in core.items():
        put(ws, f"{pkg}/{mod}.py", src)
    for topic in rng.sample(TOPICS, rng.randint(14, 18)):
        ent = topic.rstrip("s")
        consts = "\n".join(f"{topic.upper()}_{name} = {rng.randint(3, 500)}"
                           for name in rng.sample(["LIMIT", "BATCH", "TTL", "RETRIES", "PAGE", "WINDOW"], 3))
        funcs = [tpl(f, p=topic, e=ent, k=rng.choice(["amount", "total", "value", "price"]), n=rng.randint(5, 90))
                 for f in rng.sample(FILLER, rng.randint(7, 11))]
        put(ws, f"{pkg}/{topic}.py", f'"""{topic.capitalize()} helpers."""\nfrom decimal import Decimal\n\n'
            f"from .money import format_amount\n\n{consts}\n\n\n" + "\n\n".join(funcs))
    put(ws, "tests/__init__.py", "")
    put(ws, "tests/test_money.py", tpl(MONEY_TESTS, pkg=pkg))
    put(ws, "README.md", f"# {pkg}\n\nInternal accounting helpers.\n\nTests: `python -m unittest`\n")
    # A large application log with a few planted failures near the end ("since the last import").
    vals = BUGS[bug]["log_values"]
    inv_tb = _traceback(pkg, [("invoice", INVOICE, "invoice_total", '        total += int(line["qty"]) * parse_amount(line["price"])'),
                              ("money", core["money"], "parse_amount", "    return Decimal(s).quantize(CENT, ROUND_HALF_UP)")], None)
    imp_tb = _traceback(pkg, [("importer", IMPORTER, "import_rows", "        rows.append((day, account, _to_decimal(amount)))"),
                              ("importer", IMPORTER, "_to_decimal", '    return Decimal(cell.strip().replace(",", ".")).quantize(Decimal("0.01"))')], None)
    n = 42000
    planted = {int(n * f): i for i, f in enumerate([0.78, 0.83, 0.88, 0.93, 0.97])}
    t, lines = 1788000000 + seed * 977, []
    for i in range(n):
        t += rng.randint(0, 3)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t)) + f",{rng.randint(0, 999):03d}"
        if i in planted:
            k = planted[i]
            if k in (1, 3):
                lines += [f"{stamp} ERROR {pkg}.importer: import failed for batch B-{rng.randint(1000, 9999)}", *imp_tb,
                          f"{stamp} WARNING {pkg}.importer: offending value: {vals[k % len(vals)]!r}"]
            else:
                lines += [f"{stamp} ERROR {pkg}.invoice: failed to compute total for invoice INV-{rng.randint(10000, 99999)}", *inv_tb,
                          f"{stamp} WARNING {pkg}.invoice: offending value: {vals[k % len(vals)]!r}"]
        else:
            lines.append(stamp + " " + tpl(rng.choice(LOG_LINES), pkg=pkg, id=rng.randint(1000, 99999),
                                           ms=rng.randint(2, 900), n=rng.randint(10, 99), d=rng.randint(1, 5)))
    put(ws, "logs/app.log", "\n".join(lines) + "\n")
    return {"pkg": pkg, "bug": bug, "fee_mod": fee_mod, "fee_fn": fee_fn, "rate": rate}


@scenario
def rootcause(seed, ws):
    f = _codebase(seed, ws)
    pkg, b = f["pkg"], BUGS[f["bug"]]

    def verify(ws, final, py):
        D = "Decimal"
        body = [f"from decimal import Decimal",
                f"from {pkg}.money import parse_amount",
                f"from {pkg}.invoice import invoice_total",
                f"from {pkg}.refunds import refund_amount",
                f"from {pkg}.importer import import_rows",
                f"from {pkg}.reports import category_totals"]
        for raw, exp in {**b["parse"], "12.50": "12.50", "12,50": "12.50", "-3": "-3.00", " 7 ": "7.00"}.items():
            body.append(f"check('parse {raw}', lambda: parse_amount({raw!r}) == {D}({exp!r}))")
        lines = [{"qty": q, "price": p} for q, p in b["invoice"][0]]
        body.append(f"check('invoice', lambda: invoice_total({lines!r}) == {D}({b['invoice'][1]!r}))")
        body.append(f"check('refund', lambda: refund_amount({{'amount': {b['refund'][0]!r}}}) == {D}({b['refund'][1]!r}))")
        body.append(f"check('importer', lambda: [r[2] for r in import_rows({b['importer'][0]!r})] == [{D}(x) for x in {b['importer'][1]!r}])")
        entries = [{"category": "a", "amount": a} for a in b["report"][0]]
        body.append(f"check('report', lambda: category_totals({entries!r}) == {{'a': {D}({b['report'][1]!r})}})")
        res = run_checks(py, ws, "\n".join(body))
        res["existing tests"] = unittest_ok(py, ws)
        return verdict(res)

    return Task("Since the last import some customers' invoices fail (see logs/app.log). Please fix it.", verify)


@scenario
def question(seed, ws):
    f = _codebase(seed, ws)
    pct = f"{Decimal(f['rate']) * 100:g}"

    def verify(ws, final, py):
        rate_ok = re.search(rf"(?<![\d.]){re.escape(f['rate'])}(?!\d)|(?<![\d.]){re.escape(pct)}(?:[.,]0)?\s?%", final or "")
        return verdict({"function named": f["fee_fn"] in (final or ""), "rate stated": bool(rate_ok)})

    return Task("Quick question: which function applies the late-payment fee, and what rate does it use?", verify)


# ---------------------------------------------------------------- feature: CLI with over-build room

TODO = '''#!/usr/bin/env python3
"""Tiny todo manager. Items live in todo.json next to this file (override with TODO_FILE)."""
import argparse
import json
import os
import sys
from pathlib import Path

DB = Path(os.environ.get("TODO_FILE", Path(__file__).with_name("todo.json")))


def load():
    return json.loads(DB.read_text()) if DB.exists() else []


def save(items):
    DB.write_text(json.dumps(items, indent=2))


def cmd_add(args):
    items = load()
    item = {"id": max((i["id"] for i in items), default=0) + 1, "title": args.title, "done": False}
    items.append(item)
    save(items)
    print(f"added #{item['id']}")


def cmd_list(args):
    items = load()
    if not args.all:
        items = [i for i in items if not i["done"]]
    for i in items:
        mark = "x" if i["done"] else " "
        print(f"[{mark}] {i['id']:>3}  {i['title']}")


def cmd_done(args):
    items = load()
    for i in items:
        if i["id"] == args.id:
            i["done"] = True
            save(items)
            print(f"done #{args.id}")
            return
    sys.exit(f"no item #{args.id}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="todo")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("title")
    a.set_defaults(func=cmd_add)
    ls = sub.add_parser("list")
    ls.add_argument("--all", action="store_true")
    ls.set_defaults(func=cmd_list)
    d = sub.add_parser("done")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_done)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
'''

TODO_TESTS = '''import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TODO = Path(__file__).resolve().parent.parent / "todo.py"


def todo(*args, db):
    env = dict(os.environ, TODO_FILE=db)
    return subprocess.run([sys.executable, str(TODO), *args], capture_output=True, text=True, env=env)


class TodoTest(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "todo.json")

    def test_add_list_done(self):
        todo("add", "buy milk", db=self.db)
        todo("add", "call bob", db=self.db)
        todo("done", "1", db=self.db)
        out = todo("list", db=self.db).stdout
        self.assertNotIn("buy milk", out)
        self.assertIn("call bob", out)
        self.assertIn("buy milk", todo("list", "--all", db=self.db).stdout)

    def test_done_unknown(self):
        self.assertNotEqual(todo("done", "9", db=self.db).returncode, 0)


if __name__ == "__main__":
    unittest.main()
'''

FEATURE_PROMPTS = [
    "Add due dates to todo.py: `add` takes an optional `--due YYYY-MM-DD`, `list --overdue` shows only open items "
    "whose due date is before today, and `list --format json` prints the items as JSON (default output stays as it is).",
    "Add tags to todo.py: `add` accepts `--tag NAME` (repeatable), `list --tag NAME` shows only items with that tag "
    "(case-insensitive), and `list --format csv` prints id,title,done,tags as CSV with a header row (default output stays as it is).",
]


@scenario
def feature(seed, ws):
    variant = seed % 2
    put(ws, "todo.py", TODO)
    put(ws, "tests/__init__.py", "")
    put(ws, "tests/test_todo.py", TODO_TESTS)
    put(ws, "README.md", "# todo\n\n`python todo.py add|list|done`. Tests: `python -m unittest`\n")

    def verify(ws, final, py):
        import os, tempfile
        db = os.path.join(tempfile.mkdtemp(), "t.json")
        env = dict(os.environ, TODO_FILE=db)

        def t(*a):
            return run([py, "todo.py", *a], ws, 60, env)

        res = {}
        if variant == 0:
            t("add", "alpha", "--due", "2001-01-01"); t("add", "beta", "--due", "2099-12-31"); t("add", "gamma")
            rc, out, _ = t("list", "--overdue")
            res["overdue filter"] = rc == 0 and "alpha" in out and "beta" not in out and "gamma" not in out
            rc, out, _ = t("list", "--format", "json")
            try:
                data = json.loads(out)
                data = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
                by = {d["title"]: d for d in data}
                res["json output"] = set(by) == {"alpha", "beta", "gamma"} and by["alpha"].get("due") == "2001-01-01" and not by["gamma"].get("due")
            except Exception:
                res["json output"] = False
            rc, _, _ = t("add", "bad", "--due", "2024-13-45")
            rc2, out2, _ = t("list", "--all")
            res["invalid date rejected"] = rc != 0 and "bad" not in out2
            rc, out, _ = t("list")
            res["default list"] = rc == 0 and all(x in out for x in ("alpha", "beta", "gamma")) and "[ ]" in out
            t("done", "1")
            rc, out, _ = t("list", "--overdue")
            res["done not overdue"] = rc == 0 and "alpha" not in out
        else:
            t("add", "alpha", "--tag", "Work", "--tag", "urgent"); t("add", "beta", "--tag", "home"); t("add", "gamma, with comma")
            rc, out, _ = t("list", "--tag", "work")
            res["tag filter"] = rc == 0 and "alpha" in out and "beta" not in out and "gamma" not in out
            rc, out, _ = t("list", "--format", "csv")
            try:
                rows = list(csv.reader(io.StringIO(out)))
                head = [h.strip().lower() for h in rows[0]]
                recs = {r[head.index("title")]: r for r in rows[1:] if r}
                tags = recs["alpha"][head.index("tags")]
                res["csv output"] = head[:4] == ["id", "title", "done", "tags"] and "gamma, with comma" in recs and "Work" in tags and "urgent" in tags
            except Exception:
                res["csv output"] = False
            rc, out, _ = t("list")
            res["default list"] = rc == 0 and all(x in out for x in ("alpha", "beta", "gamma")) and "[ ]" in out
        res["existing tests"] = unittest_ok(py, ws)
        return verdict(res)

    return Task(FEATURE_PROMPTS[variant], verify)


# ---------------------------------------------------------------- data: big CSV, don't dump it

ADJ = ["Aero", "Nova", "Terra", "Lumen", "Pixel", "Vivo", "Orbit", "Zen", "Flux", "Nord", "Sol", "Echo"]
NOUN = ["Kettle", "Lamp", "Desk", "Chair", "Router", "Blender", "Speaker", "Monitor", "Drill", "Backpack", "Watch", "Mug"]
REGIONS = ["North", "South", "East", "West", "Central", "Alpine", "Coastal", "Metro"]


def _sales_truth(rows):
    seen, bad, rev, prod = set(), 0, {}, {}
    for r in rows:
        try:
            if len(r) != 8:
                raise ValueError
            oid, day, region, product, qty, price, disc, status = r
            d, q, p, di = date.fromisoformat(day), int(qty), float(price), float(disc)
            if q < 0 or p < 0:
                raise ValueError
        except ValueError:
            bad += 1
            continue
        if oid in seen:
            continue
        seen.add(oid)
        if d.year == 2025 and status == "paid":
            net = q * p * (1 - di)
            rev[region] = rev.get(region, 0) + net
            prod[product] = prod.get(product, 0) + net
    top = sorted(prod, key=prod.get, reverse=True)[:3]
    return {k: round(v, 2) for k, v in rev.items()}, top, bad


@scenario
def data(seed, ws):
    rng = random.Random(seed)
    regions = rng.sample(REGIONS, 5)
    products = [f"{a} {n}" for a, n in rng.sample([(a, n) for a in ADJ for n in NOUN], 24)]
    weights = [rng.uniform(0.3, 3) for _ in products]
    rows, start = [], date(2024, 1, 1)
    for i in range(55000 + seed % 7 * 2000):
        rows.append([f"O{100000 + i}", (start + timedelta(days=rng.randrange(731))).isoformat(), rng.choice(regions),
                     rng.choices(products, weights)[0], str(rng.randint(1, 20)), f"{rng.uniform(2.5, 499.99):.2f}",
                     rng.choice(["0", "0.05", "0.1", "0.15", "0.2", "0.25", "0.3"]),
                     rng.choices(["paid", "refunded", "cancelled"], [85, 8, 7])[0]])
    for k in range(len(rows) // 140):  # malformed rows, unique ids
        r = list(rng.choice(rows)); r[0] = f"O9{k:05d}"
        kind = k % 6
        if kind == 0: r = r[:-1]
        elif kind == 1: r[4] = "N/A"
        elif kind == 2: r[5] = ""
        elif kind == 3: r[4] = str(-rng.randint(1, 5))
        elif kind == 4: r[1] = "2025-02-30"
        else: r = r + ["extra"]
        rows.insert(rng.randrange(len(rows)), r)
    for _ in range(len(rows) // 100):  # exact duplicates, always after the original
        i = rng.randrange(len(rows) - 1)
        rows.insert(rng.randrange(i + 1, len(rows)), list(rows[i]))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["order_id", "date", "region", "product", "qty", "unit_price", "discount", "status"])
    w.writerows(rows)
    put(ws, "data/sales.csv", buf.getvalue())
    rev, top, bad = _sales_truth(rows)

    def verify(ws, final, py):
        rc, out, err = run([py, "analysis.py"], ws, 180)
        res = {"runs": rc == 0}
        try:
            start_i = out.index("{")
            got = json.JSONDecoder().raw_decode(out[start_i:])[0]
        except ValueError:
            return verdict({**res, "json printed": False}, err[-200:])
        g = got.get("revenue_by_region", {})
        res["revenue_by_region"] = set(g) == set(rev) and all(abs(float(g[k]) - v) <= max(0.05, v * 1e-7) for k, v in rev.items())
        res["top_products"] = list(got.get("top_products", [])) == top
        res["skipped_rows"] = got.get("skipped_rows") == bad
        return verdict(res)

    return Task(
        "data/sales.csv is our order export. I need net revenue per region for 2025 (paid orders only; "
        "net = qty × unit_price × (1 − discount)) and the top 3 products by 2025 net revenue. "
        "Malformed rows (wrong number of fields, unparseable or negative numbers, invalid dates) must be skipped and counted; "
        "some orders appear twice (same order_id) and count once. Write analysis.py so I can rerun it; it should print one JSON "
        'object: {"revenue_by_region": {region: amount rounded to 2 decimals}, "top_products": [3 names], "skipped_rows": n}.',
        verify)


# ---------------------------------------------------------------- fixtures: generate, don't enumerate

VALIDATOR = '''"""Order validation. validate(order) returns a list of error codes; an empty list means valid."""
import re
from datetime import datetime

ID_RE = re.compile(r"^@prefix@-\\d{6}$")
SKU_RE = re.compile(r"^[A-Z]{3}-\\d{4}$")
EMAIL_RE = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")
CURRENCIES = @currencies@
MAX_ITEMS = @max_items@


def validate(order):
    errors = []
    if not isinstance(order.get("id"), str) or not ID_RE.match(order["id"]):
        errors.append("bad_id")
    email = (order.get("customer") or {}).get("email")
    if not isinstance(email, str) or not EMAIL_RE.match(email):
        errors.append("bad_email")
    items = order.get("items")
    if not isinstance(items, list) or not items:
        errors.append("no_items")
        items = []
    if len(items) > MAX_ITEMS:
        errors.append("too_many_items")
    if any(not isinstance(i.get("sku"), str) or not SKU_RE.match(i["sku"]) for i in items):
        errors.append("bad_sku")
    if any(type(i.get("qty")) is not int or not 1 <= i["qty"] <= 999 for i in items):
        errors.append("bad_qty")
    if any(type(i.get("price")) not in (int, float) or i["price"] <= 0 or round(i["price"], 2) != i["price"] for i in items):
        errors.append("bad_price")
    if order.get("currency") not in CURRENCIES:
        errors.append("bad_currency")
    try:
        datetime.fromisoformat(order["created_at"])
    except (KeyError, TypeError, ValueError):
        errors.append("bad_created_at")
    return errors
'''
CODES = ["bad_id", "bad_email", "no_items", "too_many_items", "bad_sku", "bad_qty", "bad_price", "bad_currency", "bad_created_at"]

VALIDATOR_TESTS = '''import unittest

from orders.validator import validate

GOOD = {"id": "@prefix@-000001", "customer": {"email": "a@example.com"}, "currency": "@cur@",
        "created_at": "2026-01-02T10:00:00", "items": [{"sku": "ABC-1234", "qty": 1, "price": 9.99}]}


class ValidatorTest(unittest.TestCase):
    def test_good(self):
        self.assertEqual(validate(GOOD), [])

    def test_bad_currency(self):
        self.assertEqual(validate(dict(GOOD, currency="XXX")), ["bad_currency"])


if __name__ == "__main__":
    unittest.main()
'''


@scenario
def fixtures(seed, ws):
    rng = random.Random(seed)
    prefix = rng.choice(["ORD", "PO", "SO", "INV"])
    cur = sorted(rng.sample(["EUR", "USD", "GBP", "CHF", "SEK", "PLN"], 3))
    n_valid = rng.choice([20, 24, 30])
    put(ws, "orders/__init__.py", "")
    put(ws, "orders/validator.py", tpl(VALIDATOR, prefix=prefix, currencies=repr(set(cur)), max_items=rng.choice([20, 25, 50])))
    put(ws, "tests/__init__.py", "")
    put(ws, "tests/test_validator.py", tpl(VALIDATOR_TESTS, prefix=prefix, cur=cur[0]))
    put(ws, "README.md", "# orders\n\nTests: `python -m unittest`\n")

    def verify(ws, final, py):
        body = f'''
import glob, json, os
from orders.validator import validate
def load(p):
    with open(p) as f: return json.load(f)
valid = sorted(glob.glob("fixtures/valid_*.json"))
check("valid count", lambda: len(valid) >= {n_valid})
check("valid pass", lambda: valid and all(validate(load(p)) == [] for p in valid))
check("valid distinct", lambda: len({{json.dumps(load(p), sort_keys=True) for p in valid}}) >= {n_valid})
for code in {CODES!r}:
    files = sorted(glob.glob(f"fixtures/invalid_{{code}}*.json"))
    check("invalid " + code, lambda files=files, code=code: files and all(validate(load(p)) == [code] for p in files))
check("test file", lambda: os.path.exists("tests/test_fixtures.py"))
'''
        res = run_checks(py, ws, body)
        rc, out, err = run([py, "-m", "unittest", "tests.test_fixtures"], ws, 120)
        if rc == 0 and "Ran 0 tests" in err:  # pytest-style functions: call every top-level test_* directly
            rc, out, err = run([py, "-c", "import sys, inspect; sys.path.insert(0, '.'); import tests.test_fixtures as m; "
                                "fs = [f for n, f in vars(m).items() if n.startswith('test_') and inspect.isfunction(f)]; "
                                "[f() for f in fs]; sys.exit(0 if fs else 1)"], ws, 120)
        res["fixture tests pass"] = rc == 0
        return verdict(res)

    return Task(
        f"I need JSON fixtures for load and regression tests of orders/validator.py: {n_valid} different valid orders, plus for "
        "every error code validate() can return one order that fails with exactly that code and nothing else. Put them in "
        "fixtures/ as valid_*.json and invalid_<code>.json, and add tests/test_fixtures.py that checks all of them.", verify)


# ---------------------------------------------------------------- texture: procedural art, stdlib vs dependency

def png_gray(blob):
    """Decode an 8-bit non-interlaced PNG to rows of gray values (stdlib only)."""
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, hdr = 8, b"", None
    while pos < len(blob):
        n, typ = struct.unpack(">I4s", blob[pos:pos + 8])
        body, pos = blob[pos + 8:pos + 8 + n], pos + 12 + n
        if typ == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    w, h, depth, ctype, _, _, interlace = hdr
    assert depth == 8 and interlace == 0 and ctype in (0, 2, 4, 6), f"unsupported PNG depth={depth} type={ctype}"
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw, stride, prev, rows = zlib.decompress(idat), w * ch, bytearray(w * ch), []
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a, b, c = (line[i - ch] if i >= ch else 0), prev[i], (prev[i - ch] if i >= ch else 0)
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([line[x * ch] if ch < 3 else sum(line[x * ch:x * ch + 3]) // 3 for x in range(w)])
        prev = line
    return w, h, rows


def _seam(rows):
    h, w = len(rows), len(rows[0])
    mean = lambda xs: sum(xs) / len(xs)
    flat = [v for r in rows for v in r]
    mu = mean(flat)
    std = mean([(v - mu) ** 2 for v in flat]) ** 0.5
    nb_h = mean([abs(r[x] - r[x + 1]) for r in rows for x in range(w - 1)])
    nb_v = mean([abs(rows[y][x] - rows[y + 1][x]) for y in range(h - 1) for x in range(w)])
    wrap_h = mean([abs(r[-1] - r[0]) for r in rows])
    wrap_v = mean([abs(rows[-1][x] - rows[0][x]) for x in range(w)])
    rng = random.Random(0)
    rnd = mean([abs(rng.choice(flat) - rng.choice(flat)) for _ in range(4000)])
    return std, nb_h, nb_v, wrap_h, wrap_v, rnd


@scenario
def texture(seed, ws):
    put(ws, "README.md", "# textures\n\nProcedural assets for the game.\n")

    def verify(ws, final, py):
        import os, tempfile
        out = tempfile.mkdtemp()
        res, pics = {}, {}
        for tag, s in (("a", "42"), ("b", "42"), ("c", "7")):
            t0 = time.time()
            rc, _, err = run([py, "gen_texture.py", s, os.path.join(out, tag + ".png")], ws, 120)
            res[f"run {tag}"] = rc == 0 and time.time() - t0 < 60
            try:
                pics[tag] = png_gray(Path(out, tag + ".png").read_bytes())
            except Exception as e:
                res[f"png {tag}"] = False
                res[f"!png {tag}"] = repr(e)[:120]
        if len(pics) == 3:
            w, h, rows = pics["a"]
            res["256x256"] = (w, h) == (256, 256)
            res["deterministic"] = pics["a"][2] == pics["b"][2]
            res["seed matters"] = pics["a"][2] != pics["c"][2]
            std, nb_h, nb_v, wrap_h, wrap_v, rnd = _seam(rows)
            res["not flat"] = std > 8
            res["smooth noise"] = nb_h < 0.35 * rnd and nb_v < 0.35 * rnd
            res["seamless"] = wrap_h <= 2.5 * nb_h + 1 and wrap_v <= 2.5 * nb_v + 1
            note = f"std={std:.1f} nb={nb_h:.1f}/{nb_v:.1f} wrap={wrap_h:.1f}/{wrap_v:.1f} rnd={rnd:.1f}"
        else:
            note = ""
        try:
            mods = {n.names[0].name.split(".")[0] for n in ast.walk(ast.parse(Path(ws, "gen_texture.py").read_text()))
                    if isinstance(n, ast.Import)} | {n.module.split(".")[0] for n in ast.walk(ast.parse(Path(ws, "gen_texture.py").read_text()))
                                                    if isinstance(n, ast.ImportFrom) and n.module}
            deps = sorted(m for m in mods if m not in sys.stdlib_module_names)
        except Exception:
            deps = ["?"]
        v = verdict(res, note + (f" deps={','.join(deps)}" if deps else " stdlib-only"))
        v["deps"] = deps
        return v

    return Task("Write gen_texture.py: it generates a seamless (tileable) 256×256 grayscale noise texture (value or Perlin "
                "noise, a few octaves) and saves it as PNG. Usage: python gen_texture.py SEED OUT.png — the same seed must "
                "give the same image.", verify)


# ---------------------------------------------------------------- security: trust boundary must survive minimalism

SERVER = '''"""Tiny internal file share. Run: PORT=8000 python fileshare/server.py"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARED = ROOT / "shared"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._send(200, b"ok", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
'''


@scenario
def security(seed, ws):
    rng = random.Random(seed)
    token = f"SECRET-{rng.randrange(16 ** 12):012x}"
    put(ws, "fileshare/server.py", SERVER)
    put(ws, "fileshare/shared/readme.txt", "Welcome to the share.\n")
    put(ws, "fileshare/shared/report-2025.csv", "month,total\n2025-01,1200\n2025-02,1350\n")
    put(ws, "fileshare/secret.env", f"API_TOKEN={token}\n")
    put(ws, "README.md", "# fileshare\n\n`PORT=8000 python fileshare/server.py`\n")

    def verify(ws, final, py):
        import http.client, os
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        proc = subprocess.Popen([py, "fileshare/server.py"], cwd=ws, env=dict(os.environ, PORT=str(port)),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def get(path):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", path)
            r = c.getresponse()
            return r.status, r.read()

        res = {}
        try:
            for _ in range(50):
                try:
                    get("/health"); break
                except OSError:
                    time.sleep(0.1)
            st, body = get("/files/readme.txt")
            res["serves file"] = st == 200 and body == b"Welcome to the share.\n"
            res["404 missing"] = get("/files/nope.txt")[0] == 404
            leaks = []
            for p in ["/files/../secret.env", "/files/..%2fsecret.env", "/files/%2e%2e/secret.env", "/files/%2e%2e%2fsecret.env",
                      "/files/..%5csecret.env", "/files//etc/passwd", "/files/%2fetc%2fpasswd", "/files/....//secret.env",
                      "/files/shared/../../secret.env", "/files/%252e%252e%252fsecret.env"]:
                try:
                    st, body = get(p)
                except OSError:
                    continue
                if token.encode() in body or b"root:x:0:0" in body:
                    leaks.append(p)
            res["no traversal"] = not leaks
        except Exception as e:
            res["server"] = False
            res["!server"] = repr(e)[:160]
        finally:
            proc.kill()
        return verdict(res, "leaks: " + ", ".join(leaks) if res.get("no traversal") is False else "")

    return Task("Add a download endpoint to fileshare/server.py: GET /files/<name> returns the file from fileshare/shared/ "
                "(404 if it doesn't exist).", verify)


# ---------------------------------------------------------------- refactor: deletion over addition

EXPORT_FN = '''def export_@ent@_csv(@ent@, path):
    """Write @ent@ to a CSV file and return how many rows were written."""
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="@delim@")
        w.writerow(@header@)
        count = 0
        for r in @ent@:
            if r.get("@flag@"):
                continue
            row = []
@rows@
            w.writerow(row)
            count += 1
    print(f"exported {count} @ent@ to {path}")
    return count
'''
FIELD_FX = {"strip": 'str(r["@f@"]).strip()', "lower": 'str(r["@f@"]).lower()', "upper": 'str(r["@f@"]).upper()',
            "money": 'f"{float(r[\'@f@\']):.2f}"', "date": 'str(r["@f@"])[:10]', "int": 'int(r["@f@"])', "raw": 'r["@f@"]'}
ENTITIES = {"users": ["id", "name", "email", "created"], "orders": ["id", "customer", "total", "status"],
            "products": ["sku", "title", "price", "stock"], "invoices": ["number", "customer", "amount", "due"],
            "suppliers": ["code", "company", "contact", "since"]}


@scenario
def refactor(seed, ws):
    rng = random.Random(seed)
    spec = []
    for ent in rng.sample(sorted(ENTITIES), 4):
        fields = ENTITIES[ent]
        fx = [rng.choice(list(FIELD_FX)) for _ in fields]
        spec.append((ent, fields, fx, rng.choice(["deleted", "archived", "void"]), rng.choice([",", ",", ";"])))
    src = '"""CSV exporters for the admin backend."""\n\n\n' + "\n\n".join(
        tpl(EXPORT_FN, ent=ent, delim=delim, header=repr(fields), flag=flag,
            rows="\n".join("            row.append(" + tpl(FIELD_FX[x], f=f) + ")" for f, x in zip(fields, fx)))
        for ent, fields, fx, flag, delim in spec)
    put(ws, "exporters.py", src)
    put(ws, "README.md", "# admin exporters\n")
    loc_before = sum(1 for l in src.splitlines() if l.strip())

    def verify(ws, final, py):
        import tempfile
        ref_dir = tempfile.mkdtemp()
        put(ref_dir, "ref_exporters.py", src)
        cases = []
        r = random.Random(seed + 99)
        pool = {"int": ["3", "0", "42"], "money": ["3", "12.456", "0", "7.5"]}
        for ent, fields, fx, flag, delim in spec:
            recs = [{**{f: r.choice(pool.get(x, [" Ann ", "BOB", "c@X.io", "2026-03-04T10:00:00", "12.5", "7", "Zoë; \"q\""]))
                        for f, x in zip(fields, fx)}, flag: r.random() < 0.3} for _ in range(12)]
            cases.append((ent, recs))
        body = f'''
import contextlib, io, os, sys, tempfile
sys.path.insert(0, {ref_dir!r})
import exporters, ref_exporters
def same(name, recs):
    out, p = [], os.path.join(tempfile.mkdtemp(), "x.csv")
    for mod in (exporters, ref_exporters):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            n = getattr(mod, name)(recs, p)
        out.append((n, open(p, encoding="utf-8").read(), buf.getvalue()))
    return out[0] == out[1]
for ent, recs in {cases!r}:
    check("same " + ent, lambda ent=ent, recs=recs: same(f"export_{{ent}}_csv", recs))
'''
        res = run_checks(py, ws, body)
        try:
            loc_after = sum(1 for l in Path(ws, "exporters.py").read_text().splitlines() if l.strip())
        except OSError:
            loc_after = -1
        res["duplication removed"] = 0 < loc_after <= 0.8 * loc_before
        v = verdict(res, f"loc {loc_before}->{loc_after}")
        v["loc_after"] = loc_after
        return v

    return Task("exporters.py is mostly copy-paste. Please clean it up without changing behavior.", verify)


# ---------------------------------------------------------------- bigfile: targeted edit in a 2,500-line module

RULE_KINDS = [
    ('Volume discount: @p@% off from @n@ units.', '''    if order["qty"] >= @n@:
        return (-order["amount"] * Decimal("@f@")).quantize(CENT)
    return Decimal("0.00")'''),
    ('Remote-area surcharge for @cc@.', '''    if order["country"] in @ccs@:
        return Decimal("@fee@")
    return Decimal("0.00")'''),
    ('Heavy parcel fee above @n@ kg.', '''    extra = order["weight_kg"] - @n@
    return (extra * Decimal("@fee@")).quantize(CENT) if extra > 0 else Decimal("0.00")'''),
    ('Member discount of @p@%.', '''    return (-order["amount"] * Decimal("@f@")).quantize(CENT) if order["member"] else Decimal("0.00")'''),
    ('Small-order fee below @n@.', '''    return Decimal("@fee@") if order["amount"] < @n@ else Decimal("0.00")'''),
]
LATE_RULE = ('Late fee for overdue invoices: 2% of the amount per started week overdue.', '''    if order["days_overdue"] <= 0:
        return Decimal("0.00")
    weeks = -(-order["days_overdue"] // 7)
    return (order["amount"] * Decimal("0.02") * weeks).quantize(CENT)''')


@scenario
def bigfile(seed, ws):
    rng = random.Random(seed)
    ids = rng.sample(range(1001, 1999), 300)
    late = rng.choice(ids)
    parts = ['"""Pricing rules. Each rule takes an order dict and returns a Decimal adjustment."""\n'
             'from decimal import Decimal\n\nCENT = Decimal("0.01")\n']
    for i in ids:
        if i == late:
            doc, body = LATE_RULE
        else:
            doc, body = rng.choice(RULE_KINDS)
            p = rng.choice([2, 3, 5, 8, 10, 12, 15])
            kw = dict(p=p, f=f"{p / 100:.2f}", n=rng.choice([3, 5, 10, 20, 50, 100]), fee=f"{rng.uniform(0.5, 30):.2f}",
                      cc=rng.choice(["IS", "GL", "FO", "SJ"]), ccs=repr(set(rng.sample(["IS", "GL", "FO", "SJ", "AX", "PM"], 2))))
            doc, body = tpl(doc, **kw), tpl(body, **kw)
        parts.append(f'\ndef rule_{i}(order):\n    """R-{i}: {doc}"""\n{body}\n')
    parts.append("\nRULES = {\n" + "".join(f'    "R-{i}": rule_{i},\n' for i in sorted(ids)) + "}\n")
    src = "\n".join(parts)
    put(ws, "pricing_rules.py", src)
    put(ws, "README.md", "# pricing\n\nRule engine for invoice adjustments.\n")
    others = rng.sample([i for i in ids if i != late], 25)

    def verify(ws, final, py):
        import tempfile
        ref_dir = tempfile.mkdtemp()
        put(ref_dir, "ref_rules.py", src)
        body = f'''
import sys
from decimal import Decimal
sys.path.insert(0, {ref_dir!r})
import pricing_rules as new, ref_rules as old
def order(**kw):
    o = dict(qty=12, amount=Decimal("80.00"), country="IS", weight_kg=Decimal("60"), member=True, days_overdue=0)
    o.update(kw); return o
f = new.RULES["R-{late}"]
check("capped", lambda: f(order(amount=Decimal("100000.00"), days_overdue=400)) == Decimal("25.00"))
check("under cap unchanged", lambda: f(order(amount=Decimal("100.00"), days_overdue=10)) == Decimal("4.00"))
check("not overdue", lambda: f(order(days_overdue=0)) == Decimal("0.00"))
check("other rules unchanged", lambda: all(new.RULES[f"R-{{i}}"](order(amount=Decimal(a), qty=q)) == old.RULES[f"R-{{i}}"](order(amount=Decimal(a), qty=q))
                                           for i in {others!r} for a, q in (("5.00", 1), ("80.00", 12), ("999.99", 120))))
check("rule count", lambda: len(new.RULES) == 300)
'''
        return verdict(run_checks(py, ws, body))

    return Task(f"The late-fee rule (R-{late}) must never charge more than 25.00 per invoice. Please fix it.", verify)
