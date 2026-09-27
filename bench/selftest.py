"""Verifier self-test: every scenario must FAIL untouched and PASS with a reference fix. No API calls.

    python3 selftest.py [seeds...]
"""
import re, sys, tempfile
from pathlib import Path

import scenarios as S


def sub(path, old, new):
    p = Path(path)
    text = p.read_text()
    assert old in text, (path, old[:60])
    p.write_text(text.replace(old, new))


def fix_rootcause(ws, seed):
    pkg = next(p.parent.name for p in Path(ws).glob("*/money.py"))
    sub(f"{ws}/{pkg}/money.py", '    s = str(text).strip().replace(",", ".")\n    return Decimal(s)',
        '    s = str(text).strip()\n    neg = s.startswith("(") and s.endswith(")")\n'
        '    s = re.sub(r"[^0-9,.-]", "", s)\n'
        '    if "," in s and "." in s:\n        s = s.replace("." if s.rfind(",") > s.rfind(".") else ",", "")\n'
        '    elif s.count(",") > 1 or s.count(".") > 1:\n        s = s.replace(",", "").replace(".", "")\n'
        '    v = Decimal(s.replace(",", "."))\n    return (-v if neg else v)')
    sub(f"{ws}/{pkg}/money.py", "from decimal", "import re\nfrom decimal")
    sub(f"{ws}/{pkg}/importer.py", '    return Decimal(cell.strip().replace(",", ".")).quantize(Decimal("0.01"))',
        '    from .money import parse_amount\n    return parse_amount(cell)')
    return ""


def fix_question(ws, seed):
    src = next(p for p in Path(ws).glob("*/*.py") if "LATE_FEE_RATE =" in p.read_text()).read_text()
    fn = re.search(r"^def (\w+)", src, re.M).group(1)
    rate = re.search(r'LATE_FEE_RATE = Decimal\("([\d.]+)"\)', src).group(1)
    return f"`{fn}()` applies it, using LATE_FEE_RATE = {rate} per started month."


def fix_feature(ws, seed):
    p = f"{ws}/todo.py"
    sub(p, "import sys\n", "import sys\nimport csv\nfrom datetime import date\n")
    if seed % 2 == 0:
        sub(p, '"done": False}', '"done": False, "due": args.due.isoformat() if args.due else None}')
        sub(p, '    for i in items:\n        mark',
            '    if args.overdue:\n        items = [i for i in items if not i["done"] and i.get("due") and i["due"] < date.today().isoformat()]\n'
            '    if args.format == "json":\n        return print(json.dumps(items))\n    for i in items:\n        mark')
        sub(p, 'a.add_argument("title")', 'a.add_argument("title")\n    a.add_argument("--due", type=date.fromisoformat)')
        sub(p, 'ls.add_argument("--all", action="store_true")',
            'ls.add_argument("--all", action="store_true")\n    ls.add_argument("--overdue", action="store_true")\n'
            '    ls.add_argument("--format", choices=["text", "json"], default="text")')
    else:
        sub(p, '"done": False}', '"done": False, "tags": args.tag}')
        sub(p, '    for i in items:\n        mark',
            '    if args.tag:\n        items = [i for i in items if args.tag.lower() in (t.lower() for t in i.get("tags", []))]\n'
            '    if args.format == "csv":\n        w = csv.writer(sys.stdout)\n        w.writerow(["id", "title", "done", "tags"])\n'
            '        return w.writerows([i["id"], i["title"], i["done"], ";".join(i.get("tags", []))] for i in items)\n'
            '    for i in items:\n        mark')
        sub(p, 'a.add_argument("title")', 'a.add_argument("title")\n    a.add_argument("--tag", action="append", default=[])')
        sub(p, 'ls.add_argument("--all", action="store_true")',
            'ls.add_argument("--all", action="store_true")\n    ls.add_argument("--tag")\n'
            '    ls.add_argument("--format", choices=["text", "csv"], default="text")')
    return ""


def fix_data(ws, seed):
    S.put(ws, "analysis.py", '''import csv, json
from datetime import date
seen, bad, rev, prod = set(), 0, {}, {}
with open("data/sales.csv", newline="") as f:
    rows = csv.reader(f)
    next(rows)
    for r in rows:
        try:
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
print(json.dumps({"revenue_by_region": {k: round(v, 2) for k, v in rev.items()},
                  "top_products": sorted(prod, key=prod.get, reverse=True)[:3], "skipped_rows": bad}))
''')
    return ""


def fix_fixtures(ws, seed):
    src = Path(ws, "orders/validator.py").read_text()
    prefix = re.search(r'ID_RE = re.compile\(r"\^(\w+)-', src).group(1)
    cur = sorted(eval(re.search(r"CURRENCIES = (\{.*\})", src).group(1)))
    max_items = int(re.search(r"MAX_ITEMS = (\d+)", src).group(1))
    n = int(re.search(r"(\d+) different valid", S.SCENARIOS["fixtures"](seed, tempfile.mkdtemp()).prompt).group(1))
    S.put(ws, "make_fixtures.py", f'''import json, os, random
rng = random.Random(1)
os.makedirs("fixtures", exist_ok=True)
def order(i):
    return {{"id": "{prefix}-%06d" % i, "customer": {{"email": "c%d@example.com" % i}}, "currency": rng.choice({cur!r}),
            "created_at": "2026-01-%02dT10:00:00" % (i % 28 + 1),
            "items": [{{"sku": "ABC-%04d" % rng.randrange(10000), "qty": rng.randint(1, 9), "price": rng.randint(1, 9999) / 100}}]}}
for i in range({n}):
    json.dump(order(i + 1), open("fixtures/valid_%02d.json" % i, "w"))
bad = {{"bad_id": {{"id": "X"}}, "bad_email": {{"customer": {{"email": "nope"}}}}, "no_items": {{"items": []}},
       "too_many_items": {{"items": [{{"sku": "ABC-0001", "qty": 1, "price": 1.0}}] * {max_items + 1}}},
       "bad_sku": {{"items": [{{"sku": "abc", "qty": 1, "price": 1.0}}]}}, "bad_qty": {{"items": [{{"sku": "ABC-0001", "qty": 0, "price": 1.0}}]}},
       "bad_price": {{"items": [{{"sku": "ABC-0001", "qty": 1, "price": 1.001}}]}}, "bad_currency": {{"currency": "XXX"}},
       "bad_created_at": {{"created_at": "yesterday"}}}}
for code, patch in bad.items():
    json.dump({{**order(999), **patch}}, open("fixtures/invalid_%s.json" % code, "w"))
''')
    S.put(ws, "tests/test_fixtures.py", '''import glob, json, os, unittest
from orders.validator import validate
class FixtureTest(unittest.TestCase):
    def test_valid(self):
        for p in glob.glob("fixtures/valid_*.json"):
            self.assertEqual(validate(json.load(open(p))), [], p)
    def test_invalid(self):
        for p in glob.glob("fixtures/invalid_*.json"):
            code = os.path.basename(p)[8:-5]
            self.assertEqual(validate(json.load(open(p))), [code], p)
''')
    S.run([sys.executable, "make_fixtures.py"], ws)
    return ""


def fix_texture(ws, seed):
    S.put(ws, "gen_texture.py", '''import random, struct, sys, zlib
seed, out = int(sys.argv[1]), sys.argv[2]
N, P = 256, 8
rng = random.Random(seed)
def octave(period):
    g = [[rng.random() for _ in range(period)] for _ in range(period)]
    s = lambda t: t * t * (3 - 2 * t)
    cell = N / period
    def at(x, y):
        x0, y0 = int(x // cell), int(y // cell)
        fx, fy = s(x / cell - x0), s(y / cell - y0)
        a, b = g[y0 % period][x0 % period], g[y0 % period][(x0 + 1) % period]
        c, d = g[(y0 + 1) % period][x0 % period], g[(y0 + 1) % period][(x0 + 1) % period]
        return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy
    return at
octs = [(octave(P * 2 ** k), 0.5 ** k) for k in range(4)]
norm = sum(w for _, w in octs)
rows = b"".join(b"\\0" + bytes(int(255 * sum(f(x, y) * w for f, w in octs) / norm) for x in range(N)) for y in range(N))
chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
open(out, "wb").write(b"\\x89PNG\\r\\n\\x1a\\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 0, 0, 0, 0))
                      + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))
''')
    return ""


def fix_security(ws, seed):
    p = f"{ws}/fileshare/server.py"
    sub(p, "import os\n", "import os\nfrom urllib.parse import unquote\n")
    sub(p, '            self._send(200, b"ok", "text/plain")\n',
        '            self._send(200, b"ok", "text/plain")\n'
        '        elif self.path.startswith("/files/"):\n'
        '            f = (SHARED / unquote(self.path[7:])).resolve()\n'
        '            if f.parent == SHARED.resolve() and f.is_file():\n'
        '                self._send(200, f.read_bytes(), "application/octet-stream")\n'
        '            else:\n'
        '                self._send(404, b"not found", "text/plain")\n')
    return ""


def fix_refactor(ws, seed):
    src = Path(ws, "exporters.py").read_text()
    out = ['"""CSV exporters for the admin backend."""\nimport csv\n\n\n'
           'def _export(records, path, name, header, skip, delim, row):\n'
           '    with open(path, "w", newline="", encoding="utf-8") as f:\n'
           '        w = csv.writer(f, delimiter=delim)\n        w.writerow(header)\n        count = 0\n'
           '        for r in records:\n            if r.get(skip):\n                continue\n'
           '            w.writerow(row(r))\n            count += 1\n'
           '    print(f"exported {count} {name} to {path}")\n    return count\n']
    for m in re.finditer(r'def export_(\w+)_csv.*?delimiter="(.)".*?w.writerow\((\[.*?\])\).*?r.get\("(\w+)"\).*?row = \[\]\n(.*?)\n            w.writerow', src, re.S):
        ent, delim, header, flag, rows = m.groups()
        exprs = ", ".join(re.findall(r"row.append\((.*)\)", rows))
        out.append(f'\ndef export_{ent}_csv({ent}, path):\n    return _export({ent}, path, "{ent}", {header}, "{flag}", "{delim}", lambda r: [{exprs}])\n')
    Path(ws, "exporters.py").write_text("".join(out))
    return ""


def fix_bigfile(ws, seed):
    p = Path(ws, "pricing_rules.py")
    text = p.read_text()
    old = '    return (order["amount"] * Decimal("0.02") * weeks).quantize(CENT)'
    assert text.count(old) == 1
    p.write_text(text.replace(old, '    return min((order["amount"] * Decimal("0.02") * weeks).quantize(CENT), Decimal("25.00"))'))
    return ""


def main(seeds):
    ok = True
    for name, make in S.SCENARIOS.items():
        for seed in seeds:
            ws = tempfile.mkdtemp(prefix=f"st_{name}_")
            task = make(seed, ws)
            before = task.verify(ws, "", sys.executable)
            final = globals()["fix_" + name](ws, seed)
            after = task.verify(ws, final, sys.executable)
            good = not before["pass"] and after["pass"]
            ok &= good
            print(f"{'ok ' if good else 'XX '} {name:10} seed={seed}  untouched={before['score']:<5} fixed={after['score']:<5} {after['notes'][:150]}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main([int(s) for s in sys.argv[1:]] or [1, 2])
