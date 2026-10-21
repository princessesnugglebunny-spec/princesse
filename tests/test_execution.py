from princesse.execution import run_terminal, run_python, read_file, write_file, edit_file, list_dir

def test_run_terminal():
    r = run_terminal("echo hi")
    assert r["returncode"] == 0
    assert "hi" in r["stdout"]

def test_run_python():
    r = run_python("print(2+3)")
    assert r["returncode"] == 0
    assert "5" in r["stdout"]

def test_file_ops(tmp_path):
    p = tmp_path/"f.txt"
    assert write_file(str(p), "hello")["bytes"] == 5
    assert read_file(str(p))["content"] == "hello"
    assert edit_file(str(p), "hello", "world")["replaced"]
    assert read_file(str(p))["content"] == "world"
    assert "entries" in list_dir(str(tmp_path))
