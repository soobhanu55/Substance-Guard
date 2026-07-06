from app.rag.chunkers import clause_chunks, fixed_window_chunks

SAMPLE_TEXT = """Preamble text before any clause marker.

Article 33 (Duty to communicate)
Suppliers must communicate substance information above 0.1% w/w.
This obligation applies to articles placed on the market.

Annex II (Restricted substances)
Lead -- 0.1%
Cadmium -- 0.01%

Article 7(2) (Notification)
Notification is required above 0.1% w/w and one tonne per year.
"""


def test_clause_chunks_splits_on_article_and_annex_headers():
    chunks = clause_chunks(SAMPLE_TEXT, source_id="test.txt", regulation_name="TEST_REG")
    clause_ids = [c.clause_id for c in chunks]
    assert "Article 33" in clause_ids
    assert "Annex II" in clause_ids
    assert "Article 7(2)" in clause_ids
    assert len(chunks) == 3  # preamble before the first header is dropped, not its own chunk


def test_clause_chunks_each_chunk_contains_only_its_own_clause_text():
    chunks = clause_chunks(SAMPLE_TEXT, source_id="test.txt", regulation_name="TEST_REG")
    annex_chunk = next(c for c in chunks if c.clause_id == "Annex II")
    assert "Lead" in annex_chunk.text
    assert "Notification is required" not in annex_chunk.text  # that's Article 7(2)'s text


def test_clause_chunks_falls_back_to_single_chunk_when_no_headers():
    text = "Just plain prose with no legal structure markers at all."
    chunks = clause_chunks(text, source_id="test.txt", regulation_name="TEST_REG")
    assert len(chunks) == 1
    assert chunks[0].clause_id is None


def test_fixed_window_chunks_respects_window_and_overlap():
    words = " ".join(f"word{i}" for i in range(1000))
    chunks = fixed_window_chunks(words, source_id="test.txt", regulation_name="TEST_REG",
                                  window_words=300, overlap_words=50)
    assert all(c.clause_id is None for c in chunks)
    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    assert len(first_words) == 300
    # overlap: last 50 words of chunk 0 == first 50 words of chunk 1
    assert first_words[-50:] == second_words[:50]


def test_fixed_window_chunks_handles_short_text():
    chunks = fixed_window_chunks("short text only", source_id="test.txt", regulation_name="TEST_REG")
    assert len(chunks) == 1
    assert chunks[0].text == "short text only"
