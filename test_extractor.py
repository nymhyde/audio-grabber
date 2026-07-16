from pathlib import Path
import extractor

def test_find_videos_filters_and_recurses(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "c.MOV").write_bytes(b"x")  # case-insensitive
    got = extractor.find_videos([tmp_path])
    names = sorted(p.name for p in got)
    assert names == ["a.mp4", "c.MOV"]

def test_find_videos_single_file_and_dedup(tmp_path):
    f = tmp_path / "a.mp4"; f.write_bytes(b"x")
    got = extractor.find_videos([f, f, tmp_path])
    assert got == [f]

def test_output_dir_for(tmp_path):
    f = tmp_path / "a.mp4"; f.write_bytes(b"x")
    assert extractor.output_dir_for(f) == tmp_path / "MP3"
    assert extractor.output_dir_for(tmp_path) == tmp_path / "MP3"
