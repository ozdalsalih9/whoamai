import sqlite3

import app.main as main


def test_clean_reply_filters_identity_repetition_and_off_topic_suheyla() -> None:
    reply = (
        "Ben bir yapay zeka olarak cevap veriyorum. "
        "Galatasaray buyuk mac refleksi guclu. "
        "Galatasaray buyuk mac refleksi guclu. "
        "Suheyla Duzce'de yasiyor."
    )

    cleaned = main.clean_reply(reply, "Galatasaray hakkinda ne dusunuyon?", suheyla_mode=False)

    assert "yapay zeka" not in main.fold_turkish(cleaned)
    assert "suheyla" not in main.fold_turkish(cleaned)
    assert cleaned == "Galatasaray buyuk mac refleksi guclu."


def test_load_history_keeps_last_six_messages_in_order_without_latest_user(monkeypatch) -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    rows = [
        ("user", "m1"),
        ("assistant", "a1"),
        ("user", "m2"),
        ("assistant", "a2"),
        ("user", "m3"),
        ("assistant", "a3"),
        ("user", "current"),
    ]
    for role, content in rows:
        connection.execute("INSERT INTO messages (wa_id, role, content) VALUES ('wa1', ?, ?)", (role, content))
    connection.commit()

    class DbContext:
        def __enter__(self) -> sqlite3.Connection:
            return connection

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(main, "db", lambda: DbContext())
    monkeypatch.setattr(main.settings, "max_history_messages", 6)

    history = main.load_history("wa1", exclude_latest_user_text="current")

    assert history == [
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "m2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "m3"},
        {"role": "assistant", "content": "a3"},
    ]


def test_fallback_memory_candidate_uses_explicit_signal_words() -> None:
    assert main.fallback_memory_candidate("Yarin Istanbul'a gidiyorum.") == (
        "Kullanici sunu belirtti: yarin Istanbul'a gidiyorum."
    )
    assert main.fallback_memory_candidate("Naber kanka?") is None


def test_phrase_matching_accepts_turkish_and_ascii_activation() -> None:
    assert main.phrase_matches("hey mustafa, başlat", "hey mustafa, baslat")
    assert main.phrase_matches("hey mustafa, baslat", "hey mustafa, başlat")
