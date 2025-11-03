# -*- coding: utf-8 -*-
import git
import os
import fnmatch
from typing import List, Dict, Tuple, Optional
import logging

from config1 import FileRule

logger = logging.getLogger(__name__)


class GitHandler:
    """处理Git仓库操作，支持bare仓库和工作仓库"""
    
    def __init__(self, work_repo_path: str):
        self.work_repo_path = os.path.abspath(work_repo_path)
        
        try:
            # 连接工作仓库（用于读取文件和获取变更）
            self.repo = git.Repo(self.work_repo_path)
            
            # 这很重要：确保Git命令在正确的环境下执行
            self.repo.git.update_environment(
                LANG='C.UTF-8', 
                LC_ALL='C.UTF-8',
                GIT_TERMINAL_PROMPT='0',
                LC_MESSAGES='C',
                # 关键：告诉Git在哪个目录工作
                GIT_DIR=os.path.join(self.work_repo_path, '.git'),
                GIT_WORK_TREE=self.work_repo_path
            )
            
            
            logger.info(f"成功连接到工作仓库: {self.work_repo_path}")
            logger.info(f"Git工作目录: {self.work_repo_path}")
        except Exception as e:
            logger.error(f"无法打开工作仓库 {work_repo_path}: {e}")
            raise
    
    def update_working_repo(self, branch: str = 'master') -> bool:
        """
        更新工作仓库（git pull）
        
        Args:
            branch: 要更新的分支名
            
        Returns:
            bool: 是否更新成功
        """
        try:
            logger.info(f"正在更新工作仓库: {self.work_repo_path}")
            
            # 获取当前分支
            current_branch = self.repo.active_branch.name
            logger.info(f"当前分支: {current_branch}")
            
            # 如果需要切换分支
            if current_branch != branch:
                logger.info(f"切换分支: {current_branch} -> {branch}")
                self.repo.git.checkout(branch)
            
            # Pull更新（直接使用git命令，避免GitPython的参数问题）
            logger.info(f"执行 git pull origin {branch}")
            pull_result = self.repo.git.pull('origin', branch)
            logger.info(f"Pull结果: {pull_result}")
            
            logger.info("工作仓库更新成功")
            return True
            
        except Exception as e:
            logger.error(f"更新工作仓库失败: {e}")
            return False
    
    def get_project_root(self) -> str:
        """获取项目根目录路径（供LLM读取其他文件）"""
        return self.work_repo_path
    
    def get_commit_info(self, commit_hash: str) -> Dict:
        """获取提交信息"""
        try:
            commit = self.repo.commit(commit_hash)
            return {
                'hash': commit.hexsha,
                'author': str(commit.author),
                'email': commit.author.email,
                'message': commit.message.strip(),
                'date': commit.committed_datetime.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            logger.error(f"获取commit信息失败 {commit_hash}: {e}")
            return {}
    
    def get_changed_files(self, old_rev: str, new_rev: str, file_rules: List[FileRule]) -> List[Dict]:
        """
        获取变更的文件列表并分类
        
        Args:
            old_rev: 旧版本commit hash
            new_rev: 新版本commit hash
            file_rules: 文件规则列表
            
        Returns:
            List[Dict]: 变更文件信息列表
        """
        changed_files = []
        
        try:
            if old_rev == '0000000000000000000000000000000000000000':
                diff_index = self.repo.commit(new_rev).tree.traverse()
                diffs = [(item.path, 'A') for item in diff_index if item.type == 'blob']
            else:
                old_commit = self.repo.commit(old_rev)
                new_commit = self.repo.commit(new_rev)
                diff_index = old_commit.diff(new_commit)
                diffs = [(diff.b_path if diff.b_path else diff.a_path, diff.change_type) 
                        for diff in diff_index]
            
            for file_path, change_type in diffs:
                matched_rule = self._match_file_rule(file_path, file_rules)
                
                if matched_rule:
                    file_info = {
                        'path': file_path,
                        'change_type': change_type,
                        'review_type': matched_rule.review_type,
                        'rule_name': matched_rule.name
                    }
                    changed_files.append(file_info)
                    logger.debug(f"匹配文件: {file_path} -> {matched_rule.name}")
            
            logger.info(f"找到 {len(changed_files)} 个需要审查的文件")
            return changed_files
            
        except Exception as e:
            logger.error(f"获取变更文件列表失败: {e}")
            return []
    
    def _match_file_rule(self, file_path: str, file_rules: List[FileRule]) -> Optional[FileRule]:
        """
        匹配文件规则
        
        Args:
            file_path: 文件路径
            file_rules: 文件规则列表
            
        Returns:
            Optional[FileRule]: 匹配的规则对象，如果没有匹配则返回None
        """
        for rule in file_rules:
            if self._is_excluded(file_path, rule.exclude_patterns):
                continue
            
            if rule.path_pattern:
                if fnmatch.fnmatch(file_path, rule.path_pattern):
                    return rule
            
            if rule.extensions:
                _, ext = os.path.splitext(file_path)
                if ext in rule.extensions:
                    return rule
        
        return None
    
    def _is_excluded(self, file_path: str, exclude_patterns: List[str]) -> bool:
        """检查文件是否被排除"""
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_path, f"*{pattern}"):
                return True
        return False
    
    def get_file_diff(self, old_rev: str, new_rev: str, file_path: str) -> str:
        """
        获取单个文件的diff
        
        Args:
            old_rev: 旧版本
            new_rev: 新版本
            file_path: 文件路径
            
        Returns:
            str: diff内容
        """
        try:
            if old_rev == '0000000000000000000000000000000000000000':
                content = self.get_file_content(new_rev, file_path)
                return f"+++ 新文件: {file_path}\n{content}"
            
            # 使用 -- 分隔符明确指定这是文件路径
            diff_output = self.repo.git.diff(
                old_rev, new_rev, 
                '--', file_path,
                unified=5, 
                no_color=True
            )
            return diff_output
            
        except Exception as e:
            logger.error(f"获取文件diff失败 {file_path}: {e}")
            # 如果diff失败，尝试直接获取新文件内容
            try:
                content = self.get_file_content(new_rev, file_path)
                if content:
                    return f"+++ 文件变更: {file_path}\n{content}"
            except:
                pass
            return ""
    
    def get_file_content(self, commit_hash: str, file_path: str) -> str:
        """
        获取指定commit中的文件完整内容
        
        优化：如果请求的是当前HEAD的文件，直接从文件系统读取（更快）
        
        Args:
            commit_hash: commit hash
            file_path: 文件路径
            
        Returns:
            str: 文件内容
        """
        try:
            # 优化：如果是当前HEAD，直接读取文件系统（避免Git命令）
            current_head = self.repo.head.commit.hexsha
            if commit_hash == current_head or commit_hash == 'HEAD':
                full_path = os.path.join(self.work_repo_path, file_path)
                if os.path.exists(full_path):
                    logger.debug(f"[优化] 直接从文件系统读取: {file_path}")
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()
                else:
                    logger.warning(f"文件不存在: {full_path}")
                    return ""
            
            # 历史版本：仍需使用Git命令
            logger.debug(f"[Git命令] 读取历史版本: {commit_hash[:8]}:{file_path}")
            content = self.repo.git.show(f"{commit_hash}:{file_path}")
            return content
            
        except Exception as e:
            logger.warning(f"获取文件内容失败 {commit_hash}:{file_path}: {e}")
            return ""
    
    def get_file_line_count(self, commit_hash: str, file_path: str) -> int:
        """获取文件行数"""
        try:
            content = self.get_file_content(commit_hash, file_path)
            return len(content.splitlines())
        except:
            return 0
    
    def check_file_size(self, commit_hash: str, file_path: str, max_lines: int) -> bool:
        """检查文件大小是否超限"""
        line_count = self.get_file_line_count(commit_hash, file_path)
        if line_count > max_lines:
            logger.warning(f"文件 {file_path} 行数 {line_count} 超过限制 {max_lines}")
            return False
        return True

