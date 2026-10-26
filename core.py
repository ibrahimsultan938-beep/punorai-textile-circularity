import sqlite3, math, json, os, datetime, html

NOW = lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lots(
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, source_name TEXT,
 source_type TEXT, category TEXT, grade TEXT, colour TEXT,
 contamination_pct REAL, qty_kg REAL, lat REAL, lon REAL,
 location_name TEXT, status TEXT DEFAULT 'pending', photo TEXT DEFAULT '',
 notes TEXT DEFAULT '', allocated INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS buyers(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT,
 accepted_grades TEXT, max_contamination REAL, min_qty REAL, max_qty REAL,
 price_low REAL, price_high REAL, lat REAL, lon REAL, location_name TEXT,
 service_radius_km REAL, status TEXT DEFAULT 'simulated', created_at TEXT);
CREATE TABLE IF NOT EXISTS prices(
 id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, grade TEXT,
 low REAL, high REAL, source TEXT, updated_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS batches(
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, buyer_id INTEGER,
 buyer_name TEXT, total_kg REAL, lot_count INTEGER, route_km REAL,
 route_cost REAL, status TEXT DEFAULT 'candidate', created_at TEXT);
CREATE TABLE IF NOT EXISTS batch_lots(
 batch_id INTEGER, lot_id INTEGER);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER, ts TEXT,
 description TEXT);
"""

CATEGORIES = ["cotton", "polyester", "cotton-polyester blend", "denim", "mixed textile waste"]

def get_db(path):
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()

# ---------- geo ----------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

# ---------- seed ----------
def seed(conn):
    c = conn.execute("SELECT COUNT(*) n FROM lots").fetchone()["n"]
    if c: return False
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('lots', 'buyers', 'prices', 'batches', 'events')")
    except Exception:
        pass
    buyers = [
      ("Recycler X (Dhaka)", "cotton", "A,B", 5, 1000, 10000, 42, 55,
       23.8103, 90.4125, "Dhaka", 60, "simulated"),
      ("Recycler Y (Gazipur)", "polyester", "A,B,C", 8, 500, 8000, 25, 38,
       23.9999, 90.4203, "Gazipur", 50, "simulated"),
      ("Factory C - Reused Fibre (Ashulia)", "cotton", "B,C", 10, 300, 5000, 35, 48,
       23.8850, 90.2600, "Ashulia", 40, "simulated"),
    ]
    conn.executemany("""INSERT INTO buyers(name,category,accepted_grades,max_contamination,
      min_qty,max_qty,price_low,price_high,lat,lon,location_name,service_radius_km,status)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", buyers)
    lots = [
      ("LOT-A","Shanto Knitwear Ltd","factory","cotton","B","off-white",3,300,23.9999,90.4203,"Gazipur","verified"),
      ("LOT-B","Rupa Fabrics","factory","cotton","B","grey",4,250,23.9900,90.4100,"Gazipur","verified"),
      ("LOT-C","TexDye Industries","factory","cotton-polyester blend","B","navy",6,400,23.8103,90.4125,"Dhaka","verified"),
      ("LOT-D","Sunrise Apparels","factory","cotton","A","white",2,500,23.8700,90.2700,"Ashulia","pending"),
      ("LOT-E","Karim Textile Traders","trader","cotton","B","mixed",5,150,23.6200,90.5000,"Narayanganj","pending"),
      ("LOT-F","Karim Textile Traders","trader","polyester","A","black",2,200,23.6300,90.5100,"Narayanganj","verified"),
      ("LOT-G","DenimCo BD","factory","denim","C","blue",9,350,23.8500,90.2500,"Ashulia","verified"),
      ("LOT-H","Jhalkuri Collective","trader","mixed textile waste","C","mixed",12,120,23.6250,90.4950,"Narayanganj","simulated"),
      ("LOT-I","Nasrin Sorting House","trader","cotton","B","off-white",4,180,24.0100,90.4300,"Gazipur","verified"),
      ("LOT-J","TexDye Industries","factory","cotton-polyester blend","A","teal",3,600,23.8050,90.4200,"Dhaka","pending"),
    ]
    conn.executemany("""INSERT INTO lots(code,source_name,source_type,category,grade,colour,
      contamination_pct,qty_kg,lat,lon,location_name,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      [(l[0],l[1],l[2],l[3],l[4],l[5],l[6],l[7],l[8],l[9],l[10],l[11],NOW()) for l in lots])
    prices = [
      ("cotton","A",45,60,"User-entered demo range (Gazipur trader)","2026-10-01","simulated"),
      ("cotton","B",38,52,"User-entered demo range (Gazipur trader)","2026-10-01","simulated"),
      ("polyester","A",28,38,"User-entered demo range (Dhaka recycler)","2026-10-03","simulated"),
      ("cotton-polyester blend","A",30,45,"User-entered demo range (Dhaka recycler)","2026-10-03","simulated"),
      ("denim","C",15,25,"User-entered demo range (Ashulia factory)","2026-10-05","simulated"),
    ]
    conn.executemany("INSERT INTO prices(category,grade,low,high,source,updated_at,status) VALUES(?,?,?,?,?,?,?)", prices)

    # Seed current batch CIRC-2026-0001 with LOT-A (300kg, Verified), LOT-B (250kg, Verified), LOT-D (500kg, Pending verification)
    # Total = 1,050 kg for Recycler X (Dhaka)
    cur = conn.execute("""INSERT INTO batches(code,buyer_id,buyer_name,total_kg,lot_count,route_km,route_cost,status,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        ("CIRC-2026-0001", 1, "Recycler X (Dhaka)", 1050.0, 3, 58.1, 6968.0, "partially_verified", NOW()))
    bid = cur.lastrowid
    # Allocate lots 1 (LOT-A), 2 (LOT-B), 4 (LOT-D)
    for lid in [1, 2, 4]:
        conn.execute("INSERT INTO batch_lots(batch_id,lot_id) VALUES(?,?)", (bid, lid))
        conn.execute("UPDATE lots SET allocated=1 WHERE id=?", (lid,))

    events = [
        (bid, NOW(), "Batch CIRC-2026-0001 created from 3 aggregated lots (1,050 kg) for Recycler X (Dhaka)."),
        (bid, NOW(), "Supplier declared lots: LOT-A (300 kg, Verified), LOT-B (250 kg, Verified), LOT-D (500 kg, Pending verification)."),
        (bid, NOW(), "Verification protocol: Partially verified (550 / 1,050 kg verified &bull; 52%). LOT-D requires physical intake QA before full clearance."),
        (bid, NOW(), "Digital Material Passport issued. Traceability chain active with declared composition.")
    ]
    conn.executemany("INSERT INTO events(batch_id,ts,description) VALUES(?,?,?)", events)
    conn.commit()
    return True

def batch_verification_status(lots):
    """
    Evaluates the verification status of a batch based on its constituent lots.
    Returns (status_code, label, badge_class, description).
    Never presents the entire batch as verified while any constituent lot is pending.
    """
    if not lots:
        return ("empty", "No Lots", "b-simulated", "Batch has no constituent lots assigned.")

    lot_dicts = [dict(l) if not isinstance(l, dict) else l for l in lots]
    statuses = [l.get("status", "pending") for l in lot_dicts]
    total_kg = sum(float(l.get("qty_kg", 0)) for l in lot_dicts)
    verified_kg = sum(float(l.get("qty_kg", 0)) for l in lot_dicts if l.get("status") == "verified")
    pending_kg = sum(float(l.get("qty_kg", 0)) for l in lot_dicts if l.get("status") == "pending")

    ver_count = statuses.count("verified")
    pend_count = statuses.count("pending")

    if pend_count == 0 and ver_count > 0:
        return ("verified", "Verified Batch", "b-verified",
                f"All {len(lots)} constituent lots ({int(total_kg):,} kg) have completed physical intake verification.")
    elif ver_count > 0 and pend_count > 0:
        pct = int(round(100 * verified_kg / total_kg)) if total_kg else 0
        return ("partially_verified", "Partially Verified", "b-pending",
                f"{ver_count} of {len(lots)} lots verified ({int(verified_kg):,} / {int(total_kg):,} kg &bull; {pct}%). {pend_count} lot(s) pending intake QA.")
    else:
        return ("pending", "Pending Verification", "b-pending",
                f"All {len(lots)} constituent lots ({int(total_kg):,} kg) are pending physical intake QA confirmation.")

# ---------- aggregation engine (transparent constraint solver) ----------
def exclusion_reason(lot, buyer, conn=None):
    if not isinstance(lot, dict):
        lot = dict(lot)
    if not isinstance(buyer, dict):
        buyer = dict(buyer)

    # 1. Allocation check (Highest priority: already allocated lots cannot be aggregated)
    if lot.get("allocated"):
        batch_code = lot.get("batch_code")
        if not batch_code and conn and lot.get("id"):
            row = conn.execute("""
                SELECT b.code FROM batches b
                JOIN batch_lots bl ON b.id = bl.batch_id
                WHERE bl.lot_id = ?
            """, (lot["id"],)).fetchone()
            if row:
                batch_code = row["code"]
        return f"Already allocated to {batch_code}" if batch_code else "Already allocated to another batch"

    # 2. Material category mismatch
    if lot["category"] != buyer["category"]:
        return f"Material category mismatch (needs {buyer['category']})"

    # 3. Grade not accepted
    accepted_grades = [g.strip() for g in buyer["accepted_grades"].split(",")]
    if lot["grade"] not in accepted_grades:
        return f"Grade {lot['grade']} not accepted (accepts {buyer['accepted_grades']})"

    # 4. Contamination exceeds buyer limit
    if lot["contamination_pct"] > buyer["max_contamination"]:
        return f"Contamination {lot['contamination_pct']}% exceeds limit {buyer['max_contamination']}%"

    # 5. Quantity limit check
    if lot["qty_kg"] > buyer.get("max_qty", float("inf")):
        return "Quantity exceeds buyer maximum"

    # 6. Verification policy check (if buyer policy requires verified intake)
    if buyer.get("require_verified") and lot.get("status") != "verified":
        return "Pending verification (buyer requires verified intake)"

    return None

def subset_sum_kg(lots, target):
    # exact DP over integer kg to find the smallest feasible combination >= target
    units = [int(round(l["qty_kg"])) for l in lots]
    total = sum(units)
    if total < target: return None
    # dp[s] = list of indices forming sum s (minimize s >= target)
    best = None
    dp = {0: []}
    for i, w in enumerate(units):
        for s in list(dp.keys()):
            ns = s + w
            if ns > total: continue
            if ns not in dp:
                dp[ns] = dp[s] + [i]
    feasible = [s for s in dp if s >= target]
    if not feasible: return None
    best = min(feasible)
    return [lots[i] for i in dp[best]]

def find_candidate_batches(conn, buyer, eligible_lots):
    """
    Evaluates eligible unallocated lots against multi-objective operational goals:
      1. Batch weight fit (>= min_qty and <= max_qty)
      2. Material purity (weighted average contamination %)
      3. Freight friction (straight-line circuit km, total BDT, and BDT/kg at declared 120 BDT/km)
      4. Physical QA / verification provenance (% verified kg vs pending intake QA)
    Returns:
      candidates: Ranked list of candidate batch dictionaries with operational rationales.
    """
    if not eligible_lots:
        return []

    buyer_dict = dict(buyer) if not isinstance(buyer, dict) else buyer
    min_qty = float(buyer_dict["min_qty"])
    max_qty = float(buyer_dict.get("max_qty", 100000.0))
    total_avail = sum(float(l["qty_kg"]) for l in eligible_lots)
    if total_avail < min_qty:
        return []

    # Sort lots deterministically
    sorted_lots = sorted(eligible_lots, key=lambda x: (x.get("id", 0), x.get("code", "")))
    n = len(sorted_lots)

    valid_subsets = []

    # Branch-and-bound search for minimal / near-minimal subsets satisfying min_qty
    def search(idx, current_lots, current_kg):
        if current_kg >= min_qty:
            if current_kg <= max_qty:
                valid_subsets.append(list(current_lots))
            return

        for i in range(idx, n):
            lot = sorted_lots[i]
            search(i + 1, current_lots + [lot], current_kg + float(lot["qty_kg"]))

    search(0, [], 0.0)

    # If no minimal subset was captured (e.g. all lots together are needed)
    if not valid_subsets and total_avail >= min_qty and total_avail <= max_qty:
        valid_subsets.append(list(sorted_lots))

    # Deduplicate subsets by set of lot IDs or codes
    unique_subsets = []
    seen_ids = set()
    for sub in valid_subsets:
        ids_tuple = tuple(sorted(l.get("id") or l.get("code") for l in sub))
        if ids_tuple not in seen_ids:
            seen_ids.add(ids_tuple)
            unique_subsets.append(sub)

    if not unique_subsets:
        # Fallback to single subset-sum if branch search found none
        sub = subset_sum_kg(eligible_lots, int(math.ceil(min_qty)))
        if sub:
            unique_subsets.append(sub)

    if not unique_subsets:
        return []

    buyer_lat = float(buyer_dict["lat"])
    buyer_lon = float(buyer_dict["lon"])
    rate_per_km = 120.0  # Declared freight rate

    evaluated = []
    for sub in unique_subsets:
        total_kg = sum(float(l["qty_kg"]) for l in sub)
        excess_kg = max(0.0, total_kg - min_qty)
        weighted_contam = sum(float(l["qty_kg"]) * float(l["contamination_pct"]) for l in sub) / total_kg

        # Route planning
        lot_ids = [l["id"] for l in sub if "id" in l]
        if conn and lot_ids and all(isinstance(i, int) for i in lot_ids):
            r = plan_route(conn, lot_ids, buyer_lat, buyer_lon, rate_per_km=rate_per_km)
            route_km = r["total_km"]
            route_cost = r["est_cost"]
        else:
            # Fallback distance calculation
            pts = [(float(l["lat"]), float(l["lon"])) for l in sub]
            route_km = 0.0
            cur = (buyer_lat, buyer_lon)
            rem = pts[:]
            while rem:
                nxt = min(rem, key=lambda p: haversine(cur[0], cur[1], p[0], p[1]))
                route_km += haversine(cur[0], cur[1], nxt[0], nxt[1])
                cur = nxt
                rem.remove(nxt)
            route_km += haversine(cur[0], cur[1], buyer_lat, buyer_lon)
            route_km = round(route_km, 1)
            route_cost = round(route_km * rate_per_km)

        cost_per_kg = route_cost / total_kg if total_kg > 0 else 0.0

        # Verification breakdown (strictly preserve pending/simulated distinctions)
        v_code, v_label, v_badge, v_desc = batch_verification_status(sub)
        verified_kg = sum(float(l["qty_kg"]) for l in sub if l.get("status") == "verified")
        verified_pct = round(100.0 * verified_kg / total_kg, 1) if total_kg > 0 else 0.0
        pending_kg = sum(float(l["qty_kg"]) for l in sub if l.get("status") == "pending")
        pending_pct = round(100.0 * pending_kg / total_kg, 1) if total_kg > 0 else 0.0
        verified_count = sum(1 for l in sub if l.get("status") == "verified")
        pending_count = sum(1 for l in sub if l.get("status") == "pending")

        # Multi-objective desirability scoring (0 to 100)
        # 1. Verification score (35%): higher verified share reduces QA quarantine risk
        score_ver = verified_pct
        # 2. Purity score (25%): lower contamination is better
        max_c = max(float(buyer_dict.get("max_contamination", 5.0)), 1.0)
        score_purity = max(0.0, 100.0 * (1.0 - (weighted_contam / max_c)))
        # 3. Transport efficiency score (25%): lower BDT/kg is better (reference max ~25 BDT/kg)
        score_transport = max(0.0, min(100.0, 100.0 * (1.0 - (cost_per_kg / 25.0))))
        # 4. Weight fit score (15%): closer to target weight is leaner
        score_fit = max(0.0, min(100.0, 100.0 * (1.0 - (excess_kg / max(min_qty, 1.0)))))

        composite_score = round(0.35 * score_ver + 0.25 * score_purity + 0.25 * score_transport + 0.15 * score_fit, 1)

        candidate = {
            "lots": [dict(l) for l in sub],
            "lot_ids": [l["id"] for l in sub if "id" in l],
            "lot_codes": [l["code"] for l in sub],
            "total_kg": total_kg,
            "excess_kg": excess_kg,
            "target_kg": min_qty,
            "avg_contamination": round(weighted_contam, 2),
            "route_km": route_km,
            "route_cost": route_cost,
            "cost_per_kg": round(cost_per_kg, 2),
            "stops_count": len(sub),
            "v_code": v_code,
            "v_label": v_label,
            "v_badge": v_badge,
            "v_desc": v_desc,
            "verified_kg": verified_kg,
            "verified_pct": verified_pct,
            "pending_kg": pending_kg,
            "pending_pct": pending_pct,
            "verified_count": verified_count,
            "pending_count": pending_count,
            "composite_score": composite_score,
            "score_ver": round(score_ver, 1),
            "score_purity": round(score_purity, 1),
            "score_transport": round(score_transport, 1),
            "score_fit": round(score_fit, 1),
        }
        evaluated.append(candidate)

    # Sort candidates by composite desirability descending
    evaluated.sort(key=lambda c: -c["composite_score"])

    # Designate Primary Recommended candidate
    best = evaluated[0]
    best["is_recommended"] = True
    best["profile_id"] = "recommended"
    best["profile_name"] = "Balanced Optimal Batch"
    best["profile_badge"] = "Recommended (Balanced Optimal)"
    best["profile_badge_class"] = "b-verified"
    best["rationale"] = (
        f"Top-ranked multi-objective trade-off: {best['verified_pct']}% QA-verified feedstock, "
        f"{best['cost_per_kg']:.2f} BDT/kg logistics friction ({best['route_km']} km circuit), and "
        f"{best['avg_contamination']:.1f}% weighted contamination (well within buyer limit of {buyer_dict['max_contamination']}%)."
    )

    if len(evaluated) == 1:
        best["rationale"] = (
            f"Sole feasible unallocated combination meeting minimum batch size "
            f"({int(best['total_kg']):,} kg \u2265 {int(min_qty):,} kg target). "
            f"Provides {best['verified_pct']}% QA verification at {best['cost_per_kg']:.2f} BDT/kg logistics friction."
        )
        return [best]

    # Select up to 2 distinct operational alternative profiles
    seen_lot_tuples = {tuple(sorted(best["lot_codes"]))}
    candidates = [best]

    # Profile A: Highest Physical QA / Zero Quarantine Delay
    qa_candidates = [c for c in evaluated if tuple(sorted(c["lot_codes"])) not in seen_lot_tuples]
    if qa_candidates:
        qa_best = max(qa_candidates, key=lambda c: (c["verified_pct"], -c["avg_contamination"]))
        if qa_best["verified_pct"] > best["verified_pct"] or (best["verified_pct"] < 100.0 and qa_best["verified_pct"] == 100.0):
            qa_best["is_recommended"] = False
            qa_best["profile_id"] = "highest_qa"
            qa_best["profile_name"] = "Maximum Physical QA Verification"
            qa_best["profile_badge"] = "Alternative (Highest Physical QA)"
            qa_best["profile_badge_class"] = "b-primary"
            qa_best["rationale"] = (
                f"Maximizes physical QA verification to {qa_best['verified_pct']}% "
                f"({qa_best['verified_count']} of {len(qa_best['lots'])} lots verified). "
                f"Minimizes intake quarantine delay and lab inspection friction at reception."
            )
            candidates.append(qa_best)
            seen_lot_tuples.add(tuple(sorted(qa_best["lot_codes"])))

    # Profile B: Lowest Freight Friction / Geographic Proximity
    freight_candidates = [c for c in evaluated if tuple(sorted(c["lot_codes"])) not in seen_lot_tuples]
    if freight_candidates:
        freight_best = min(freight_candidates, key=lambda c: (c["cost_per_kg"], c["route_km"]))
        if freight_best["cost_per_kg"] < best["cost_per_kg"]:
            freight_best["is_recommended"] = False
            freight_best["profile_id"] = "lowest_freight"
            freight_best["profile_name"] = "Lowest Logistics Friction"
            freight_best["profile_badge"] = "Alternative (Lowest Freight Friction)"
            freight_best["profile_badge_class"] = "b-accent"
            freight_best["rationale"] = (
                f"Minimizes freight expenditure to {freight_best['cost_per_kg']:.2f} BDT/kg "
                f"({freight_best['route_km']} km circuit &bull; {int(freight_best['route_cost']):,} BDT total) "
                f"by bundling geographically proximate suppliers."
            )
            candidates.append(freight_best)
            seen_lot_tuples.add(tuple(sorted(freight_best["lot_codes"])))

    # Profile C: Leanest Volume Match
    if len(candidates) < 3:
        lean_candidates = [c for c in evaluated if tuple(sorted(c["lot_codes"])) not in seen_lot_tuples]
        if lean_candidates:
            lean_best = min(lean_candidates, key=lambda c: (c["excess_kg"], c["total_kg"]))
            if lean_best["excess_kg"] < best["excess_kg"]:
                lean_best["is_recommended"] = False
                lean_best["profile_id"] = "lean_volume"
                lean_best["profile_name"] = "Closest Target Volume Match"
                lean_best["profile_badge"] = "Alternative (Leanest Target Fit)"
                lean_best["profile_badge_class"] = "b-pending"
                lean_best["rationale"] = (
                    f"Closest match to buyer minimum ({int(lean_best['total_kg']):,} kg vs {int(min_qty):,} kg target "
                    f"&bull; {int(lean_best['excess_kg']):,} kg excess). Conserves remaining inventory for subsequent orders."
                )
                candidates.append(lean_best)
                seen_lot_tuples.add(tuple(sorted(lean_best["lot_codes"])))

    # If still fewer than 3 and there are other valid evaluated candidates, add the next best
    for c in evaluated:
        if len(candidates) >= 3:
            break
        tup = tuple(sorted(c["lot_codes"]))
        if tup not in seen_lot_tuples:
            c["is_recommended"] = False
            c["profile_id"] = f"alt_{len(candidates)}"
            c["profile_name"] = f"Alternative Option {len(candidates)}"
            c["profile_badge"] = f"Alternative Candidate {len(candidates)}"
            c["profile_badge_class"] = "b-pending"
            c["rationale"] = (
                f"Viable aggregation option: {int(c['total_kg']):,} kg total weight, "
                f"{c['verified_pct']}% QA verified, {c['cost_per_kg']:.2f} BDT/kg freight friction."
            )
            candidates.append(c)
            seen_lot_tuples.add(tup)

    return candidates

def plan_aggregation(conn, buyer_id):
    buyer = conn.execute("SELECT * FROM buyers WHERE id=?", (buyer_id,)).fetchone()
    if not buyer: return None
    lots = conn.execute("SELECT * FROM lots ORDER BY id").fetchall()
    batch_map = {}
    for row in conn.execute("""
        SELECT bl.lot_id, b.code as batch_code
        FROM batch_lots bl
        JOIN batches b ON bl.batch_id = b.id
    """).fetchall():
        batch_map[row["lot_id"]] = row["batch_code"]

    eligible, excluded = [], []
    for l in lots:
        ld = dict(l)
        if l["id"] in batch_map:
            ld["batch_code"] = batch_map[l["id"]]
        r = exclusion_reason(ld, buyer, conn)
        if r:
            excluded.append((ld, r))
        else:
            eligible.append(ld)

    eligible_total_kg = sum(l["qty_kg"] for l in eligible)
    candidates = find_candidate_batches(conn, buyer, eligible)

    recommended = candidates[0] if candidates else None
    alternatives = candidates[1:] if len(candidates) > 1 else []

    feasible = bool(recommended)
    batch_total_kg = float(recommended["total_kg"]) if feasible else 0.0
    shortfall = max(0.0, float(buyer["min_qty"]) - eligible_total_kg) if not feasible else 0.0

    selected_lots = [dict(l) for l in recommended["lots"]] if feasible else []
    selected_ids = set(l["id"] for l in selected_lots)
    skipped_eligible = [dict(l) for l in eligible if l["id"] not in selected_ids]

    # Actionable shortfall diagnostic details
    shortfall_details = {
        "shortfall_kg": shortfall,
        "eligible_kg": eligible_total_kg,
        "target_kg": float(buyer["min_qty"]),
        "category": buyer["category"],
        "accepted_grades": buyer["accepted_grades"],
        "max_contamination": float(buyer["max_contamination"]),
        "location_name": buyer["location_name"],
        "service_radius_km": float(buyer["service_radius_km"]),
        "recommendation": (
            f"Network deficit of {int(shortfall):,} kg. Aggregate at least {int(shortfall):,} kg "
            f"additional unallocated {buyer['category']} (Grades: {buyer['accepted_grades']}, "
            f"max {buyer['max_contamination']}% contamination) within {int(buyer['service_radius_km'])} km "
            f"of {buyer['location_name']} to achieve commercial recycling scale."
        ) if shortfall > 0 else "Sufficient inventory available."
    }

    return {
        "buyer": dict(buyer),
        "selected": selected_lots,
        "excluded": [{"lot": dict(l), "reason": r} for l, r in excluded],
        "skipped_eligible": skipped_eligible,
        "eligible": [dict(l) for l in eligible],
        "eligible_kg": eligible_total_kg,
        "batch_kg": batch_total_kg,
        "total_kg": batch_total_kg if feasible else eligible_total_kg,
        "target_kg": float(buyer["min_qty"]),
        "shortfall_kg": shortfall,
        "feasible": feasible,
        # Multi-objective optimizer extensions
        "candidates": candidates,
        "recommended": recommended,
        "alternatives": alternatives,
        "shortfall_details": shortfall_details,
    }

# ---------- buyer matching (transparent scoring) ----------
def match_buyers(conn, category, grade, qty_kg, lat, lon):
    out = []
    for b in conn.execute("SELECT * FROM buyers").fetchall():
        reasons, score = [], 0
        if b["category"] == category:
            score += 40; reasons.append("+40 material category match")
        else:
            reasons.append("0 category mismatch"); continue
        if grade in b["accepted_grades"].split(","):
            score += 20; reasons.append("+20 grade accepted")
        else:
            reasons.append("0 grade not accepted")
        if b["min_qty"] <= qty_kg <= b["max_qty"]:
            score += 20; reasons.append("+20 quantity fit")
        else:
            reasons.append("0 quantity outside " + str(int(b["min_qty"])) + "-" + str(int(b["max_qty"])) + "kg")
        d = haversine(lat, lon, b["lat"], b["lon"])
        if d <= b["service_radius_km"]:
            score += int(max(0, 20 * (1 - d / b["service_radius_km"])))
            reasons.append("+%d within service area (%.0f km)" % (int(max(0,20*(1-d/b["service_radius_km"]))), d))
        else:
            reasons.append("0 outside service area (%.0f km)" % d)
        out.append({"buyer": dict(b), "score": score, "distance_km": round(d,1), "reasons": reasons})
    out.sort(key=lambda x: -x["score"])
    return out

# ---------- route planning (declared heuristic) ----------
def plan_route(conn, lot_ids, buyer_lat, buyer_lon, rate_per_km=120.0):
    pts = [dict(conn.execute("SELECT id,code,qty_kg,lat,lon,location_name FROM lots WHERE id=?", (i,)).fetchone()) for i in lot_ids]
    route, cur_lat, cur_lon, total = [], buyer_lat, buyer_lon, 0.0
    remaining = pts[:]
    while remaining:
        nxt = min(remaining, key=lambda p: haversine(cur_lat, cur_lon, p["lat"], p["lon"]))
        d = haversine(cur_lat, cur_lon, nxt["lat"], nxt["lon"])
        total += d; route.append((nxt, round(d,1)))
        cur_lat, cur_lon = nxt["lat"], nxt["lon"]
        remaining.remove(nxt)
    back = haversine(cur_lat, cur_lon, buyer_lat, buyer_lon)
    total += back
    return {"stops": route, "total_km": round(total,1), "return_km": round(back,1),
            "est_cost": round(total * rate_per_km), "rate_per_km": rate_per_km,
            "method": "Greedy nearest-neighbour heuristic (straight-line distance). Simulated - not traffic-aware."}

# ---------- misc helpers ----------
PALETTE = ["#153D32", "#2A7F7F", "#B8D96B", "#8A7967", "#3B82F6", "#F59E0B"]

CAT_SHORT = {
    "cotton": "Cotton",
    "polyester": "Polyester",
    "cotton-polyester blend": "Cotton-Poly",
    "cotton-polyester": "Cotton-Poly",
    "denim": "Denim",
    "mixed textile waste": "Mixed Waste",
    "mixed": "Mixed Waste"
}

def svg_bar(title, items, w=580, h=220, color="#10B981"):
    if not items: return "<p class='muted'>No inventory data available for chart.</p>"
    mx = max((v for _, v in items), default=1) or 1
    total = sum((v for _, v in items), 0) or 1
    n = len(items)
    
    # Left margin for Y-axis numbers
    y_axis_w = 48
    chart_right = w - 16
    plot_w = chart_right - y_axis_w
    bw = plot_w // max(n, 1)
    bar_w = min(48, max(22, bw - 22))
    
    chart_top = 28
    chart_bottom = h - 34
    chart_h = chart_bottom - chart_top
    max_bar_h = chart_h - 14
    
    out = [f"<svg viewBox='0 0 {w} {h}' class='chart' preserveAspectRatio='xMidYMid meet' role='img'>"]
    
    # Defs for gradients
    out.append("""<defs>
      <linearGradient id="bar-cotton-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#10B981"/>
        <stop offset="100%" stop-color="#047857"/>
      </linearGradient>
      <linearGradient id="bar-slate-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#2D3B52"/>
        <stop offset="100%" stop-color="#1E2738"/>
      </linearGradient>
    </defs>""")
    
    # Dynamic round ticks with clean upper bound
    if mx <= 500:
        top_val = 500
        ticks = [(1.0, "500"), (0.5, "250"), (0.0, "0")]
    elif mx <= 1000:
        top_val = 1000
        ticks = [(1.0, "1,000"), (0.75, "750"), (0.5, "500"), (0.25, "250"), (0.0, "0")]
    elif mx <= 1500:
        top_val = 1500
        ticks = [(1.0, "1,500"), (1000/1500, "1,000"), (500/1500, "500"), (0.0, "0")]
    elif mx <= 2000:
        top_val = 2000
        ticks = [(1.0, "2,000"), (0.75, "1,500"), (0.5, "1,000"), (0.25, "500"), (0.0, "0")]
    else:
        step = 1000 if mx > 3000 else 500
        top_val = int(math.ceil(mx / float(step)) * step)
        num_intervals = 4
        ticks = []
        for i in range(num_intervals, -1, -1):
            ratio = i / float(num_intervals)
            v = int(top_val * ratio)
            ticks.append((ratio, f"{v:,}"))
    
    for step, lbl in ticks:
        gy = chart_bottom - int(max_bar_h * step)
        out.append(f"<text x='{y_axis_w - 8}' y='{gy + 4}' font-size='10' font-weight='500' fill='#64748B' text-anchor='end'>{lbl}</text>")
        out.append(f"<line x1='{y_axis_w}' y1='{gy}' x2='{chart_right}' y2='{gy}' stroke='rgba(255,255,255,0.06)' stroke-dasharray='3 3' stroke-width='1'/>")
    
    # Baseline axis
    out.append(f"<line x1='{y_axis_w}' y1='{chart_bottom}' x2='{chart_right}' y2='{chart_bottom}' stroke='rgba(255,255,255,0.12)' stroke-width='1'/>")
    
    for i, (label, v) in enumerate(items):
        bh = int(max_bar_h * v / top_val)
        center_x = y_axis_w + i * bw + bw // 2
        bar_x = center_x - bar_w // 2
        bar_y = chart_bottom - max(4, bh)
        pct = int(round(100 * v / total))
        raw_key = label.strip().lower()
        disp_label = CAT_SHORT.get(raw_key, label.strip().title()[:12])
        
        is_cotton = "cotton" in raw_key and "blend" not in raw_key
        bar_fill = "url(#bar-cotton-grad)" if is_cotton else "url(#bar-slate-grad)"
        bar_stroke = "rgba(16, 185, 129, 0.4)" if is_cotton else "rgba(255,255,255,0.08)"
        
        # Bar rect
        out.append(f"<rect x='{bar_x}' y='{bar_y}' width='{bar_w}' height='{max(4, bh)}' fill='{bar_fill}' stroke='{bar_stroke}' stroke-width='1' rx='4'/>")
        # Bar value text above bar
        out.append(f"<text x='{center_x}' y='{bar_y - 6}' font-size='11' font-weight='600' fill='{('#10B981' if is_cotton else '#CBD5E1')}' text-anchor='middle'>{v:,} kg</text>")
        # Primary category label below baseline
        out.append(f"<text x='{center_x}' y='{chart_bottom + 16}' font-size='11.5' font-weight='500' fill='#94A3B8' text-anchor='middle'>{html.escape(disp_label)}</text>")
        
    out.append("</svg>")
    return "".join(out)

def svg_ring_gauge(pct, label="Verified Quality", sub="Declared & Human-Confirmed", size=130):
    r = 46
    c = 2 * math.pi * r
    pct_clamped = max(0, min(100, int(round(pct))))
    dash = (pct_clamped / 100) * c
    return (f"<div class='gauge-wrap'>"
            f"<svg width='{size}' height='{size}' viewBox='0 0 120 120' class='gauge-svg'>"
            f"<circle cx='60' cy='60' r='{r}' fill='none' stroke='#EAF0EC' stroke-width='12'/>"
            f"<circle cx='60' cy='60' r='{r}' fill='none' stroke='#153D32' stroke-width='12' "
            f"stroke-dasharray='{dash:.1f} {c:.1f}' stroke-linecap='round' transform='rotate(-90 60 60)'/>"
            f"<text x='60' y='58' class='gauge-num' text-anchor='middle'>{pct_clamped}%</text>"
            f"<text x='60' y='74' class='gauge-sub' text-anchor='middle'>Score</text>"
            f"</svg>"
            f"<div class='gauge-meta'><div class='gauge-label'>{html.escape(label)}</div>"
            f"<div class='gauge-desc'>{html.escape(sub)}</div></div>"
            f"</div>")

def add_event(conn, batch_id, desc):
    conn.execute("INSERT INTO events(batch_id,ts,description) VALUES(?,?,?)", (batch_id, NOW(), desc))

STATUS_LABEL = {"verified": "Verified", "pending": "Pending verification", "simulated": "Simulated demo data"}

