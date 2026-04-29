"""EnterpriseRAGSystem — parent-child retrieval + RBAC filtering + audit log."""
import glob
import os
from datetime import datetime
from typing import List, Optional

from .auth import AuditEntry, User, user_store
from .llm import LLMGenerator
from .rbac import (
    CLS_MAP,
    CONFIDENTIAL_DOCS,
    Classification,
    ROLE_PERMISSIONS,
    Role,
)
from .retriever import make_splitters, strip_boilerplate


def discover_documents(documents_path: str):
    """Walks documents_path. Each top-level folder = category. Returns (md_paths, file_to_category)."""
    md_paths = []
    file_to_category = {}
    for entry in sorted(os.listdir(documents_path)):
        cat_dir = os.path.join(documents_path, entry)
        if not os.path.isdir(cat_dir):
            continue
        category = entry.upper()
        for fp in sorted(glob.glob(os.path.join(cat_dir, "*.md"))):
            fname = os.path.basename(fp)
            md_paths.append(fp)
            file_to_category[fname] = category
    return md_paths, file_to_category


class EnterpriseRAGSystem:

    def __init__(
        self,
        documents_path: str,
        collection_name: str = "aurelius_policies",
        persist_directory: Optional[str] = None,
        parent_chunk_size: int = 1500,
        parent_chunk_overlap: int = 200,
        child_chunk_size: int = 300,
        child_chunk_overlap: int = 50,
    ):
        self.documents_path = documents_path
        self.collection_name = collection_name
        self.persist_directory = persist_directory or os.environ.get(
            "CHROMA_DB_PATH", "/tmp/chroma_db"
        )

        self.audit_log: List[AuditEntry] = []
        self.current_user: Optional[User] = None
        self.vector_store = None
        self.documents = []
        self.parent_store = {}
        self.child_chunks = []

        self.md_paths, self.file_to_category = discover_documents(documents_path)

        print("\n🔧 Initializing RAG system (Parent-Child Retriever)...")
        print("  ⏳ Loading embedding model...")
        from langchain_community.embeddings import HuggingFaceEmbeddings
        self.emb = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        print("  ✅ Embedding model loaded (384d)")

        self.parent_splitter, self.child_splitter = make_splitters(
            parent_chunk_size, parent_chunk_overlap,
            child_chunk_size, child_chunk_overlap,
        )
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size

        self.llm = LLMGenerator()

    def _extract_metadata(self, content: str, filename: str) -> dict:
        category = self.file_to_category.get(filename, "UNKNOWN")
        classification = "Confidential" if filename in CONFIDENTIAL_DOCS else "Internal"
        meta = {
            "company": "Aurelius Health Systems", "source": filename,
            "category": category, "classification": classification,
            "document_type": category, "version": "1.0",
            "department": category.replace("_", " ").title(),
        }
        for line in content.split("\n")[:20]:
            for key in ["Company", "Document Type", "Department", "Version", "Classification"]:
                if f"{key}:" in line:
                    val = line.split(f"{key}:")[1].strip().strip("*").strip()
                    if val:
                        meta[key.lower().replace(" ", "_")] = val
        meta["category"] = category
        return meta

    def initialize(self):
        from langchain_chroma import Chroma
        from langchain_core.documents import Document

        print("\n" + "═" * 60)
        print("  Building RAG Index (Parent-Child Strategy)")
        print("═" * 60)

        print("\n📂 Loading documents...")
        for fp in self.md_paths:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            filename = os.path.basename(fp)
            meta = self._extract_metadata(content, filename)
            cleaned = strip_boilerplate(content)
            title = filename.replace(".md", "").replace("_", " ")
            cleaned = f"# {title}\n\n{cleaned}"
            self.documents.append(Document(page_content=cleaned, metadata=meta))
        print(f"   ✅ {len(self.documents)} documents loaded")

        if not self.documents:
            print("❌ No .md files found!")
            return

        print("\n✂️  Creating parent chunks...")
        parent_chunks = []
        for doc in self.documents:
            pcs = self.parent_splitter.split_documents([doc])
            for i, pc in enumerate(pcs):
                pid = f"{doc.metadata['source']}::parent_{i}"
                pc.metadata.update(doc.metadata)
                pc.metadata["parent_id"] = pid
                pc.metadata["chunk_type"] = "parent"
                parent_chunks.append(pc)
                self.parent_store[pid] = pc
        print(f"   ✅ {len(parent_chunks)} parent chunks")

        print("\n✂️  Creating child chunks...")
        for pc in parent_chunks:
            ccs = self.child_splitter.split_documents([pc])
            for j, cc in enumerate(ccs):
                cc.metadata.update(pc.metadata)
                cc.metadata["chunk_type"] = "child"
                cc.metadata["child_index"] = j
                self.child_chunks.append(cc)
        per_parent = len(self.child_chunks) // max(len(parent_chunks), 1)
        print(f"   ✅ {len(self.child_chunks)} child chunks (~{per_parent} per parent)")

        print("\n🧮 Indexing child chunks...")
        import shutil
        if os.path.exists(self.persist_directory):
            shutil.rmtree(self.persist_directory, ignore_errors=True)
        os.makedirs(self.persist_directory, exist_ok=True)

        # ChromaDB 0.5.x caps batch size; add in batches of 100
        self.vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.emb,
            persist_directory=self.persist_directory,
        )
        batch_size = 100
        total = len(self.child_chunks)
        for i in range(0, total, batch_size):
            batch = self.child_chunks[i:i + batch_size]
            self.vector_store.add_documents(batch)
            print(f"   ... indexed {min(i + batch_size, total)}/{total}")
        print(f"   ✅ {self.vector_store._collection.count()} chunks indexed")

        cats, cls_c = {}, {}
        for doc in self.documents:
            cats[doc.metadata["category"]] = cats.get(doc.metadata["category"], 0) + 1
            cls_c[doc.metadata["classification"]] = cls_c.get(doc.metadata["classification"], 0) + 1
        print("\n📊 By category:")
        for c, n in sorted(cats.items()):
            print(f"   {c}: {n} docs")
        print("🔐 By classification:")
        for c, n in sorted(cls_c.items()):
            print(f"   {c}: {n} docs")
        print("\n" + "═" * 60)
        print("  ✅ RAG System Ready!")
        print("═" * 60)

    # ── Auth ────────────────────────────────────────────────────────
    def login(self, username: str, password: str) -> bool:
        u = user_store.authenticate(username, password)
        if u:
            self.current_user = u
            self._log("LOGIN", "", 0, 0, "", True, "OK")
            p = ROLE_PERMISSIONS[u.role]
            print(
                f"\n✅ {u.full_name} ({u.role.value}) | "
                f"Categories: {', '.join(p['categories'])} | Max: {p['max_classification'].name}"
            )
            return True
        self._log("LOGIN_FAILED", "", 0, 0, "", False, username)
        print(f"❌ Login failed: '{username}'")
        return False

    def logout(self):
        if self.current_user:
            print(f"👋 Logged out {self.current_user.full_name}")
            self.current_user = None

    # ── RBAC ───────────────────────────────────────────────────────
    def _rbac_filter(self, results):
        if not self.current_user:
            return [], len(results)
        p = ROLE_PERMISSIONS[self.current_user.role]
        allowed = set(p["categories"])
        max_cls = p["max_classification"]
        ok, blocked = [], 0
        for d in results:
            cat = d.metadata.get("category", "UNKNOWN")
            cls = CLS_MAP.get(d.metadata.get("classification", "Internal"), Classification.INTERNAL)
            if cat in allowed and cls.value <= max_cls.value:
                ok.append(d)
            else:
                blocked += 1
        return ok, blocked

    def _resolve_parents(self, child_docs):
        seen_parents = {}
        seen_sources = set()
        for c in child_docs:
            pid = c.metadata.get("parent_id", "")
            if pid and pid not in seen_parents and pid in self.parent_store:
                seen_parents[pid] = self.parent_store[pid]
        unique = []
        for pid, parent in seen_parents.items():
            src_name = parent.metadata.get("source", "")
            if src_name not in seen_sources:
                seen_sources.add(src_name)
                unique.append(parent)
        return unique

    # ── Query ──────────────────────────────────────────────────────
    def query(self, text: str, k: int = 5, category_filter: Optional[str] = None,
              generate_answer: bool = True) -> dict:
        if not self.current_user:
            return {"answer": "🔒 Please /login first.", "documents": [], "metadata": {"error": "auth"}}

        p = ROLE_PERMISSIONS[self.current_user.role]
        if category_filter and category_filter not in p["categories"]:
            self._log("ACCESS_DENIED", text, 0, 0, category_filter, False, "Denied")
            return {
                "answer": f"🔒 Access denied: {category_filter} not available for {self.current_user.role.value}.",
                "documents": [], "metadata": {"error": "cat_denied"},
            }

        filt = {"category": category_filter} if category_filter else None
        children = self.vector_store.similarity_search(query=text, k=k * 5, filter=filt)
        ok_children, blocked = self._rbac_filter(children)
        parents = self._resolve_parents(ok_children)
        final = parents[:k]

        if generate_answer and final:
            ans = self.llm.answer(text, final, self.current_user)
        elif not final:
            ans = "No documents found within your access level."
        else:
            ans = ""

        self._log("QUERY", text, len(final), blocked, category_filter or "ALL", True)
        return {
            "answer": ans, "documents": final,
            "metadata": {
                "user": self.current_user.username, "role": self.current_user.role.value,
                "child_matches": len(ok_children), "parents_resolved": len(parents),
                "returned": len(final), "filtered_by_rbac": blocked,
                "category_filter": category_filter, "timestamp": datetime.now().isoformat(),
            },
        }

    # ── Audit ──────────────────────────────────────────────────────
    def _log(self, action, q, res, filt, cat, ok, details=""):
        self.audit_log.append(AuditEntry(
            datetime.now().isoformat(),
            self.current_user.user_id if self.current_user else "anon",
            self.current_user.username if self.current_user else "anon",
            self.current_user.role.value if self.current_user else "none",
            action, q, res, filt, cat, ok, details,
        ))

    def get_audit_log(self, n: int = 20):
        if not self.current_user:
            return [{"error": "Not authenticated"}]
        if not ROLE_PERMISSIONS[self.current_user.role]["can_view_audit_log"]:
            return [{"error": "Access denied: elevated role required"}]
        return [{"timestamp": e.timestamp, "user": e.username, "role": e.role,
                 "action": e.action, "query": e.query_text[:50],
                 "results": e.results_count, "rbac_filtered": e.filtered_count,
                 "success": e.success, "details": e.details}
                for e in self.audit_log[-n:]]

    def get_stats(self) -> dict:
        cnt = self.vector_store._collection.count() if self.vector_store else 0
        llm_label = (
            f"OpenAI ({self.llm.model})" if self.llm.provider == "openai"
            else f"Z.AI ({self.llm.model})" if self.llm.provider == "zai"
            else "Disabled"
        )
        return {
            "documents": len(self.documents), "parent_chunks": len(self.parent_store),
            "child_chunks_indexed": cnt, "retriever": "Parent-Child",
            "parent_size": self.parent_chunk_size, "child_size": self.child_chunk_size,
            "embedding": "all-MiniLM-L6-v2 (384d)",
            "categories": len(set(d.metadata["category"] for d in self.documents)),
            "llm": llm_label, "llm_enabled": self.llm.available,
            "audit_entries": len(self.audit_log),
        }
