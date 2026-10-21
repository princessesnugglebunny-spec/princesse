from princesse.models_ini import ModelsIni
from pathlib import Path

def test_models_ini(tmp_path):
    p = tmp_path/"models.ini"
    m = ModelsIni(p)
    m.set_section("main", {"model": "/m.gguf", "ctx-size": "4096"})
    m.save(backup=False)
    m2 = ModelsIni(p)
    assert m2.get_section("main")["model"] == "/m.gguf"
    assert "main" in m2.sections()

def test_models_ini_backup(tmp_path):
    p = tmp_path/"models.ini"
    m = ModelsIni(p)
    m.set_section("a", {"x": "1"})
    m.save(backup=False)
    m.set_section("a", {"x": "2"})
    m.save(backup=True)
    backups = list(tmp_path.glob("models.ini.*.bak"))
    assert len(backups) >= 1
