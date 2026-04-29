"""User, AuditEntry, UserStore — pre-populated from rbac_config.json."""
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from .rbac import RBAC_CONFIG, Role


@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    role: object
    department: str
    full_name: str
    email: str
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AuditEntry:
    timestamp: str
    user_id: str
    username: str
    role: str
    action: str
    query_text: str
    results_count: int
    filtered_count: int
    category_filter: str
    success: bool
    details: str = ""


class UserStore:
    def __init__(self):
        self.users: Dict[str, User] = {}

    def _hash(self, pw: str) -> str:
        return hashlib.sha256(pw.encode()).hexdigest()

    def create_user(self, username, password, role, dept, name, email) -> User:
        u = User(str(uuid.uuid4())[:8], username, self._hash(password), role, dept, name, email)
        self.users[username] = u
        return u

    def authenticate(self, username: str, password: str) -> Optional[User]:
        u = self.users.get(username)
        if u and u.is_active and u.password_hash == self._hash(password):
            return u
        return None


user_store = UserStore()
for u_cfg in RBAC_CONFIG["users"]:
    user_store.create_user(
        u_cfg["username"], u_cfg["password"], Role[u_cfg["role"].upper()],
        u_cfg["department"], u_cfg["full_name"], u_cfg["email"],
    )
