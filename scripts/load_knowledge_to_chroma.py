#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "app" / "app").exists():
    sys.path.insert(0, str(ROOT / "app"))
else:
    sys.path.insert(0, str(ROOT))

from app.rag import ChromaMemory, OllamaEmbedder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Load persona Markdown into ChromaDB.")
    parser.add_argument("--knowledge", default="knowledge/mustafa_persona.md", help="Markdown knowledge file.")
    parser.add_argument("--chroma-path", default="data/chroma", help="ChromaDB persistence path.")
    parser.add_argument("--collection", default="mustafa_persona", help="Chroma collection name.")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434", help="Ollama base URL.")
    parser.add_argument("--embedding-model", default="nomic-embed-text", help="Ollama embedding model.")
    args = parser.parse_args()

    embedder = OllamaEmbedder(args.ollama_base_url, args.embedding_model)
    memory = ChromaMemory(args.chroma_path, args.collection, embedder)
    count = memory.reset_from_markdown(args.knowledge)
    print(f"Loaded {count} chunks into Chroma collection '{args.collection}'.")


if __name__ == "__main__":
    main()
