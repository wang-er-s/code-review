#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
客户端Git Hook处理程序

处理pre-push和post-push hook的逻辑
"""

import sys
import os
import json
import tempfile
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import requests

import git
import yaml

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class ClientHookHandler:
    """客户端Hook处理器"""
    
    def __init__(self, repo_root: str):
        """
        初始化处理器
        
        Args:
            repo_root: Git仓库根目录
        """
        self.repo_root = Path(repo_root).resolve()
        self.repo = git.Repo(self.repo_root)
        
        # 加载配置
        self.config = self._load_config()
        
        # 临时文件目录
        self.temp_dir = Path(tempfile.gettempdir())
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        # 配置文件路径：项目根目录/hooks/config/config.yaml
        config_path = self.repo_root / "hooks" / "config" / "config.yaml"
        if not config_path.exists():
            # 兼容旧路径：client/config/config.yaml
            config_path = self.repo_root / "client" / "config" / "config.yaml"
        if not config_path.exists():
            # 兼容旧路径：仓库根目录的config/config.yaml
            config_path = self.repo_root / "config" / "config.yaml"
        
        if not config_path.exists():
            logger.warning(f"配置文件不存在: {config_path}")
            return {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get('client', {})
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def _get_log_file(self) -> Path:
        """获取日志文件路径"""
        log_file = self.config.get('log_file', 'logs/client_hook.log')
        
        # 如果是相对路径，相对于仓库根目录
        if not Path(log_file).is_absolute():
            log_path = self.repo_root / log_file
        else:
            log_path = Path(log_file)
        
        # 确保日志目录存在
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        return log_path
    
    def _log(self, message: str, level: str = 'INFO'):
        """记录日志"""
        log_file = self._get_log_file()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] [{level}] {message}\n")
        except Exception as e:
            logger.error(f"写入日志失败: {e}")
    
    def _get_state_file(self, branch: str) -> Path:
        """获取状态文件路径"""
        # Windows兼容：使用仓库名和分支名构建文件名
        repo_name = self.repo_root.name or 'repo'
        safe_branch = branch.replace('/', '_').replace('\\', '_')
        filename = f"git_push_state_{repo_name}_{safe_branch}.txt"
        return self.temp_dir / filename
    
    def handle_pre_push(self, remote_name: str, remote_url: str):
        """
        处理pre-push hook
        
        Args:
            remote_name: 远程仓库名称（通常是origin）
            remote_url: 远程仓库URL
        """
        try:
            # 获取当前分支名
            branch = self.repo.active_branch.name
            self._log(f"pre-push: 分支={branch}, 远程={remote_name}")
            
            # 尝试获取远程分支的commit（推送前的状态）
            try:
                remote_ref = f"{remote_name}/{branch}"
                remote_commit = self.repo.commit(remote_ref)
                old_rev = remote_commit.hexsha
                self._log(f"pre-push: 远程分支 {remote_ref} 的commit={old_rev[:8]}")
            except Exception as e:
                # 如果远程分支不存在，使用全0的hash
                old_rev = '0000000000000000000000000000000000000000'
                self._log(f"pre-push: 远程分支不存在，使用初始commit: {e}")
            
            # 保存状态到临时文件
            state_file = self._get_state_file(branch)
            try:
                with open(state_file, 'w', encoding='utf-8') as f:
                    f.write(old_rev)
                self._log(f"pre-push: 状态已保存到 {state_file}")
            except Exception as e:
                self._log(f"pre-push: 保存状态失败: {e}", 'ERROR')
                
        except Exception as e:
            self._log(f"pre-push处理失败: {e}", 'ERROR')
            logger.error(f"pre-push处理失败: {e}", exc_info=True)
    
    def handle_post_push(self, remote_name: str, remote_url: str):
        """
        处理post-push hook
        
        Args:
            remote_name: 远程仓库名称（通常是origin）
            remote_url: 远程仓库URL
        """
        try:
            # 获取当前分支名
            branch = self.repo.active_branch.name
            self._log(f"post-push: 分支={branch}, 远程={remote_name}")
            
            # 检查分支是否需要审查
            review_branches = self.config.get('review_branches', [])
            if review_branches and branch not in review_branches:
                self._log(f"post-push: 分支 {branch} 不在审查列表中，跳过")
                return
            
            # 读取pre-push保存的状态
            state_file = self._get_state_file(branch)
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    old_rev = f.read().strip()
            except FileNotFoundError:
                # 如果状态文件不存在，尝试查询远程分支
                try:
                    remote_ref = f"{remote_name}/{branch}"
                    remote_commit = self.repo.commit(remote_ref)
                    old_rev = remote_commit.hexsha
                    self._log(f"post-push: 状态文件不存在，从远程分支获取: {old_rev[:8]}")
                except Exception:
                    old_rev = '0000000000000000000000000000000000000000'
                    self._log(f"post-push: 无法获取远程状态，使用初始commit")
            
            # 获取当前HEAD（推送后的最新commit）
            new_rev = self.repo.head.commit.hexsha
            ref_name = f"refs/heads/{branch}"
            
            self._log(f"post-push: old_rev={old_rev[:8]}, new_rev={new_rev[:8]}")
            
            # 获取old_rev到new_rev之间的所有commit
            commits = self._get_commits(old_rev, new_rev)
            
            if not commits:
                self._log(f"post-push: 没有新的commit需要审查")
                return
            
            # 构建通知数据
            notification_data = {
                "repository_url": remote_url,
                "branch": branch,
                "old_rev": old_rev,
                "new_rev": new_rev,
                "ref_name": ref_name,
                "commits": commits,
                "push_time": datetime.now().isoformat()
            }
            
            # 发送通知到审查机器
            self._send_notification(notification_data)
            
            # 清理状态文件
            try:
                if state_file.exists():
                    state_file.unlink()
            except Exception:
                pass
                
        except Exception as e:
            self._log(f"post-push处理失败: {e}", 'ERROR')
            logger.error(f"post-push处理失败: {e}", exc_info=True)
    
    def _get_commits(self, old_rev: str, new_rev: str) -> List[Dict]:
        """
        获取两个commit之间的所有commit信息
        
        Args:
            old_rev: 旧commit hash
            new_rev: 新commit hash
            
        Returns:
            commit信息列表
        """
        commits = []
        
        try:
            if old_rev == '0000000000000000000000000000000000000000':
                # 如果是初始commit，获取new_rev的所有父commit
                commit_list = list(self.repo.iter_commits(new_rev))
            else:
                # 获取old_rev..new_rev之间的commit（不包括old_rev，包括new_rev）
                commit_list = list(self.repo.iter_commits(f"{old_rev}..{new_rev}"))
            
            for commit in commit_list:
                commits.append({
                    "hash": commit.hexsha,
                    "author": str(commit.author),
                    "email": commit.author.email,
                    "message": commit.message.strip(),
                    "date": commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')
                })
            
            # 反转列表，使最早的commit在前
            commits.reverse()
            
            self._log(f"获取到 {len(commits)} 个commit")
            
        except Exception as e:
            self._log(f"获取commit列表失败: {e}", 'ERROR')
            logger.error(f"获取commit列表失败: {e}", exc_info=True)
        
        return commits
    
    def _send_notification(self, data: Dict):
        """
        发送通知到审查机器
        
        Args:
            data: 通知数据
        """
        review_machine_url = self.config.get('review_machine_url')
        
        if not review_machine_url:
            self._log("审查机器地址未配置，跳过通知", 'WARNING')
            logger.warning("审查机器地址未配置，请在hooks/config/config.yaml中配置client.review_machine_url")
            return
        
        # 确保URL以/结尾，然后添加review路径
        url = review_machine_url.rstrip('/') + '/review'
        
        try:
            self._log(f"发送通知到审查机器: {url}")
            
            response = requests.post(
                url,
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                self._log(f"通知发送成功: {response.json()}")
            else:
                self._log(f"通知发送失败: HTTP {response.status_code}, {response.text}", 'ERROR')
                
        except requests.exceptions.RequestException as e:
            self._log(f"发送通知异常: {e}", 'ERROR')
            logger.error(f"发送通知异常: {e}", exc_info=True)


def find_repo_root() -> Optional[Path]:
    """查找Git仓库根目录"""
    # 从当前工作目录向上查找.git目录
    current = Path.cwd()
    
    while current != current.parent:
        git_dir = current / '.git'
        if git_dir.exists():
            return current
        current = current.parent
    
    return None


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法: python client_hook_handler.py <hook_type> <remote_name> <remote_url>", file=sys.stderr)
        print("hook_type: pre-push 或 post-push", file=sys.stderr)
        sys.exit(1)
    
    hook_type = sys.argv[1]
    remote_name = sys.argv[2] if len(sys.argv) > 2 else 'origin'
    remote_url = sys.argv[3] if len(sys.argv) > 3 else ''
    
    # 查找仓库根目录
    repo_root = find_repo_root()
    if not repo_root:
        logger.error("未找到Git仓库根目录")
        sys.exit(1)
    
    # 创建处理器
    handler = ClientHookHandler(str(repo_root))
    
    # 根据hook类型处理
    if hook_type == 'pre-push':
        handler.handle_pre_push(remote_name, remote_url)
    elif hook_type == 'post-push':
        handler.handle_post_push(remote_name, remote_url)
    else:
        logger.error(f"未知的hook类型: {hook_type}")
        sys.exit(1)


if __name__ == '__main__':
    main()

