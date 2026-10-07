from src.parsing.llm import chunking


def test_should_enable_chunking_by_force_threshold():
    assert chunking.should_enable_chunking('x' * (chunking.FORCE_CHUNKING_TEXT_LENGTH + 1), {'sender_tag': 'foo'}) is True
    assert chunking.should_enable_chunking('x' * 100, {'sender_tag': 'foo'}) is False


def test_chunk_text_by_transactions_splits_large_text():
    lines = [f'2026-03-{i:02d} item {i}' for i in range(1, 30)]
    text = '\n'.join(lines)

    chunks = chunking.chunk_text_by_transactions(text, max_chunk_size=140, min_transactions_per_chunk=2)
    assert len(chunks) > 1
    assert all(chunk_text for chunk_text, _ in chunks)


def test_merge_transaction_results_dedupes():
    merged = chunking.merge_transaction_results([
        [{'date': '2026-01-01', 'amount': 100.0, 'expense_name': 'A'}],
        [
            {'date': '2026-01-01', 'amount': 100.0, 'expense_name': 'A'},
            {'date': '2026-01-02', 'amount': 200.0, 'expense_name': 'B'},
        ],
    ])

    assert len(merged) == 2
