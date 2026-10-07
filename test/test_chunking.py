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


def test_should_enable_chunking_hsbc_long_text_dates_and_force():
    hsbc = {'sender_tag': 'hsbc'}
    assert chunking.should_enable_chunking('HSBC' * 2000, hsbc) is True
    assert chunking.should_enable_chunking('HSBC' * 2000, {'sender_tag': 'foo'}) is False
    assert chunking.should_enable_chunking('Small text', hsbc) is False

    many_dates = '\n'.join(f'2024-01-{i:02d} x' for i in range(1, 31))
    assert chunking.should_enable_chunking(many_dates, {'sender_tag': 'foo'}) is True
    assert chunking.should_enable_chunking('Small text', {'sender_tag': 'foo'}, force=True) is True


def test_chunk_text_by_transactions_keeps_every_transaction():
    text = '\n'.join(f'2024-01-{i:02d} NT${i * 100}.00 Transaction {i}' for i in range(1, 31))

    chunks = chunking.chunk_text_by_transactions(text, max_chunk_size=500)

    assert len(chunks) == 3
    assert all(len(chunk_text) <= 500 for chunk_text, _ in chunks)
    assert sum(len(indices) for _, indices in chunks) == 30
