"""Admin & permission management (persisted JSON).

Owners = ADMIN_IDS từ env/config (full quyền, không thể bị xoá quyền).
Admins thêm runtime = lưu trong data/admins.json kèm dict quyền.

Backward compat: nếu file chưa tồn tại -> chỉ owner mới có quyền.
"""
import json
import os
from typing import Dict, List, Optional

from config import DATA_DIR, ADMIN_IDS

ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")

# Danh sách quyền chi tiết
PERMS = [
    ("CHECK",      "🛡 CHECK JOIN"),
    ("AUTO",       "🤖 AUTO"),
    ("REF",        "🎯 REF"),
    ("SPAM",       "💬 SPAM"),
    ("JOIN",       "🚪 JOIN GROUP"),
    ("MANAGE_ACC", "👤 Quản lý TK"),
    ("READ_MSG",   "📩 Đọc tin nhắn TK"),
    ("STOP",       "⛔ Stop task"),
    ("LOGS",       "📜 Logs/Status"),
    ("ADD_ADMIN",  "➕ Thêm admin"),
    ("DEL_ADMIN",  "🗑 Xoá admin"),
    ("EDIT_ADMIN", "✏️ Sửa quyền admin"),
]
PERM_KEYS = [k for k, _ in PERMS]


def _default_perms(value: bool = True) -> Dict[str, bool]:
    return {k: value for k in PERM_KEYS}


def _load() -> dict:
    if not os.path.exists(ADMINS_FILE):
        return {"admins": {}}
    try:
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "admins" not in d:
                d["admins"] = {}
            return d
    except Exception:
        return {"admins": {}}


def _save(d: dict):
    tmp = ADMINS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ADMINS_FILE)


def is_owner(uid: int) -> bool:
    return uid in ADMIN_IDS


def is_admin(uid: int) -> bool:
    if is_owner(uid):
        return True
    d = _load()
    return str(uid) in d["admins"]


def has_perm(uid: int, perm: str) -> bool:
    if is_owner(uid):
        return True
    d = _load()
    rec = d["admins"].get(str(uid))
    if not rec:
        return False
    return bool(rec.get("perms", {}).get(perm, False))


def list_admins() -> List[dict]:
    """Trả về list [{uid, owner, name, perms}]. Owners trước, admin sau."""
    out = []
    for oid in sorted(ADMIN_IDS):
        out.append({"uid": oid, "owner": True, "name": "Owner", "perms": _default_perms(True)})
    d = _load()
    for uid_s, rec in d["admins"].items():
        try:
            uid = int(uid_s)
        except Exception:
            continue
        if uid in ADMIN_IDS:
            continue
        out.append({
            "uid": uid,
            "owner": False,
            "name": rec.get("name", ""),
            "perms": {**_default_perms(False), **rec.get("perms", {})},
        })
    return out


def get_admin(uid: int) -> Optional[dict]:
    for a in list_admins():
        if a["uid"] == uid:
            return a
    return None


def add_admin(uid: int, name: str = "") -> bool:
    if uid in ADMIN_IDS:
        return False
    d = _load()
    if str(uid) in d["admins"]:
        return False
    d["admins"][str(uid)] = {"name": name, "perms": _default_perms(True)}
    _save(d)
    return True


def remove_admin(uid: int) -> bool:
    if uid in ADMIN_IDS:
        return False  # không thể xoá owner
    d = _load()
    if str(uid) not in d["admins"]:
        return False
    del d["admins"][str(uid)]
    _save(d)
    return True


def toggle_perm(uid: int, perm: str) -> Optional[bool]:
    if uid in ADMIN_IDS:
        return None
    if perm not in PERM_KEYS:
        return None
    d = _load()
    rec = d["admins"].get(str(uid))
    if not rec:
        return None
    perms = {**_default_perms(False), **rec.get("perms", {})}
    perms[perm] = not perms.get(perm, False)
    rec["perms"] = perms
    d["admins"][str(uid)] = rec
    _save(d)
    return perms[perm]