"""Hash-chain journal: concurrent writers stay linear; a benign fork is reported, a deletion or edit still breaks."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from journal import Journal, verify

d = Path(tempfile.mkdtemp())

# 1. Two writers on one file (the bot's Journal and review.py's), interleaved: chain must stay linear.
p = d / "log.jsonl"
bot, review = Journal(p), Journal(p)
bot.log("regime", n=1)
review.log("tune", n=2)          # written by the other process
bot.log("review", n=3)           # bot's in-memory head is stale here; the old code forked at this line
bot.log("regime", n=4)
ok, n, forks = verify(p, with_forks=True)
assert ok and n == 4 and forks == [], (ok, n, forks)
print("interleaved writers: linear chain ✓")

# 2. A historical fork (two siblings naming the same parent) is reported, not a break.
rows = [json.loads(x) for x in p.read_text().splitlines()]
import hashlib
def seal(r):
    r = {k: v for k, v in r.items() if k != "hash"}
    r["hash"] = hashlib.sha256(json.dumps(r, sort_keys=True, default=str).encode()).hexdigest()
    return r
rows[2]["prev"] = rows[0]["hash"]; rows[2] = seal(rows[2])        # sibling of rows[1]
rows[3]["prev"] = rows[2]["hash"]; rows[3] = seal(rows[3])
f = d / "fork.jsonl"; f.write_text("".join(json.dumps(r) + "\n" for r in rows))
ok, n, forks = verify(f, with_forks=True)
assert ok and forks == [2], (ok, n, forks)
print("historical fork reported, not broken ✓")

# 3. Deleting a record still breaks the chain.
g = d / "del.jsonl"; g.write_text("".join(json.dumps(r) + "\n" for i, r in enumerate(json.loads(x) for x in p.read_text().splitlines()) if i != 1))
assert verify(g) == (False, 1), verify(g)
print("deleted record detected ✓")

# 4. Editing a record still breaks the chain.
rows = [json.loads(x) for x in p.read_text().splitlines()]; rows[1]["n"] = 99
h = d / "edit.jsonl"; h.write_text("".join(json.dumps(r) + "\n" for r in rows))
assert verify(h)[0] is False
print("edited record detected ✓")
print("ALL PASS")
