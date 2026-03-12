from src.llm import chunking


def test_safe_env_int_clamps(monkeypatch):
    monkeypatch.setenv('MAX_CHUNK_SIZE', '999999')
    assert chunking.safe_env_int('MAX_CHUNK_SIZE', 3500, maximum=20000) == 20000


def test_get_chunking_config_reads_env(monkeypatch):
    monkeypatch.setenv('ENABLE_ADAPTIVE_CHUNKING', 'false')
    monkeypatch.setenv('MAX_CHUNK_SIZE', '1200')
    monkeypatch.setenv('MIN_TRANSACTIONS_PER_CHUNK', '2')
    monkeypatch.setenv('FORCE_CHUNKING_TEXT_LENGTH', '1500')

    cfg = chunking.get_chunking_config()
    assert cfg['enabled'] is False
    assert cfg['max_chunk_size'] == 1200
    assert cfg['min_transactions_per_chunk'] == 2
    assert cfg['force_threshold'] == 1500


def test_should_enable_chunking_by_force_threshold(monkeypatch):
    monkeypatch.setenv('ENABLE_ADAPTIVE_CHUNKING', 'true')
    monkeypatch.setenv('FORCE_CHUNKING_TEXT_LENGTH', '1000')

    text = 'x' * 1001
    assert chunking.should_enable_chunking(text, {'sender_tag': 'foo'}) is True


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
