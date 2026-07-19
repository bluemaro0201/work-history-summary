from app.llm.chunker import ContextChunker


def test_small_data_does_not_need_chunking():
    chunker = ContextChunker("unknown", 0.7, 0.4)
    assert chunker.needs_chunking([{"a": "b"}]) is False


def test_large_data_needs_chunking_and_preserves_groups():
    chunker = ContextChunker("tiny", 0.01, 0.005)
    chunker.CONTEXT_WINDOWS["tiny"] = 1000
    groups = [{"id": i, "text": "x" * 200} for i in range(5)]
    assert chunker.needs_chunking(groups) is True
    chunks = chunker.split_into_chunks(groups)
    assert sum(len(chunk) for chunk in chunks) == len(groups)
    assert all(isinstance(chunk, list) for chunk in chunks)
