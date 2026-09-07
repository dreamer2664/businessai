"""A practice week in the store: python3 engine/scripts/practice_week.py [days=7] [--fresh]
Each day: customers come (simulated), the AI drafts a reply to every store message (thinking model + the store's own pages
+ the order system), runs its review, and the 'owner' (this script) applies the ship/cancel/refund proposals like a busy
owner would. Prints every reply with its safety flags, then the week's numbers. Reply quality is judged by rules:
  - order questions must state the true status (and tracking when shipped), never the generic policy days;
  - product / shipping / returns questions must carry the page's figure or answer;
  - never a flag from Inbox._check.
Ends with WEEK SCORE: good replies / all replies.  Store state lives in BAI_STATE (default /tmp/bai_state_week)."""
import os, re, sys, time, shutil, pathlib
sys.path.insert(0, ".")
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = os.environ.get("BAI_STATE", "/tmp/bai_state_week")
days = next((int(a) for a in sys.argv[1:] if a.isdigit()), 7)
if "--fresh" in sys.argv:
    shutil.rmtree(os.environ["BAI_STATE"], ignore_errors=True)
pathlib.Path(os.environ["BAI_STATE"], "logs").mkdir(parents=True, exist_ok=True)
from agent import config as _cfg
_cfg.ensure_dirs()
from agent import store as ST
from agent.inbox import Inbox
from agent.shopfacts import ShopFacts
from agent.tasks import Tasks
from agent.planner import Planner

PORT = 8098
S = ST.Store(log=lambda k, **f: None)
srv, url = ST.start(S, port=PORT)
T = Tasks()
F = ShopFacts(tasks=T, log=lambda k, **f: None)
print(F.learn(url).splitlines()[0], flush=True)
T.close_browser()
P = Planner()
I = Inbox(planner=P, shopfacts=F, store=S)
ST.Handler.inbox = I
good = total = 0
t0 = time.time()


def judge(rec, d):
    """Rule-based quality check of one reply."""
    low = d["text"].lower()
    why = []
    if d["checks"]:
        why.append("flags: " + "; ".join(d["checks"]))
    if re.search(r"7-15 business days", low):
        why.append("generic policy days")
    od = d.get("order") or {}
    if od and not od.get("mismatch"):
        st = od.get("status")
        if d["kind"] == "where_is_my_order":
            if st == "paid" and not re.search(r"warehouse|not (yet )?shipped|hasn't shipped|has not shipped|leaves within|will ship|being prepared", low):
                why.append("did not say it is still in the warehouse")
            if st in ("shipped", "delivered") and (od.get("tracking") or "").lower() not in low:
                why.append("no tracking number")
        if d["kind"] == "cancel_or_change":
            if st == "paid" and not re.search(r"cancel", low):
                why.append("did not confirm the cancellation path")
            if st in ("shipped", "delivered") and not re.search(r"cannot be cancel|can no longer|already (been )?shipped|already left|return", low):
                why.append("did not explain it already shipped")
    if d["kind"] == "product_question" and re.search(r"switzerland", rec["text"].lower()) and not re.search(r"not yet|2027|do not ship|don't ship|only .*eu|within the eu", low):
        why.append("did not say we don't ship to Switzerland yet")
    if d["kind"] == "product_question" and re.search(r"germany", rec["text"].lower()) and not re.search(r"4.6|6,90|6\.90", low):
        why.append("no German delivery figures")
    if d["kind"] == "return_or_refund" and not re.search(r"30 days|30-day", low):
        why.append("no return window")
    if d["kind"] == "discount_request" and "newsletter" not in low:
        why.append("discount policy missing")
    if re.search(r"\[[^\]]+\]", d["text"]):
        why.append("placeholder")
    if re.search(r"\bcancel", rec["text"].lower()) and d["kind"] != "cancel_or_change":
        why.append(f"a cancellation request was treated as {d['kind']}")
    if re.search(r"\b(photo of the damage)\b", low) and not re.search(r"\b(broken|damaged|crack|chip|dent|scratch|missing|faulty|defective)", rec["text"].lower()):
        why.append("asks for a damage photo although nothing is damaged")
    return why


try:
    for _ in range(days):
        r = S.simulate_day(inbox=I)
        print(f"\n=== day {r['day']}: {r['visits']} visits, {len(r['orders'])} order(s), {len(r['messages'])} message(s)", flush=True)
        for rec in I.items("new"):
            t1 = time.time()
            d = I.draft(rec)
            I.decide(rec["id"], "approved" if not d["checks"] else "rejected", d["text"] if not d["checks"] else "", kind=d["kind"], draft=d["text"])
            why = judge(rec, d)
            total += 1
            good += not why
            body = d["text"].split("\n\n")[1] if "\n\n" in d["text"] else d["text"]
            print(f"  {'ok ' if not why else 'BAD'} [{time.time()-t1:.0f}s] {d['kind']:17s} {rec['from'][:18]:18s} “{rec['text'][:70]}”\n        → {body[:260]!r}" + (f"\n        ✗ {'; '.join(why)}" if why else "") + (f"\n        (model draft rejected: {d['rejected']['checks']})" if d.get("rejected") else ""), flush=True)
            if rec.get("channel") == "store" and d.get("order_no") and d["kind"] in ("cancel_or_change", "damaged_or_wrong", "where_is_my_order"):
                prop = S.proposal_for_message(d["kind"], d["order_no"], rec["text"]) or next((p for p in reversed(S.data["proposals"]) if p["status"] == "open" and p["target"] == str(d["order_no"])), None)
                if prop:
                    print(f"        🏪 proposal: {prop['kind']} #{prop['target']} — applied by the owner: {S.apply(prop['id'])}", flush=True)
        props = S.review()
        applied = [S.apply(p["id"]) for p in props if p["kind"] in ("ship",)]
        others = [f"{p['kind']} {p['target']} → {p['change']}" for p in props if p["kind"] not in ("ship",)]
        print(f"  review: {len(props)} proposal(s); owner applied {len(applied)} shipment(s)" + (f"; left open: {', '.join(others)}" if others else ""), flush=True)
    print("\n" + S.numbers_text())
    print(f"\nWEEK SCORE: {good}/{total} good replies  ({time.time()-t0:.0f} s)")
finally:
    P.stop()
    ST.stop(S)
