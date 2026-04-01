from http.server import HTTPServer, BaseHTTPRequestHandler
import json, psycopg2, urllib.request, urllib.error, time
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DB = {
    "host": "guacdb", "port": 5432,
    "dbname": "guacamole_db", "user": "guacamole_user", "password": "guacamole_pass"
}
GUAC_URL  = "http://172.19.0.3:8080/guacamole"
GUAC_USER = "guacadmin"
GUAC_PASS = "guacadmin"

# In-memory role store (extend with DB-backed table if needed)
# Format: { "email": "ADMIN" | "TEAM_LEAD" | "USER" }
ROLES = {"guacadmin": "ADMIN"}  # populated from DB or set here

# Lab capacity limits  { connection_name: max_users }
LAB_LIMITS = {}  # e.g. {"Linux SSH": 30}

# ─── DB HELPERS ──────────────────────────────────────────────────────────────
def db_conn():
    return psycopg2.connect(**DB)

def db_query(sql, params=None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

def db_exec(sql, params=None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()

# ─── GUACAMOLE API HELPERS ───────────────────────────────────────────────────
def get_guac_token():
    data = f"username={GUAC_USER}&password={GUAC_PASS}".encode()
    req  = urllib.request.Request(f"{GUAC_URL}/api/tokens", data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())["authToken"]

def guac_get(path, token):
    req = urllib.request.Request(f"{GUAC_URL}{path}?token={token}")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

def guac_delete(path, token):
    req = urllib.request.Request(
        f"{GUAC_URL}{path}?token={token}", method="DELETE"
    )
    try:
        with urllib.request.urlopen(req, timeout=5): pass
        return True
    except Exception:
        return False

# ─── ACTIVE SESSIONS ─────────────────────────────────────────────────────────
def get_active_sessions():
    try:
        token   = get_guac_token()
        results = []
        for ds in ["postgresql", "postgresql-shared"]:
            try:
                active = guac_get(f"/api/session/data/{ds}/activeConnections", token)
                conns  = guac_get(f"/api/session/data/{ds}/connections", token)
                for sid, s in active.items():
                    cname = conns.get(s.get("connectionIdentifier",""), {}).get("name","")
                    results.append({
                        "session_id":  sid,
                        "datasource":  ds,
                        "username":    s.get("username",""),
                        "lab":         cname,
                        "start_date":  s.get("startDate",""),
                        "remote_host": s.get("remoteHost",""),
                        "connection_id": s.get("connectionIdentifier","")
                    })
            except Exception:
                pass
        # Deduplicate
        seen, unique = set(), []
        for r in results:
            k = (r["username"], r["lab"])
            if k not in seen:
                seen.add(k)
                unique.append(r)
        return unique
    except Exception:
        # DB fallback
        rows = db_query("""
            SELECT '' as session_id, 'db' as datasource,
                   e.name as username, c.connection_name as lab,
                   h.start_date::text, h.remote_host,
                   h.connection_id::text as connection_id
            FROM guacamole_connection_history h
            JOIN guacamole_entity e ON h.user_id=e.entity_id
            JOIN guacamole_connection c ON h.connection_id=c.connection_id
            WHERE h.end_date IS NULL ORDER BY h.start_date DESC
        """)
        return rows

# ─── KILL SESSION ─────────────────────────────────────────────────────────────
def kill_session(session_id, datasource):
    try:
        token = get_guac_token()
        return guac_delete(
            f"/api/session/data/{datasource}/activeConnections/{session_id}", token
        )
    except Exception as e:
        return False

# ─── USER PROFILE ─────────────────────────────────────────────────────────────
def get_user_profile(username):
    # Assigned labs
    labs = db_query("""
        SELECT c.connection_name as name, c.protocol
        FROM guacamole_connection_permission cp
        JOIN guacamole_entity e ON cp.entity_id=e.entity_id
        JOIN guacamole_connection c ON cp.connection_id=c.connection_id
        WHERE e.name=%s AND e.type='USER'
    """, (username,))

    # Session history (last 30)
    history = db_query("""
        SELECT c.connection_name as lab, h.start_date::text, h.end_date::text,
               h.remote_host,
               CASE WHEN h.end_date IS NULL THEN 'active'
                    ELSE 'completed' END as status,
               CASE WHEN h.end_date IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (h.end_date - h.start_date))::int
                    ELSE NULL END as duration_sec
        FROM guacamole_connection_history h
        JOIN guacamole_entity e ON h.user_id=e.entity_id
        JOIN guacamole_connection c ON h.connection_id=c.connection_id
        WHERE e.name=%s ORDER BY h.start_date DESC LIMIT 30
    """, (username,))

    # Stats
    stats = db_query("""
        SELECT COUNT(*) as total_sessions,
               COUNT(CASE WHEN end_date IS NULL THEN 1 END) as active_sessions,
               MAX(start_date)::text as last_login,
               SUM(CASE WHEN end_date IS NOT NULL
                   THEN EXTRACT(EPOCH FROM (end_date - start_date))::int
                   ELSE 0 END) as total_time_sec
        FROM guacamole_connection_history h
        JOIN guacamole_entity e ON h.user_id=e.entity_id
        WHERE e.name=%s
    """, (username,))

    # Most used labs
    top_labs = db_query("""
        SELECT c.connection_name as lab, COUNT(*) as count
        FROM guacamole_connection_history h
        JOIN guacamole_entity e ON h.user_id=e.entity_id
        JOIN guacamole_connection c ON h.connection_id=c.connection_id
        WHERE e.name=%s GROUP BY c.connection_name ORDER BY count DESC LIMIT 5
    """, (username,))

    return {
        "username":  username,
        "role":      ROLES.get(username, "USER"),
        "labs":      labs,
        "history":   history,
        "stats":     stats[0] if stats else {},
        "top_labs":  top_labs
    }

# ─── LABS WITH STATS ──────────────────────────────────────────────────────────
def get_labs_with_stats():
    labs = db_query("""
        SELECT c.connection_id as id, c.connection_name as name, c.protocol,
               COUNT(DISTINCT cp.entity_id) as assigned_users
        FROM guacamole_connection c
        LEFT JOIN guacamole_connection_permission cp ON c.connection_id=cp.connection_id
        GROUP BY c.connection_id, c.connection_name, c.protocol
        ORDER BY c.connection_name
    """)
    active = get_active_sessions()
    amap   = {}
    for s in active:
        amap.setdefault(s["lab"], []).append(s["username"])
    for lab in labs:
        lab["active_users"]  = len(amap.get(lab["name"], []))
        lab["active_list"]   = amap.get(lab["name"], [])
        lab["max_users"]     = LAB_LIMITS.get(lab["name"], 0)
        lab["enabled"]       = True   # could store in DB
        overload = lab["max_users"] > 0 and lab["active_users"] >= lab["max_users"]
        lab["overloaded"]    = overload
    return labs

# ─── ALERTS ───────────────────────────────────────────────────────────────────
def get_alerts():
    alerts = []
    labs   = get_labs_with_stats()
    active = get_active_sessions()

    # Overloaded labs
    for lab in labs:
        if lab.get("overloaded"):
            alerts.append({
                "type":    "error",
                "icon":    "🔴",
                "title":   f"Lab overloaded: {lab['name']}",
                "message": f"{lab['active_users']}/{lab['max_users']} users connected"
            })

    # High usage (>80% of limit)
    for lab in labs:
        if lab["max_users"] > 0 and not lab.get("overloaded"):
            pct = lab["active_users"] / lab["max_users"]
            if pct >= 0.8:
                alerts.append({
                    "type":    "warning",
                    "icon":    "🟡",
                    "title":   f"Lab near capacity: {lab['name']}",
                    "message": f"{lab['active_users']}/{lab['max_users']} users"
                })

    # Long running sessions (>4 hours)
    now = time.time() * 1000
    for s in active:
        try:
            start = s.get("start_date", 0)
            if isinstance(start, str):
                start = int(start) if start.isdigit() else 0
            if start and (now - start) > 4 * 3600 * 1000:
                alerts.append({
                    "type":    "warning",
                    "icon":    "⏱",
                    "title":   f"Long session: {s['username']}",
                    "message": f"Connected to {s['lab']} for over 4 hours"
                })
        except Exception:
            pass

    # No active sessions at all (info)
    if not active:
        alerts.append({
            "type":    "info",
            "icon":    "ℹ️",
            "title":   "No active sessions",
            "message": "All labs are idle right now"
        })

    return alerts

# ─── CONNECTION HISTORY (enhanced) ────────────────────────────────────────────
def get_history(limit=100):
    return db_query(f"""
        SELECT e.name as username, c.connection_name as lab,
               h.start_date::text, h.end_date::text,
               h.remote_host,
               CASE WHEN h.end_date IS NULL THEN 'active' ELSE 'completed' END as status,
               CASE WHEN h.end_date IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (h.end_date - h.start_date))::int
                    ELSE NULL END as duration_sec
        FROM guacamole_connection_history h
        JOIN guacamole_entity e ON h.user_id=e.entity_id
        JOIN guacamole_connection c ON h.connection_id=c.connection_id
        ORDER BY h.start_date DESC LIMIT {int(limit)}
    """)

# ─── HTTP HANDLER ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json(self, data, code=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", len(body))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def route(self):
        p = self.path.split("?")[0].rstrip("/")
        return p

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        try:
            p = self.route()

            # GET /users
            if p == "/users":
                data = db_query("""
                    SELECT e.name as username,
                           array_agg(DISTINCT c.connection_name)
                               FILTER (WHERE c.connection_name IS NOT NULL) as labs
                    FROM guacamole_entity e
                    LEFT JOIN guacamole_connection_permission cp ON e.entity_id=cp.entity_id
                    LEFT JOIN guacamole_connection c ON cp.connection_id=c.connection_id
                    WHERE e.type='USER'
                    GROUP BY e.name ORDER BY e.name
                """)
                for r in data:
                    if r["labs"] is None: r["labs"] = []
                    r["role"] = ROLES.get(r["username"], "USER")
                self.send_json(data)

            # GET /labs
            elif p == "/labs":
                self.send_json(get_labs_with_stats())

            # GET /active
            elif p == "/active":
                self.send_json(get_active_sessions())

            # GET /history
            elif p == "/history":
                self.send_json(get_history(100))

            # GET /alerts
            elif p == "/alerts":
                self.send_json(get_alerts())

            # GET /profile/<username>
            elif p.startswith("/profile/"):
                username = urllib.request.unquote(p[9:])
                self.send_json(get_user_profile(username))

            # GET /roles
            elif p == "/roles":
                self.send_json(ROLES)

            # GET /stats  (dashboard summary)
            elif p == "/stats":
                users   = db_query("SELECT COUNT(*) as n FROM guacamole_entity WHERE type='USER'")
                labs    = db_query("SELECT COUNT(*) as n FROM guacamole_connection")
                assigns = db_query("SELECT COUNT(*) as n FROM guacamole_connection_permission")
                active  = get_active_sessions()
                self.send_json({
                    "total_users":       users[0]["n"]   if users   else 0,
                    "total_labs":        labs[0]["n"]    if labs    else 0,
                    "total_assignments": assigns[0]["n"] if assigns else 0,
                    "active_sessions":   len(active),
                    "alerts":            len(get_alerts())
                })

            else:
                self.send_json({"error": "Not found"}, 404)

        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        try:
            body   = self.read_body()
            action = body.get("action", "")
            p      = self.route()

            # POST /manage  (assign / remove / bulk_assign / bulk_remove_all)
            if p == "/manage":

                if action == "assign":
                    username, lab = body["username"], body["lab"]
                    db_exec("""
                        INSERT INTO guacamole_connection_permission
                            (entity_id, connection_id, permission)
                        SELECT e.entity_id, c.connection_id,
                               'READ'::guacamole_object_permission_type
                        FROM guacamole_entity e, guacamole_connection c
                        WHERE e.name=%s AND c.connection_name=%s
                        ON CONFLICT DO NOTHING
                    """, (username, lab))
                    self.send_json({"ok": True, "message": f"Assigned {lab} to {username}"})

                elif action == "remove":
                    username, lab = body["username"], body["lab"]
                    db_exec("""
                        DELETE FROM guacamole_connection_permission
                        WHERE entity_id=(SELECT entity_id FROM guacamole_entity WHERE name=%s)
                          AND connection_id=(SELECT connection_id FROM guacamole_connection
                                             WHERE connection_name=%s)
                    """, (username, lab))
                    self.send_json({"ok": True, "message": f"Removed {lab} from {username}"})

                elif action == "bulk_assign":
                    lab      = body["lab"]
                    userlist = body.get("users")   # optional: list of usernames
                    if userlist:
                        for u in userlist:
                            db_exec("""
                                INSERT INTO guacamole_connection_permission
                                    (entity_id, connection_id, permission)
                                SELECT e.entity_id, c.connection_id,
                                       'READ'::guacamole_object_permission_type
                                FROM guacamole_entity e, guacamole_connection c
                                WHERE e.name=%s AND c.connection_name=%s
                                  AND e.type='USER'
                                ON CONFLICT DO NOTHING
                            """, (u, lab))
                    else:
                        db_exec("""
                            INSERT INTO guacamole_connection_permission
                                (entity_id, connection_id, permission)
                            SELECT e.entity_id, c.connection_id,
                                   'READ'::guacamole_object_permission_type
                            FROM guacamole_entity e, guacamole_connection c
                            WHERE e.type='USER' AND c.connection_name=%s
                            ON CONFLICT DO NOTHING
                        """, (lab,))
                    self.send_json({"ok": True, "message": f"Bulk assigned {lab}"})

                elif action == "bulk_remove":
                    lab      = body.get("lab")
                    userlist = body.get("users")
                    if lab and userlist:
                        for u in userlist:
                            db_exec("""
                                DELETE FROM guacamole_connection_permission
                                WHERE entity_id=(SELECT entity_id FROM guacamole_entity WHERE name=%s)
                                  AND connection_id=(SELECT connection_id FROM guacamole_connection
                                                     WHERE connection_name=%s)
                            """, (u, lab))
                    elif lab:
                        db_exec("""
                            DELETE FROM guacamole_connection_permission
                            WHERE connection_id=(SELECT connection_id FROM guacamole_connection
                                                 WHERE connection_name=%s)
                        """, (lab,))
                    else:
                        db_exec("DELETE FROM guacamole_connection_permission")
                    self.send_json({"ok": True})

                elif action == "bulk_remove_all":
                    db_exec("DELETE FROM guacamole_connection_permission")
                    self.send_json({"ok": True, "message": "All assignments removed"})

                else:
                    self.send_json({"error": "Unknown action"}, 400)

            # POST /kill  { session_id, datasource }
            elif p == "/kill":
                sid = body.get("session_id")
                ds  = body.get("datasource", "postgresql")
                ok  = kill_session(sid, ds)
                self.send_json({"ok": ok})

            # POST /roles  { username, role }
            elif p == "/roles":
                username = body["username"]
                role     = body["role"]
                if role not in ("ADMIN", "TEAM_LEAD", "USER"):
                    self.send_json({"error": "Invalid role"}, 400)
                    return
                ROLES[username] = role
                self.send_json({"ok": True})

            # POST /limits  { lab, max_users }
            elif p == "/limits":
                lab       = body["lab"]
                max_users = int(body["max_users"])
                LAB_LIMITS[lab] = max_users
                self.send_json({"ok": True})

            else:
                self.send_json({"error": "Not found"}, 404)

        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def log_message(self, *args): pass

# ─── MAIN ─────────────────────────────────────────────────────────────────────
print("Dashboard API v3 running on :9091")
print("Endpoints: /users /labs /active /history /alerts /profile/<u> /stats /roles")
print("POST: /manage /kill /roles /limits")
HTTPServer(("0.0.0.0", 9091), Handler).serve_forever()
