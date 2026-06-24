from __future__ import annotations

from pathlib import Path

from chatbot_backend.scripts import init_vector_collection


def test_run_does_not_print_pgvector_connection_secret(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    secret_connection = (
        "postgresql+psycopg://mamute:secret-password@db.internal:5432/mamute"
        "?sslmode=require"
    )
    dummy_engine = object()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PGVECTOR_CONNECTION", secret_connection)
    monkeypatch.setenv("PGVECTOR_COLLECTION", "test_collection")
    monkeypatch.setenv("APPLICATION_NAME", "test_app")
    monkeypatch.setattr(
        init_vector_collection,
        "_create_engine",
        lambda connection, application_name: dummy_engine,
    )
    monkeypatch.setattr(init_vector_collection, "_ensure_extensions", lambda engine: None)
    monkeypatch.setattr(init_vector_collection, "_existing_dimension", lambda engine: None)
    monkeypatch.setattr(
        init_vector_collection,
        "_ensure_tables",
        lambda engine, dimension: None,
    )
    monkeypatch.setattr(
        init_vector_collection,
        "_ensure_collection",
        lambda engine, collection_name: None,
    )

    init_vector_collection.run(force_dimension=1536)

    output = capsys.readouterr().out
    assert secret_connection not in output
    assert "secret-password" not in output
    assert "postgresql+psycopg://mamute:***@db.internal:5432/mamute" in output
