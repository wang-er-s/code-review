import os
from main import load_config, setup_logging
from git_handler import GitHandler
from pathlib import Path
script_dir = Path(__file__).parent.parent
os.chdir(script_dir)
setup_logging(load_config())
work_repo_path = "E:/git-rep/my-project-work"
git_handler = GitHandler(work_repo_path)
git_handler.update_working_repo()