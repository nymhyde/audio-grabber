from pathlib import Path
import subprocess, extractor

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

def _make_clip(path: Path, with_audio=True):
    cmd = [extractor.resolve_ffmpeg(), "-y",
           "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, check=True)

def test_extract_one_ok(tmp_path):
    v = tmp_path / "clip.mp4"; _make_clip(v, with_audio=True)
    out = extractor.output_dir_for(v)
    r = extractor.extract_one(v, out)
    assert r.status == "ok"
    assert r.output.exists() and r.output.suffix == ".mp3"
    assert r.output.stat().st_size > 0

def test_extract_one_no_audio_is_skipped(tmp_path):
    v = tmp_path / "silent.mp4"; _make_clip(v, with_audio=False)
    r = extractor.extract_one(v, extractor.output_dir_for(v))
    assert r.status == "skipped"

def test_extract_one_bad_file_is_error(tmp_path):
    v = tmp_path / "broken.mp4"; v.write_bytes(b"not a video")
    r = extractor.extract_one(v, extractor.output_dir_for(v))
    assert r.status == "error"

def test_unique_path_no_overwrite(tmp_path):
    v = tmp_path / "clip.mp4"; _make_clip(v, with_audio=True)
    out = extractor.output_dir_for(v)
    r1 = extractor.extract_one(v, out)
    r2 = extractor.extract_one(v, out)
    assert r1.output != r2.output
    assert r2.output.name == "clip (2).mp3"
    assert r1.output.exists()  # first not overwritten
