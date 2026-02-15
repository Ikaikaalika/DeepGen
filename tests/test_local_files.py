from pathlib import Path

from deepgen.services.local_files import index_local_folder, search_local_records


def test_index_local_folder_lists_supported_files(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("ancestor reference", encoding="utf-8")
    (tmp_path / "photo.jpg").write_bytes(b"fake")
    (tmp_path / "ignore.bin").write_bytes(b"x")

    idx = index_local_folder(str(tmp_path), max_files=20)
    assert idx.file_count == 2
    assert any("notes.txt" in p for p in idx.sample_files)


def test_search_local_records_matches_name_tokens(tmp_path: Path):
    target = tmp_path / "john_doe_1900_notes.txt"
    target.write_text("John Doe b. 1900 likely son of ...", encoding="utf-8")

    hits = search_local_records(str(tmp_path), name="John Doe", birth_year=1900, max_results=5)
    assert len(hits) == 1
    assert hits[0].title == "john_doe_1900_notes.txt"
    assert hits[0].source == "local_folder"
