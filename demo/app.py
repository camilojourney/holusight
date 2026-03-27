"""CodeSight — AI Document Search Chat UI.

Run with: streamlit run demo/app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="CodeSight",
    page_icon="🔍",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Helpers (defined before use)
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_engine(folder: str):
    from codesight.api import CodeSight
    return CodeSight(folder)


def _render_sources(sources) -> list[dict]:
    """Render source citations as expandable cards. Returns serializable data."""
    if not sources:
        return []

    source_data = []
    st.caption(f"Sources ({len(sources)})")

    for s in sources:
        # Handle both SearchResult objects and dicts (from session state)
        if isinstance(s, dict):
            file_path = s["file_path"]
            scope = s["scope"]
            snippet = s["snippet"]
            score = s["score"]
            start_line = s["start_line"]
            end_line = s["end_line"]
        else:
            file_path = s.file_path
            scope = s.scope
            snippet = s.snippet
            score = s.score
            start_line = s.start_line
            end_line = s.end_line

        with st.expander(f"{file_path} — {scope} (score: {score:.4f})"):
            st.code(snippet[:800], language=None)
            st.caption(f"Lines/pages: {start_line}-{end_line}")

        source_data.append({
            "file_path": file_path,
            "scope": scope,
            "snippet": snippet,
            "score": score,
            "start_line": start_line,
            "end_line": end_line,
        })

    return source_data


# ---------------------------------------------------------------------------
# Sidebar — folder config + indexing
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("CodeSight")
    st.caption("AI-powered document search")

    folder_path = st.text_input(
        "Document folder path",
        value=st.session_state.get("folder_path", ""),
        placeholder="/path/to/your/documents",
        help="Enter the absolute path to a folder containing documents to search. "
             "Example: /Users/you/Documents/contracts or ~/projects/my-repo",
    )

    # Expand ~ in path for user convenience
    if folder_path and folder_path.startswith("~"):
        folder_path = str(Path(folder_path).expanduser())

    if folder_path:
        st.session_state["folder_path"] = folder_path

    col1, col2 = st.columns(2)

    with col1:
        index_btn = st.button("Index", use_container_width=True)
    with col2:
        rebuild_btn = st.button("Rebuild", use_container_width=True)

    # Status display
    if folder_path and Path(folder_path).is_dir():
        try:
            engine = _get_engine(folder_path)
            status = engine.status()
            if status.indexed:
                st.success(f"Indexed: {status.files_indexed} files, {status.chunk_count} chunks")
                if status.last_indexed_at:
                    st.caption(f"Last indexed: {status.last_indexed_at[:19]}")
            else:
                st.warning("Not indexed yet. Click 'Index' to start.")
        except Exception as e:
            st.error(f"Error: {e}")
    elif folder_path:
        st.error("Directory not found")

    st.divider()
    st.caption("Powered by hybrid BM25 + vector search with Claude")


# ---------------------------------------------------------------------------
# Handle indexing
# ---------------------------------------------------------------------------

if index_btn and folder_path:
    with st.spinner("Indexing documents..."):
        try:
            engine = _get_engine(folder_path)
            stats = engine.index()
            st.sidebar.success(
                f"Done! {stats.files_indexed} files, "
                f"{stats.chunks_created} chunks in {stats.elapsed_seconds}s"
            )
        except Exception as e:
            st.sidebar.error(f"Indexing failed: {e}")

if rebuild_btn and folder_path:
    with st.spinner("Rebuilding index from scratch..."):
        try:
            engine = _get_engine(folder_path)
            stats = engine.index(force_rebuild=True)
            st.sidebar.success(
                f"Rebuilt! {stats.files_indexed} files, "
                f"{stats.chunks_created} chunks in {stats.elapsed_seconds}s"
            )
        except Exception as e:
            st.sidebar.error(f"Rebuild failed: {e}")


# ---------------------------------------------------------------------------
# Chat interface
# ---------------------------------------------------------------------------

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "sources" in msg:
            _render_sources(msg["sources"])

# Empty state guidance
if not st.session_state.messages:
    if not folder_path:
        st.markdown("---")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**Step 1**")
            st.markdown(
                "Enter a folder path in the sidebar pointing to your"
                " documents (PDFs, code, markdown, etc.)"
            )
        with col_b:
            st.markdown("**Step 2**")
            st.markdown("Click **Index** to scan and embed your documents. This runs 100% locally.")
        with col_c:
            st.markdown("**Step 3**")
            st.markdown(
                "Ask questions in natural language. CodeSight searches"
                " with hybrid BM25 + vector retrieval."
            )
        st.markdown("---")
        st.caption(
            "Supported formats: .py, .js, .ts, .go, .rs, .java,"
            " .md, .txt, .pdf, .docx, .pptx, and 40+ more"
        )
    elif folder_path and Path(folder_path).is_dir():
        try:
            engine = _get_engine(folder_path)
            s = engine.status()
            if not s.indexed:
                st.info(
                    "**Ready to index.** Click **Index** in the sidebar to scan your documents, "
                    "then ask questions here."
                )
            else:
                st.markdown("---")
                st.markdown(
                    f"**{s.files_indexed} files indexed** with {s.chunk_count} searchable chunks. "
                    "Try one of these example queries:"
                )
                example_queries = [
                    "What are the main components in this codebase?",
                    "Find all error handling patterns",
                    "Summarize the configuration options",
                ]
                for q in example_queries:
                    st.markdown(f"- *{q}*")
                st.markdown("---")
        except Exception:
            pass

# Chat input
if prompt := st.chat_input("Ask a question about your documents..."):
    if not folder_path or not Path(folder_path).is_dir():
        st.error("Please set a valid document folder path in the sidebar.")
    else:
        # Display user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Searching and thinking..."):
                try:
                    engine = _get_engine(folder_path)
                    answer = engine.ask(prompt)

                    st.markdown(answer.text)
                    sources_data = _render_sources(answer.sources)

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer.text,
                        "sources": sources_data,
                    })
                except Exception as e:
                    error_msg = f"Error: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg,
                    })
