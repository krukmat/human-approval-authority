"""Shared fixed synthetic D3 fixture; no production authority."""
from pathlib import Path
import json
import subprocess

BASE=Path("/Library/WorkflowHAA")
NAME="haa-delta-fixture"
CONTENT="synthetic approved candidate\n"
BEFORE="synthetic initial content\n"
REPOSITORY="fixture/haa-synthetic"
COMMAND=("/usr/bin/grep","-Fx",CONTENT.rstrip("\n"),"README.md")
CARD={"schema_version":2,"card_id":NAME,"task_id":NAME,
      "spec":"Replace the synthetic README with the approved fixture line.",
      "allowed_paths":["README.md"],
      "acceptance_criteria":[{"id":"AC-1","statement":"Exact candidate line in README."}],
      "verification_commands":[{"id":"check","criterion_ids":["AC-1"],"argv":list(COMMAND)}],
      "rri":35,"band":"Moderate","plan":"docs/p.md"}


def card_bytes():
    return json.dumps(CARD,sort_keys=True,separators=(",",":")).encode()


def git(root,*args):
    return subprocess.check_output(["/usr/bin/git","-C",str(root),
       "-c","core.hooksPath=/dev/null","-c","core.fsmonitor=false",*args],
       timeout=15,stderr=subprocess.PIPE,
       env={"PATH":"/usr/bin:/bin","HOME":"/var/empty","LANG":"C",
            "GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
            "GIT_TERMINAL_PROMPT":"0","GIT_NO_REPLACE_OBJECTS":"1"}).decode().strip()


def initialize_repo(root):
    root.mkdir(mode=0o700)
    git(root,"init","-b","candidate")
    git(root,"config","user.name","HAA synthetic")
    git(root,"config","user.email","fixture@example.invalid")
    git(root,"remote","add","origin","https://github.com/"+REPOSITORY+".git")
    (root/"README.md").write_text(BEFORE)
    (root/"docs").mkdir()
    (root/"docs/p.md").write_text("# Synthetic plan\n")
    (root/"docs/tasks.md").write_text("- [ ] "+NAME+"\n")
    (root/"card.json").write_bytes(card_bytes())
    git(root,"add","README.md","docs","card.json")
    git(root,"commit","-m","synthetic base [skip ci]")
    return git(root,"rev-parse","HEAD")
