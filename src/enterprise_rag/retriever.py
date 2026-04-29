"""Boilerplate stripping + parent-child splitter helpers."""
import re

BOILERPLATE_PATTERNS = [
    r"\*\*Company:\*\*.*?\n",
    r"\*\*Document Type:\*\*.*?\n",
    r"\*\*Department:\*\*.*?\n",
    r"\*\*Version:\*\*.*?\n",
    r"\*\*Classification:\*\*.*?\n",
    r"## Purpose\nThis document defines internal standards.*?secure handling of data\.",
    r"## Scope\nThis document applies to all employees.*?Aurelius Health Systems\.",
    r"## Roles & Responsibilities\n- Leadership ensures.*?compliance with this document\.",
]


def strip_boilerplate(text: str) -> str:
    cleaned = text
    for pattern in BOILERPLATE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def make_splitters(parent_chunk_size=1500, parent_chunk_overlap=200,
                   child_chunk_size=300, child_chunk_overlap=50):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    parent = RecursiveCharacterTextSplitter(
        chunk_size=parent_chunk_size, chunk_overlap=parent_chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    child = RecursiveCharacterTextSplitter(
        chunk_size=child_chunk_size, chunk_overlap=child_chunk_overlap,
        separators=["\n### ", "\n\n", "\n", " ", ""],
    )
    return parent, child
