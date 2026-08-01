"""Graph engine extension methods for Stage 47/55/59/60/62/63/64."""
from __future__ import annotations

import copy
import difflib
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


class ConflictError(Exception):
    def __init__(self, resource, base, ours, theirs, clock_base, clock_theirs):
        self.resource = resource
        self.base = base
        self.ours = ours
        self.theirs = theirs
        self.clock_base = clock_base
        self.clock_theirs = clock_theirs

    def to_dict(self):
        return {
            "status": "conflict",
            "resource": self.resource,
            "base": self.base,
            "ours": self.ours,
            "theirs": self.theirs,
            "clock_base": self.clock_base,
            "clock_theirs": self.clock_theirs,
        }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------
def _sys_meta(node_or_edge):
    if not isinstance(node_or_edge, dict):
        return {}
    if "meta" in node_or_edge:
        m = node_or_edge.setdefault("meta", {})
        if not isinstance(m, dict):
            node_or_edge["meta"] = {}
        return node_or_edge["meta"]
    return node_or_edge


def _get_rev(resource):
    return _sys_meta(resource).get("_rev", 0)


def _get_clock(resource):
    return dict(_sys_meta(resource).get("_clock", {}))


def _bump(resource, actor):
    m = _sys_meta(resource)
    m["_rev"] = m.get("_rev", 0) + 1
    clock = dict(m.get("_clock", {}))
    clock[actor] = clock.get(actor, 0) + 1
    m["_clock"] = clock
    m["_modified_by"] = actor


def _clock_compare(a, b):
    dom_a = all(a.get(k, 0) >= b.get(k, 0) for k in set(a) | set(b))
    dom_b = all(b.get(k, 0) >= a.get(k, 0) for k in set(a) | set(b))
    if dom_a and not dom_b:
        return 1
    if dom_b and not dom_a:
        return -1
    return 0


def _find_node(engine, node_id):
    nodes = getattr(engine._graph, "_nodes", {})
    if isinstance(nodes, dict):
        return nodes.get(node_id)
    for n in nodes:
        if isinstance(n, dict) and n.get("id") == node_id:
            return n
    return None


def _find_edge_index(engine, edge_id):
    for i, e in enumerate(getattr(engine._graph, "_edges", [])):
        if isinstance(e, dict) and e.get("_id") == edge_id:
            return i
    return -1


def _detect_conflict(engine, resource, base_revision, actor):
    if base_revision is None:
        return False, None
    current_rev = _get_rev(resource)
    if current_rev == 0 or base_revision >= current_rev:
        return False, None
    report = {
        "resource": resource.get("id") or resource.get("_id"),
        "current_rev": current_rev,
        "base_revision": base_revision,
        "current_clock": _get_clock(resource),
        "current_content": resource.get("content") or resource.get("label") or resource.get("relation"),
        "current_modified_by": _sys_meta(resource).get("_modified_by"),
    }
    return True, report


def _apply_strategy(engine, resource, incoming, base_revision, strategy, actor):
    is_conflict, report = _detect_conflict(engine, resource, base_revision, actor)
    if not is_conflict:
        return incoming
    if strategy == "reject":
        raise ConflictError(
            report["resource"],
            base_revision,
            incoming,
            report["current_content"],
            {},
            report["current_clock"],
        )
    if strategy == "lww":
        cmp = _clock_compare(
            incoming.get("meta", {}).get("_clock", {actor: 1}),
            report["current_clock"],
        )
        if cmp == 1 or (cmp == 0 and actor > report.get("current_modified_by", "")):
            return incoming
        return resource
    if strategy == "content_merge":
        base_content = _fetch_base_content(engine, report["resource"], base_revision)
        ours = incoming.get("content", incoming.get("label", ""))
        theirs = report["current_content"] or ""
        merged = _three_way_merge(engine, base_content, ours, theirs)
        result = copy.deepcopy(resource)
        result["content"] = merged
        return result
    if strategy == "structural_merge":
        return copy.deepcopy(resource)
    raise ValueError(f"Unknown strategy: {strategy}")


def _fetch_base_content(engine, resource_id, base_revision):
    node = _find_node(engine, resource_id)
    if node:
        if base_revision in (0, None):
            return _sys_meta(node).get("_original_content") or node.get("content") or node.get("label") or ""
        return node.get("content") or node.get("label") or ""
    return ""


def _three_way_merge(engine, base, ours, theirs):
    base_lines = base.splitlines(True)
    ours_lines = ours.splitlines(True)
    theirs_lines = theirs.splitlines(True)
    ops_o = list(difflib.SequenceMatcher(None, base_lines, ours_lines).get_opcodes())
    ops_t = list(difflib.SequenceMatcher(None, base_lines, theirs_lines).get_opcodes())
    return _merge_hunks(engine, base_lines, ours_lines, theirs_lines, ops_o, ops_t)


def _merge_hunks(engine, base, ours, theirs, ops_o, ops_t):
    def changed_ranges(ops):
        return [(i1, i2) for tag, i1, i2, _, _ in ops if tag != "equal"]

    co = changed_ranges(ops_o)
    ct = changed_ranges(ops_t)
    overlap = any(
        not (a2 <= b1 or b2 <= a1)
        for a1, a2 in co
        for b1, b2 in ct
    )
    if not overlap:
        result = []
        i = 0
        while i < len(base):
            in_o = any(a1 <= i < a2 for a1, a2 in co)
            in_t = any(b1 <= i < b2 for b1, b2 in ct)
            if in_o and not in_t:
                for tag, o1, o2, j1, j2 in ops_o:
                    if o1 <= i < o2 and tag != "equal":
                        result.extend(ours[j1:j2])
                        i = o2
                        break
            elif in_t and not in_o:
                for tag, o1, o2, j1, j2 in ops_t:
                    if o1 <= i < o2 and tag != "equal":
                        result.extend(theirs[j1:j2])
                        i = o2
                        break
            else:
                result.append(base[i])
                i += 1
        return "".join(result)
    return (
        "<<<<<<< ours\n"
        + "".join(ours)
        + "=======\n"
        + "".join(theirs)
        + ">>>>>>> theirs\n"
    )


# ------------------------------------------------------------------
# Stage 47/55/59/60/62/63/64 public implementations
# ------------------------------------------------------------------
def export_graph(engine, format="json", include_context=True):
    snap = engine._snapshot()
    nodes = list(snap.get("nodes", []))
    edges = list(snap.get("edges", []))
    if not include_context:
        nodes = [n for n in nodes if not n["id"].startswith(("user:", "session:", "query:"))]
        edges = [
            e
            for e in edges
            if not e.get("from", "").startswith(("user:", "session:", "query:"))
            and not e.get("to", "").startswith(("user:", "session:", "query:"))
        ]
    payload = {"nodes": nodes, "edges": edges}
    return {
        "ok": True,
        "format": format,
        "data": json.dumps(payload, ensure_ascii=False),
        "nodes": len(nodes),
        "edges": len(edges),
    }


def import_graph(engine, payload, format="json", merge_strategy="upsert"):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": str(exc)}
    incoming_nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
    incoming_edges = payload.get("edges", []) if isinstance(payload, dict) else []
    current = engine._snapshot()
    current_ids = {n["id"] for n in current.get("nodes", []) if isinstance(n, dict)}
    current_edges = {
        (e.get("from"), e.get("to"), e.get("relation"))
        for e in current.get("edges", [])
        if isinstance(e, dict)
    }
    added_nodes = 0
    skipped_nodes = 0
    for node in incoming_nodes:
        nid = node.get("id")
        if not nid:
            continue
        if nid in current_ids:
            skipped_nodes += 1
            continue
        label = node.get("label") or node.get("title") or nid
        meta = node.get("meta") or {}
        try:
            engine._graph.add_node(nid, label, meta)
        except Exception:
            pass
        added_nodes += 1
    added_edges = 0
    skipped_edges = 0
    for edge in incoming_edges:
        key = (edge.get("from"), edge.get("to"), edge.get("relation"))
        if key in current_edges:
            skipped_edges += 1
            continue
        if key[0] and key[1]:
            try:
                engine._graph.add_edge(key[0], key[1], key[2] or "links")
            except Exception:
                pass
            added_edges += 1
    return {
        "ok": True,
        "nodes_added": added_nodes,
        "nodes_skipped": skipped_nodes,
        "edges_added": added_edges,
        "edges_skipped": skipped_edges,
    }


def backup_graph(engine):
    if not engine._fs or not engine._snapshot_path:
        return {"ok": False, "error": "filesystem or snapshot path not configured"}
    path = f"{engine._snapshot_path}.backup.{int(time.time())}.json"
    try:
        engine._fs.write_content(path, json.dumps(engine._snapshot(), ensure_ascii=False))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": path}


def restore_graph(engine, path):
    if not engine._fs:
        return {"ok": False, "error": "filesystem not configured"}
    try:
        raw = engine._fs.read_content(path)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        engine._graph.clear()
        for n in payload.get("nodes", []):
            if isinstance(n, dict) and n.get("id"):
                engine._graph.add_node(
                    n["id"],
                    n.get("label") or n.get("id"),
                    n.get("meta") or {},
                )
        for e in payload.get("edges", []):
            if isinstance(e, dict) and e.get("from") and e.get("to"):
                engine._graph.add_edge(
                    e["from"], e["to"], e.get("relation") or "links"
                )
    except Exception:
        pass
    engine._maybe_snapshot()
    snap = engine._snapshot()
    return {
        "ok": True,
        "restored_nodes": len(snap.get("nodes", [])),
        "restored_edges": len(snap.get("edges", [])),
    }


def find_hidden_connections(engine, threshold=0.5, limit=20):
    snap = engine._snapshot()
    nodes = {n["id"]: n for n in snap.get("nodes", []) if isinstance(n, dict)}
    edges = snap.get("edges", [])
    content_ids = [nid for nid in nodes if not nid.startswith(("user:", "session:", "query:"))]
    degree = {nid: 0 for nid in content_ids}
    succ = {nid: set() for nid in content_ids}
    pred = {nid: set() for nid in content_ids}
    existing = set()
    for e in edges:
        if not isinstance(e, dict):
            continue
        f, t, r = e.get("from"), e.get("to"), e.get("relation")
        if f in degree and t in degree and r not in {"user_query", "query_hit", "interest"}:
            degree[f] += 1
            degree[t] += 1
            succ[f].add(t)
            pred[t].add(f)
        existing.add((f, t, r))

    def neighbors(nid):
        return succ.get(nid, set()) | pred.get(nid, set())

    seen = []
    for src in content_ids:
        src_neighbors = neighbors(src)
        for cand in content_ids:
            if cand <= src:
                continue
            if (src, cand, "links") in existing or (cand, src, "links") in existing:
                continue
            common = src_neighbors & neighbors(cand)
            adamic_adar = sum(1 / max(degree[x], 1) for x in common) if common else 0.0
            src_label = (nodes.get(src, {}) or {}).get("label", src)
            cand_label = (nodes.get(cand, {}) or {}).get("label", cand)
            src_tokens = set(re.findall(r"\w+", src_label.lower()))
            cand_tokens = set(re.findall(r"\w+", cand_label.lower()))
            token_union = src_tokens | cand_tokens
            content_bonus = 0.5 * len(src_tokens & cand_tokens) / len(token_union) if token_union else 0.0
            max_aa = max(degree[src], degree[cand], 1)
            score = min((adamic_adar + content_bonus) / max_aa, 1.0)
            if score >= threshold and (common or content_bonus > 0):
                seen.append(
                    {
                        "from": src,
                        "to": cand,
                        "score": round(score, 4),
                        "reason": "shared neighbors + title overlap",
                    }
                )
    seen.sort(key=lambda x: x["score"], reverse=True)
    return {"ok": True, "pairs": seen[:limit], "count": min(limit, len(seen))}


def apply_suggested_link(engine, from_node, to_node, relation="links"):
    key = (from_node, to_node, relation)
    existing = {
        (e.get("from"), e.get("to"), e.get("relation"))
        for e in engine._snapshot().get("edges", [])
        if isinstance(e, dict)
    }
    created = key not in existing
    if created:
        try:
            engine._graph.add_edge(from_node, to_node, relation)
        except Exception:
            pass
        engine._maybe_snapshot()
    return {"ok": True, "from": from_node, "to": to_node, "relation": relation, "created": created}


def query_dsl(engine, query_string, session_id=None):
    start = time.perf_counter()
    query_string = (query_string or "").strip()
    if not query_string:
        return {"ok": False, "error": "empty query"}
    tokens = [t for t in re.findall(r'"[^"]*"|\S+', query_string.strip()) if t]
    if not tokens:
        return {"ok": False, "error": "unknown query type"}
    upper = query_string.upper()
    try:
        if upper.startswith("MATCH"):
            out = _match_query(engine, tokens)
        elif upper.startswith("PATH FROM") and " TO " in upper:
            out = _path_query(engine, query_string)
        elif upper.strip() == "HEALTH":
            out = {**engine.graph_health_report(), "query_type": "health", "ok": True}
        elif upper.startswith("NOTIFICATIONS"):
            out = engine.list_notifications(acknowledged=False, limit=50)
            out["query_type"] = "notifications"
        elif upper.startswith("SUGGESTIONS FOR"):
            node_id = tokens[2].strip('"') if len(tokens) > 2 else ""
            r = engine.find_hidden_connections(threshold=0.3, limit=20)
            filtered = [
                p for p in r.get("pairs", []) if p.get("from") == node_id or p.get("to") == node_id
            ]
            out = {"ok": True, "query_type": "suggestions", "results": filtered, "count": len(filtered)}
        else:
            return {"ok": False, "error": "unknown query type"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    out.setdefault("results", [])
    out.setdefault("count", len(out.get("results", [])) if isinstance(out.get("results"), list) else 0)
    out["execution_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return out


def _match_query(engine, tokens):
    snap = engine._snapshot()
    nodes = {n["id"]: n for n in snap.get("nodes", []) if isinstance(n, dict)}
    edges = snap.get("edges", [])
    return_parts = ["*"]
    for i, token in enumerate(tokens):
        if token.upper() == "RETURN":
            return_parts = [p.strip() for p in " ".join(tokens[i + 1:]).split(",") if p.strip()]
            break
    results = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        src, dst = e.get("from"), e.get("to")
        if not src or not dst:
            continue
        if src not in nodes or dst not in nodes:
            continue
        if return_parts == ["*"]:
            results.append({"a": src, "b": dst, "r": e.get("relation")})
        else:
            row = {}
            for part in return_parts:
                if part == "a":
                    row["a"] = src
                elif part == "b":
                    row["b"] = dst
                elif part == "r.relation":
                    row["r.relation"] = e.get("relation")
                elif part == "n.id":
                    row["n.id"] = src
            results.append(row)
    return {"ok": True, "query_type": "match", "results": results, "count": len(results)}


def _path_query(engine, query_string):
    upper = query_string.upper()
    if not upper.startswith("PATH FROM") or " TO " not in upper:
        return {"ok": False, "error": "invalid PATH query"}
    original = query_string.strip()
    from_part = original.split(" FROM ", 1)[1].split(" TO ", 1)[0]
    to_part = original.split(" TO ", 1)[1].strip()
    to_part = to_part.split(" MAX ", 1)[0].strip()
    from_node = from_part.strip().strip('"')
    to_node = to_part.strip().strip('"')
    path = engine.path(from_node, to_node, max_depth=10)
    if path:
        return {"ok": True, "query_type": "path", "path": path, "results": [{"nodes": path}], "count": 1}
    return {"ok": False, "query_type": "path", "error": "no path found", "results": [], "count": 0}


def rebuild_semantic_index(engine):
    if not engine._semantic_index:
        return {"ok": False, "error": "semantic index not configured"}
    docs = []
    for n in engine._snapshot().get("nodes", []):
        if n.get("id", "").startswith(("user:", "session:", "query:", "metric:", "branch:", "queue:")):
            continue
        text = " ".join(re.findall(r"\w+", (n.get("label") or n.get("id") or "").lower()))
        docs.append({"id": n.get("id"), "text": text})
    try:
        engine._semantic_index.build_or_update(docs)
        return {"ok": True, "documents": len(docs)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def semantic_similarity(engine, node_a, node_b):
    snap = engine._snapshot()
    nodes = {n["id"]: n for n in snap.get("nodes", []) if isinstance(n, dict)}
    if node_a not in nodes or node_b not in nodes:
        return 0.0
    tokens_a = set(re.findall(r"\w+", (nodes[node_a].get("label") or node_a).lower()))
    tokens_b = set(re.findall(r"\w+", (nodes[node_b].get("label") or node_b).lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    return round(len(tokens_a & tokens_b) / len(tokens_a | tokens_b), 4)


def run_maintenance_cycle(engine, dry_run=True, auto_cleanup_orphans=True, auto_apply_suggestions=0, notify=True):
    ts_start = time.time()
    health = engine.graph_health_report()
    new_notif_count = 0
    if notify:
        notif = engine.check_and_notify()
        new_notif_count = int(notif.get("new_notifications", 0))
    cleanup_result = {"removed": 0, "skipped": True}
    if auto_cleanup_orphans and health.get("orphan_count", 0) > 0 and not dry_run:
        cleanup_result = engine.cleanup_orphans(dry_run=False)
        if isinstance(cleanup_result, dict):
            cleanup_result = {"removed": int(cleanup_result.get("removed", 0)), "skipped": False}
    suggestions_result = {"scanned": 0, "applied": 0}
    if auto_apply_suggestions > 0 and not dry_run:
        candidate_limit = max(1, auto_apply_suggestions * 5)
        suggestions = engine.find_hidden_connections(threshold=0.15, limit=candidate_limit).get("pairs", [])
        suggestions_result["scanned"] = len(suggestions)
        for pair in suggestions:
            if suggestions_result["applied"] >= auto_apply_suggestions:
                break
            from_node, to_node = pair.get("from"), pair.get("to")
            if not from_node or not to_node:
                continue
            existing = {
                (e.get("from"), e.get("to"), e.get("relation"))
                for e in engine._snapshot().get("edges", [])
                if isinstance(e, dict)
            }
            if (from_node, to_node, "links") in existing:
                continue
            engine.apply_suggested_link(from_node, to_node, "links")
            suggestions_result["applied"] += 1
    snapshot_triggered = False
    if not dry_run and (cleanup_result.get("removed", 0) > 0 or suggestions_result.get("applied", 0) > 0):
        engine._maybe_snapshot()
        snapshot_triggered = True
    mutations = not dry_run and (
        cleanup_result.get("removed", 0) > 0 or suggestions_result.get("applied", 0) > 0
    )
    log_entry = {
        "ts": ts_start,
        "dry_run": dry_run,
        "steps": {
            "health": {
                "orphan_count": int(health.get("orphan_count", 0)),
                "broken_count": int(health.get("broken_count", 0)),
                "density": health.get("density", 0.0),
            },
            "notifications": {"new": new_notif_count},
            "cleanup": cleanup_result,
            "suggestions": suggestions_result,
            "snapshot": {"triggered": snapshot_triggered},
        },
        "mutations": mutations,
    }
    if not hasattr(engine, "_maintenance_log"):
        engine._maintenance_log = []
    engine._maintenance_log.append(log_entry)
    return {
        "ok": True,
        "dry_run": dry_run,
        "steps": log_entry["steps"],
        "mutations_occurred": mutations,
        "duration_ms": round((time.time() - ts_start) * 1000, 2),
    }


def get_maintenance_history(engine, limit=10):
    history = list(reversed(getattr(engine, "_maintenance_log", [])[-max(0, limit):]))
    return {"ok": True, "history": history}


def configure_maintenance(engine, config):
    if not isinstance(config, dict):
        config = {}
    engine._maintenance_config = {**getattr(engine, "_maintenance_config", {}), **config}
    return {"ok": True, "config": dict(engine._maintenance_config)}


def check_and_notify(engine, session_id=None):
    health = engine.graph_health_report()
    notifications = []
    orphan_count = int(health.get("orphan_count", 0))
    if orphan_count:
        notifications.append(
            {
                "id": f"health-orphan-{int(time.time())}",
                "type": "health",
                "message": f"Found {orphan_count} orphan nodes.",
                "severity": "warn",
                "acknowledged": False,
            }
        )
    if session_id:
        ctx = engine.get_session_context(session_id, depth=2)
        interest_ids = []
        for item in ctx.get("interest_profile", [])[:5]:
            node_id = item.get("node")
            interest_ids.append(node_id)
            related = engine.forward_links(node_id) + engine.backlinks(node_id)
            related = [x for x in related if x and x != node_id][:2]
            related_str = ", ".join(related) if related else node_id
            notifications.append(
                {
                    "id": f"interest-{session_id}-{node_id}-{int(time.time() * 1000)}",
                    "type": "interest",
                    "message": f"Suggested follow-up for {item.get('title') or node_id}; related: {related_str}",
                    "severity": "info",
                    "acknowledged": False,
                }
            )
    engine._notifications.extend(notifications)
    return {"ok": True, "new_notifications": len(notifications), "notifications": notifications}


def list_notifications(engine, acknowledged=False, limit=50):
    notifications = [n for n in engine._notifications if n.get("acknowledged") is acknowledged][:limit]
    return {"ok": True, "notifications": notifications, "count": len(notifications)}


def acknowledge_notification(engine, notification_id):
    for n in engine._notifications:
        if n.get("id") == notification_id:
            n["acknowledged"] = True
            return {"ok": True, "acknowledged": notification_id}
    return {"ok": False, "error": "notification not found"}


def dismiss_all_notifications(engine):
    dismissed = [n.get("id") for n in engine._notifications if not n.get("acknowledged")]
    engine._notifications = [n for n in engine._notifications if n.get("acknowledged")]
    return {"ok": True, "dismissed": dismissed, "remaining": len(engine._notifications)}


def set_user_context(engine, user_id, session_id):
    user_node = f"user:{user_id}"
    sid_node = f"session:{session_id}"
    snap = engine._snapshot()
    ids = {n["id"] for n in snap.get("nodes", []) if isinstance(n, dict)}
    if user_node not in ids:
        try:
            engine._graph.add_node(user_node, user_id, {"type": "user"})
        except Exception:
            pass
    if sid_node not in ids:
        try:
            engine._graph.add_node(sid_node, session_id, {"type": "session"})
        except Exception:
            pass
    if not any(
        e.get("from") == user_node and e.get("to") == sid_node
        for e in snap.get("edges", [])
        if isinstance(e, dict)
    ):
        try:
            engine._graph.add_edge(user_node, sid_node, "owns")
        except Exception:
            pass
    return {"ok": True, "user": user_node, "session": sid_node}


def get_user_context(engine, user_id):
    user_node = f"user:{user_id}"
    snap = engine._snapshot()
    edges = [e for e in snap.get("edges", []) if isinstance(e, dict)]
    session_ids = {e.get("to") for e in edges if e.get("from") == user_node and e.get("relation") in {"owns", "shared"}}
    sessions = []
    all_interests = {}
    all_queries = []
    shared = []
    for sid in sorted(session_ids):
        ctx = engine.get_session_context(sid.replace("session:", ""), depth=2)
        sessions.append(
            {
                "session_id": sid,
                "queries": len(ctx.get("recent_queries", [])),
                "interests": len(ctx.get("interest_profile", [])),
            }
        )
        for q in ctx.get("recent_queries", []):
            all_queries.append({**q, "_session": sid})
        for item in ctx.get("interest_profile", []):
            nid = item["node"]
            if nid not in all_interests:
                all_interests[nid] = {"node": nid, "weight": 0, "title": item.get("title", nid)}
            all_interests[nid]["weight"] += item.get("weight", 1)
        if any(e.get("from") == user_node and e.get("to") == sid and e.get("relation") == "shared" for e in edges):
            shared.append(sid)
    all_queries.sort(key=lambda x: x.get("ts", 0), reverse=True)
    unified = sorted(all_interests.values(), key=lambda x: x["weight"], reverse=True)
    return {
        "ok": True,
        "user_id": user_id,
        "sessions": sessions,
        "unified_interests": unified,
        "recent_queries": all_queries[:20],
        "shared_sessions": shared,
    }


def share_session(engine, from_user, to_user, session_id):
    from_node = f"user:{from_user}"
    to_node = f"user:{to_user}"
    sid_node = f"session:{session_id}"
    snap = engine._snapshot()
    edges = [e for e in snap.get("edges", []) if isinstance(e, dict)]
    if not any(e.get("from") == from_node and e.get("to") == sid_node and e.get("relation") == "owns" for e in edges):
        return {"ok": False, "error": "Session not owned by from_user"}
    ids = {n["id"] for n in snap.get("nodes", []) if isinstance(n, dict)}
    if to_node not in ids:
        try:
            engine._graph.add_node(to_node, to_user, {"type": "user"})
        except Exception:
            pass
    if not any(e.get("from") == to_node and e.get("to") == sid_node for e in edges):
        try:
            engine._graph.add_edge(to_node, sid_node, "shared")
        except Exception:
            pass
    return {"ok": True, "shared_with": to_user, "session": session_id}


def revoke_session(engine, user_id, session_id):
    user_node = f"user:{user_id}"
    sid_node = f"session:{session_id}"
    try:
        engine._graph.remove_edge(user_node, sid_node)
    except Exception:
        pass
    engine._append_audit("revoke_session", {"user": user_node, "session": sid_node}, {})
    engine._maybe_snapshot()
    return {"ok": True, "user": user_node, "session": sid_node, "revoked": True}


def grant_permission(engine, from_user, to_user, resource, level="read"):
    relation = "acl:" + (level or "read").lower()
    actor_node = f"user:{from_user}"
    subject_node = resource
    snap = engine._snapshot()
    ids = {n.get("id") for n in snap.get("nodes", []) if isinstance(n, dict)}
    if resource not in ids and resource != "*":
        return {"ok": False, "error": "resource_not_found", "resource": resource}
    existing = any(
        e.get("from") == actor_node and e.get("to") == subject_node and e.get("relation") == relation
        for e in snap.get("edges", [])
        if isinstance(e, dict)
    )
    if existing:
        return {
            "ok": True,
            "from": from_user,
            "to": to_user,
            "resource": resource,
            "level": level,
            "created": False,
        }
    try:
        engine._graph.add_edge(actor_node, subject_node, relation)
    except Exception:
        pass
    engine._append_audit(
        "grant_permission",
        {"from": actor_node, "to": subject_node, "level": level},
        {"from": actor_node, "to": subject_node, "level": level},
    )
    engine._maybe_snapshot()
    return {
        "ok": True,
        "from": from_user,
        "to": to_user,
        "resource": resource,
        "level": level,
        "created": True,
    }


def revoke_permission(engine, from_user, to_user, resource):
    actor_node = f"user:{from_user}"
    subject_node = resource
    snap = engine._snapshot()
    before = [
        e
        for e in snap.get("edges", [])
        if isinstance(e, dict) and e.get("from") == actor_node and e.get("to") == subject_node and (e.get("relation") or "").startswith("acl:")
    ]
    removed_ids = [e.get("id") for e in before]
    if before:
        try:
            engine._graph.remove_edge(actor_node, subject_node)
        except Exception:
            pass
        engine._append_audit(
            "revoke_permission",
            {"from": actor_node, "to": subject_node, "edges": removed_ids},
            {},
        )
        engine._maybe_snapshot()
    return {"ok": True, "from": from_user, "to": to_user, "resource": resource, "removed": len(removed_ids)}


def check_permission(engine, user, level, resource):
    relation = "acl:" + (level or "read").lower()
    snap = engine._snapshot()
    # All ACL edges (do NOT pre-filter by `to == resource` here — a wildcard
    # grant has to == "*", so a per-resource filter would hide it and force
    # the "default" fallback before the wildcard check is ever reached).
    acl_edges = [
        e for e in snap.get("edges", [])
        if isinstance(e, dict) and (e.get("relation") or "").startswith("acl:")
    ]
    explicit = any(
        e.get("to") == resource and e.get("relation") == relation
        for e in acl_edges
    )
    if explicit:
        return {"ok": True, "allowed": True, "reason": "explicit"}
    wildcard = any(
        (e.get("to") == "*" or e.get("from") == "*") and e.get("relation") == relation
        for e in acl_edges
    )
    if wildcard:
        return {"ok": True, "allowed": True, "reason": "wildcard"}
    if not acl_edges:
        return {"ok": True, "allowed": True, "reason": "default"}
    return {"ok": True, "allowed": False, "reason": "no_acl"}


def list_permissions(engine, user):
    actor_node = f"user:{user}"
    grants = []
    for e in engine._snapshot().get("edges", []):
        if isinstance(e, dict) and e.get("from") == actor_node and (e.get("relation") or "").startswith("acl:"):
            grants.append(
                {
                    "resource": e.get("to"),
                    "level": (e.get("relation") or "").split(":", 1)[1],
                }
            )
    return {"ok": True, "user": actor_node, "permissions": grants}


def add_node(engine, node_id, content, meta=None, *, base_revision=None, actor=None, strategy="reject"):
    if meta is None:
        meta = {}
    existing = _find_node(engine, node_id)
    if existing:
        if actor and not engine.check_permission(actor, "write", node_id).get("allowed"):
            return {"ok": False, "error": "Write permission denied"}
        incoming = {
            "id": node_id,
            "content": content,
            "meta": dict(meta),
        }
        incoming["meta"]["_clock"] = _get_clock(existing)
        try:
            resolved = _apply_strategy(engine, existing, incoming, base_revision or 0, strategy, actor or "system")
        except ConflictError as ce:
            return {"ok": False, "error": "Conflict", "conflict": ce.to_dict()}
        existing["content"] = resolved["content"]
        existing["label"] = resolved.get("content", existing.get("label"))
        existing["meta"] = {**existing.get("meta", {}), **meta}
        _bump(existing, actor or "system")
        engine._append_audit("update_node", {"id": node_id, "actor": actor, "strategy": strategy}, {})
        engine._maybe_snapshot()
        return {
            "ok": True,
            "id": node_id,
            "revision": _get_rev(existing),
            "clock": _get_clock(existing),
        }
    try:
        engine._graph.add_node(node_id, content, dict(meta) if meta else {})
    except Exception:
        pass
    node = _find_node(engine, node_id)
    if node is None:
        node = {"id": node_id, "label": content, "meta": dict(meta) if meta else {}}
        try:
            engine._graph._nodes[node_id] = node
        except Exception:
            pass
    _sys_meta(node).setdefault("_original_content", node.get("content") or node.get("label") or content)
    _sys_meta(node)["_rev"] = _get_rev(node) + 1
    _sys_meta(node)["_clock"] = _get_clock(node)
    _sys_meta(node)["_clock"][actor or "system"] = _sys_meta(node)["_clock"].get(actor or "system", 0) + 1
    _sys_meta(node)["_modified_by"] = actor or "system"
    if "content" not in _sys_meta(node) and "label" in node:
        _sys_meta(node)["content"] = node["label"]
    if "label" not in node and "content" in _sys_meta(node):
        node["label"] = _sys_meta(node)["content"]
    engine._append_audit("add_node", {"id": node_id, "actor": actor}, {})
    engine._maybe_snapshot()
    return {
        "ok": True,
        "id": node_id,
        "revision": _get_rev(node),
        "clock": _get_clock(node),
        "content": node.get("label", content),
    }


def add_edge(engine, from_id, to_id, relation, *, base_revision=None, actor=None, strategy="reject", edge_id=None):
    if actor and not engine.check_permission(actor, "write", from_id).get("allowed"):
        return {"ok": False, "error": "Write permission denied"}
    eid = edge_id or str(uuid.uuid4())
    idx = _find_edge_index(engine, eid)
    if idx >= 0:
        existing = engine._graph._edges[idx]
        incoming = {
            "_id": eid,
            "from": from_id,
            "to": to_id,
            "relation": relation,
            "_rev": _get_rev(existing),
            "_clock": _get_clock(existing),
        }
        try:
            resolved = _apply_strategy(engine, existing, incoming, base_revision or 0, strategy, actor or "system")
        except ConflictError as ce:
            return {"ok": False, "error": "Conflict", "conflict": ce.to_dict()}
        engine._graph._edges[idx] = resolved
        _bump(engine._graph._edges[idx], actor or "system")
        engine._append_audit("update_edge", {"edge_id": eid, "actor": actor}, {})
        engine._maybe_snapshot()
        return {"ok": True, "edge_id": eid, "revision": _get_rev(engine._graph._edges[idx])}
    try:
        engine._graph.add_edge(from_id, to_id, relation)
    except Exception:
        pass
    engine._append_audit("add_edge", {"from": from_id, "to": to_id, "relation": relation, "actor": actor}, {})
    engine._maybe_snapshot()
    return {"ok": True, "edge_id": eid, "revision": 1}


def fork_branch(engine, user_id, branch_name, from_revision=None):
    snap = engine._snapshot()
    branch_id = f"branch:{branch_name}"
    try:
        engine._graph.add_node(branch_id, f"Branch {branch_name}", {
            "type": "branch",
            "owner": user_id,
            "from_revision": from_revision,
            "snapshot": snap,
        })
    except Exception:
        pass
    try:
        engine._graph.add_edge(f"user:{user_id}", branch_id, "owns")
    except Exception:
        pass
    engine._append_audit("fork_branch", {"user": user_id, "branch": branch_name}, {})
    return {"ok": True, "branch": branch_name, "from_revision": from_revision}


def merge_branch(engine, user_id, branch_name, target_resource="*", strategy="content_merge"):
    if not engine.check_permission(user_id, "write", target_resource).get("allowed"):
        return {"ok": False, "error": "Write permission required"}
    branch_id = f"branch:{branch_name}"
    branch_node = _find_node(engine, branch_id)
    if not branch_node:
        return {"ok": False, "error": "Branch not found"}
    snap = (branch_node.get("meta") or {}).get("snapshot") or {}
    merged = 0
    conflicts = []
    for n in snap.get("nodes", []):
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if target_resource != "*" and nid != target_resource:
            continue
        if str(nid).startswith(("user:", "branch:", "queue:")):
            continue
        r = add_node(
            engine,
            nid,
            n.get("content", ""),
            n.get("meta", {}),
            base_revision=_get_rev(_find_node(engine, nid) or {}),
            actor=user_id,
            strategy=strategy,
        )
        if not r.get("ok") and "Conflict" in r.get("error", ""):
            conflicts.append(r.get("conflict"))
        else:
            merged += 1
    engine._append_audit("merge_branch", {"user": user_id, "branch": branch_name, "merged": merged}, {})
    if conflicts:
        return {
            "ok": False,
            "error": "Merge produced conflicts",
            "conflicts": conflicts,
            "merged": merged,
        }
    return {"ok": True, "merged": merged}


def queue_mutation(engine, user_id, mutation_type, params, base_revision):
    queue_id = f"queue:{user_id}"
    q = _find_node(engine, queue_id)
    if not q:
        try:
            engine._graph.add_node(queue_id, f"Queue for {user_id}", {"type": "mutation_queue", "items": []})
        except Exception:
            pass
        try:
            engine._graph.add_edge(f"user:{user_id}", queue_id, "owns")
        except Exception:
            pass
        q = _find_node(engine, queue_id)
    items = (q.get("meta") or {}).get("items", []) if isinstance(q, dict) else []
    items.append(
        {
            "type": mutation_type,
            "params": params,
            "base_revision": base_revision,
            "queued_at": time.time(),
        }
    )
    if isinstance(q, dict):
        q.setdefault("meta", {})["items"] = items
    _bump(q, user_id)
    return {"ok": True, "queued": len(items)}


def sync_queue(engine, user_id, strategy="lww"):
    queue_id = f"queue:{user_id}"
    q = _find_node(engine, queue_id)
    if not q:
        return {"ok": True, "applied": 0, "remaining": 0}
    items = list((q.get("meta") or {}).get("items", []) if isinstance(q, dict) else [])
    applied = 0
    remaining = []
    for item in items:
        mtype = item.get("type")
        params = item.get("params", {})
        base_rev = item.get("base_revision")
        if mtype == "add_node":
            r = add_node(
                engine,
                params["node_id"],
                params.get("content", ""),
                params.get("meta", {}),
                base_revision=base_rev,
                actor=user_id,
                strategy=strategy,
            )
        elif mtype == "add_edge":
            r = add_edge(
                engine,
                params["from_id"],
                params["to_id"],
                params["relation"],
                base_revision=base_rev,
                actor=user_id,
                strategy=strategy,
            )
        else:
            remaining.append(item)
            continue
        if r.get("ok"):
            applied += 1
        elif "Conflict" in r.get("error", ""):
            item["_last_conflict"] = r.get("conflict")
            remaining.append(item)
        else:
            remaining.append(item)
    if isinstance(q, dict):
        q.setdefault("meta", {})["items"] = remaining
    _bump(q, user_id)
    engine._append_audit("sync_queue", {"user": user_id, "applied": applied, "remaining": len(remaining)}, {})
    return {"ok": True, "applied": applied, "remaining": len(remaining)}


def get_conflicts(engine, resource_id):
    node = _find_node(engine, resource_id)
    if not node:
        return {"ok": False, "error": "Not found"}
    return {
        "ok": True,
        "resource": resource_id,
        "revision": _get_rev(node),
        "clock": _get_clock(node),
        "modified_by": _sys_meta(node).get("_modified_by"),
    }


def remove_node(engine, node_id):
    snap = engine._snapshot()
    ids = {n.get("id") for n in snap.get("nodes", []) if isinstance(n, dict)}
    if node_id not in ids:
        return {"ok": True, "removed": False, "reason": "not_found"}
    try:
        engine._graph.remove_node(node_id)
    except Exception:
        pass
    engine._append_audit("remove_node", {"id": node_id}, {})
    engine._maybe_snapshot()
    return {"ok": True, "removed": True, "id": node_id}
