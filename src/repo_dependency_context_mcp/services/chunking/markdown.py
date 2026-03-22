from __future__ import annotations

from repo_dependency_context_mcp.services.chunking.common import ChunkDraft


def chunk_markdown_file(repo_name: str, file_path: str, source_text: str) -> list[ChunkDraft]:
    lines = source_text.splitlines()
    chunks: list[ChunkDraft] = []
    headings: list[str] = []
    buffer: list[str] = []
    active_section = "Document Root"

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if not body:
            return
        section_path = " > ".join(headings) if headings else active_section
        chunks.append(
            ChunkDraft(
                chunk_type="markdown_section",
                text=body,
                context_prefix="\n".join(
                    [
                        f"Repo: {repo_name}",
                        f"File: {file_path}",
                        f"Section: {section_path}",
                        "This chunk contains repository documentation.",
                    ]
                ),
                token_count=max(1, len(body.split())),
                metadata={
                    "file_path": file_path,
                    "language": "markdown",
                    "heading_path": section_path,
                },
            )
        )

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            buffer.clear()
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[level:].strip()
            headings[:] = headings[: level - 1]
            headings.append(title)
            active_section = title
            continue
        buffer.append(line)

    flush()
    return chunks
