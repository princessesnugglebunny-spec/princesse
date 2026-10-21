from princesse.skills import parse_skill, SkillRegistry

def test_parse_skill(tmp_path):
    text = "---\nname: greet\ndescription: hi\n---\n\nHello {name}"
    skill = parse_skill(text)
    assert skill.name == "greet"
    assert "Hello" in skill.content

def test_registry(tmp_path):
    d = tmp_path/"skills"
    d.mkdir()
    (d/"greet.md").write_text("---\nname: greet\ndescription: hi\n---\nbody")
    reg = SkillRegistry(directory=d)
    assert reg.get("greet") is not None
    reg.register(parse_skill("---\nname: x\ndescription: y\n---\nbody"), persist=True)
    assert (d/"x.md").exists()
