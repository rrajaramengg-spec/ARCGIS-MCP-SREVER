"""One-time script to ingest few-shot examples into the RAG vector store."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def ingest_all():
    from core.rag import database, ingest_document

    database.init_db()

    with open("/app/uploads/few_shot_examples_enhanced.json") as f:
        examples = json.load(f)

    print(f"Ingesting {len(examples)} examples...")

    for ex in examples:
        content = ex["content"]
        if ex.get("layers"):
            layer_info = "\n\nAvailable Layers:\n"
            for layer in ex["layers"]:
                name = layer["name"].upper()
                url = layer["url"]
                layer_info += f"- {name}: {url}\n"
            content = content + layer_info

        result = await ingest_document(
            content=content,
            doc_type=ex.get("doc_type", "example"),
            title=ex.get("title", ""),
            metadata={
                "original_id": ex.get("id"),
                "operations": ex.get("operations", []),
                "layers": ex.get("layers", []),
            },
        )
        print(f"  [{ex['id']}] {ex['title']}: {result['status']}")

    print("Done!")


if __name__ == "__main__":
    asyncio.run(ingest_all())
