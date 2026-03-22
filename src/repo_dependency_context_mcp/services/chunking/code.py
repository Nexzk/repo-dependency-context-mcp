from __future__ import annotations

import ast

from repo_dependency_context_mcp.services.chunking.common import ChunkDraft


def chunk_python_file(repo_name: str, file_path: str, source_text: str) -> list[ChunkDraft]:
    tree = ast.parse(source_text)
    lines = source_text.splitlines()
    chunks: list[ChunkDraft] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        start_line = node.lineno
        end_line = getattr(node, "end_lineno", node.lineno)
        snippet = "\n".join(lines[start_line - 1 : end_line]).strip()
        if not snippet:
            continue

        symbol_name = getattr(node, "name", "unknown")
        symbol_kind = "class" if isinstance(node, ast.ClassDef) else "function"
        symbol_path = symbol_name
        summary = f"This chunk contains {symbol_kind} logic for {symbol_name}."
        context_prefix = "\n".join(
            [
                f"Repo: {repo_name}",
                f"File: {file_path}",
                f"Symbol: {symbol_name}",
                f"Kind: {symbol_kind}",
                "LastChanged: unknown",
                summary,
            ]
        )
        chunks.append(
            ChunkDraft(
                chunk_type="code_symbol",
                text=snippet,
                context_prefix=context_prefix,
                token_count=_estimate_tokens(snippet),
                symbol_path=symbol_path,
                metadata={
                    "file_path": file_path,
                    "language": "python",
                    "symbol_name": symbol_name,
                    "symbol_kind": symbol_kind,
                    "symbol_path": symbol_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "last_commit_sha": None,
                    "last_updated_at": None,
                },
            )
        )

    if chunks:
        return chunks

    stripped_text = source_text.strip()
    if not stripped_text:
        return []

    return [
        ChunkDraft(
            chunk_type="code_file",
            text=stripped_text,
            context_prefix="\n".join(
                [
                    f"Repo: {repo_name}",
                    f"File: {file_path}",
                    "Symbol: file",
                    "Kind: module",
                    "LastChanged: unknown",
                    "This chunk contains module-level code.",
                ]
            ),
            token_count=_estimate_tokens(stripped_text),
            metadata={
                "file_path": file_path,
                "language": "python",
                "symbol_name": None,
                "symbol_kind": "module",
                "symbol_path": None,
                "start_line": 1,
                "end_line": len(lines),
                "last_commit_sha": None,
                "last_updated_at": None,
            },
        )
    ]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))
