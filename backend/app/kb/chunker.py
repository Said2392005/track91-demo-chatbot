"""
Structural chunking per docs/phase-4-knowledge-base/chunking-strategy.md:
- default rule: split on h2 (`## `) headings, one chunk per section
- `app_faq` special case: one chunk per `## Q: ...` pair (identical mechanism to the default
  rule, since FAQ files already use `## Q: ...` as their section headings — called out
  separately in the design doc because it's the case that matters for retrieval quality, not
  because it needs different code)
- oversized-section fallback: sections over ~500 words split further at paragraph boundaries
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

OVERSIZED_SECTION_WORD_LIMIT = 500

REQUIRED_FRONT_MATTER_FIELDS = ["doc_id", "title", "category", "version", "approved_pricing"]


@dataclass
class SourceDoc:
    doc_id: str
    title: str
    category: str
    version: str
    approved_pricing: bool
    source_path: str
    sections: list[tuple[str, str]] = field(default_factory=list)  # (section_title, body)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    category: str
    section_title: str
    doc_version: str
    approved_pricing: bool
    chunk_index: int
    content_hash: str
    source_path: str
    text: str


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_source_file(path: Path) -> SourceDoc:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path}: missing YAML front-matter block")

    _, front_matter_raw, body = raw.split("---", 2)
    front_matter = yaml.safe_load(front_matter_raw)

    missing = [f for f in REQUIRED_FRONT_MATTER_FIELDS if f not in front_matter]
    if missing:
        raise ValueError(f"{path}: front-matter missing required field(s): {missing}")

    sections = []
    for match in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL):
        section_title = match.group(1).strip()
        section_body = match.group(2).strip()
        sections.append((section_title, section_body))

    if not sections:
        raise ValueError(f"{path}: no '## ' sections found — nothing to chunk")

    return SourceDoc(
        doc_id=front_matter["doc_id"],
        title=front_matter["title"],
        category=front_matter["category"],
        version=str(front_matter["version"]),
        approved_pricing=bool(front_matter["approved_pricing"]),
        source_path=str(path),
        sections=sections,
    )


def _split_oversized(section_title: str, body: str) -> list[str]:
    if len(body.split()) <= OVERSIZED_SECTION_WORD_LIMIT:
        return [body]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    sub_chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for para in paragraphs:
        para_words = len(para.split())
        if current and current_words + para_words > OVERSIZED_SECTION_WORD_LIMIT:
            sub_chunks.append("\n\n".join(current))
            current, current_words = [], 0
        current.append(para)
        current_words += para_words
    if current:
        sub_chunks.append("\n\n".join(current))
    return sub_chunks


def chunk_document(doc: SourceDoc) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_index = 0
    for section_title, body in doc.sections:
        parts = _split_oversized(section_title, body)
        base_id = f"{doc.doc_id}::{slugify(section_title)}"
        for i, part_text in enumerate(parts):
            chunk_id = base_id if len(parts) == 1 else f"{base_id}::{i}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    title=doc.title,
                    category=doc.category,
                    section_title=section_title,
                    doc_version=doc.version,
                    approved_pricing=doc.approved_pricing,
                    chunk_index=chunk_index,
                    content_hash=_content_hash(part_text),
                    source_path=doc.source_path,
                    text=part_text,
                )
            )
            chunk_index += 1
    return chunks


def load_and_chunk_source_dir(source_dir: Path) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for path in sorted(source_dir.glob("**/*.md")):
        doc = parse_source_file(path)
        all_chunks.extend(chunk_document(doc))
    return all_chunks
