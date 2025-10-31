import logging
import json
import os
from typing import Dict, List
from pathlib import Path

from git_handler import GitHandler
from llm_client import LLMClient
from feishu_client import FeishuClient
from config import Config

logger = logging.getLogger(__name__)


class ReviewEngine:
    """代码审查引擎，协调整个审查流程"""
    
    def __init__(self, config: Config):
        self.config = config
        
        self.git_handler = GitHandler(
            config.git.work_repo_path,
        )
        # LLM和Feishu客户端仍使用字典兼容
        config_dict = config.to_dict()
        # 添加项目根目录给LLM
        config_dict['llm']['project_root'] = self.git_handler.get_project_root()
        
        self.llm_client = LLMClient(config_dict['llm'])
        self.feishu_client = FeishuClient(config_dict['feishu'])
        
        self.file_rules = [rule for rule in config.review.file_rules]
        self.max_files = config.advanced.max_files_per_commit
        self.continue_on_error = config.advanced.continue_on_error
        
        self.cache_enabled = config.advanced.enable_cache
        self.cache_file = Path(config.advanced.cache_file)
        
        logger.info("ReviewEngine初始化完成")
    
    def review_commit(self, old_rev: str, new_rev: str, ref_name: str) -> bool:
        """
        审查单次提交
        
        Args:
            old_rev: 旧版本hash
            new_rev: 新版本hash
            ref_name: 分支引用名（如 refs/heads/master）
            
        Returns:
            bool: 审查是否成功
        """
        logger.info(f"开始审查: {old_rev[:8]}..{new_rev[:8]} ({ref_name})")
        
        # 先更新工作仓库
        branch = ref_name.replace('refs/heads/', '')
        if not self.git_handler.update_working_repo(branch):
            logger.error("工作仓库更新失败，终止审查")
            return False
        
        if self._is_cached(new_rev):
            logger.info(f"Commit {new_rev[:8]} 已审查过，跳过")
            return True
        
        commit_info = self.git_handler.get_commit_info(new_rev)
        if not commit_info:
            logger.error("无法获取commit信息")
            return False
        
        logger.info(f"审查提交: {commit_info['message'][:50]} by {commit_info['author']}")
        
        changed_files = self.git_handler.get_changed_files(old_rev, new_rev, self.file_rules)
        
        if not changed_files:
            logger.info("没有需要审查的文件变更")
            self._cache_commit(new_rev)
            return True
        
        if len(changed_files) > self.max_files:
            logger.warning(f"变更文件数 {len(changed_files)} 超过限制 {self.max_files}")
            return True
        
        review_results = []
        success_count = 0
        
        for file_info in changed_files:
            try:
                result = self._review_single_file(old_rev, new_rev, file_info)
                review_results.append(result)
                
                if result.get('success', False):
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"审查文件失败 {file_info['path']}: {e}")
                if not self.continue_on_error:
                    self.feishu_client.send_error_notification(str(e), commit_info)
                    return False
        
        logger.info(f"审查完成: 成功 {success_count}/{len(changed_files)} 个文件")
        
        self.feishu_client.send_review_report(commit_info, review_results)
        
        self._cache_commit(new_rev)
        
        return success_count > 0
    
    def _review_single_file(self, old_rev: str, new_rev: str, file_info: Dict) -> Dict:
        """
        审查单个文件
        
        Args:
            old_rev: 旧版本
            new_rev: 新版本
            file_info: 文件信息（包含path, change_type, review_type等）
            
        Returns:
            Dict: 审查结果
        """
        file_path = file_info['path']
        review_type = file_info['review_type']
        change_type = file_info.get('change_type', 'M')
        
        logger.info(f"审查文件: {file_path} (类型: {review_type}, 变更: {change_type})")
        
        # 删除的文件通常不需要审查（可选：如果需要可以审查删除原因）
        if change_type == 'D':
            logger.info(f"文件已删除，跳过审查: {file_path}")
            return {
                'file': file_path,
                'success': True,
                'result': {
                    'issues': [],
                    'summary': '文件已删除'
                }
            }
        
        # 对于新增或修改的文件，检查大小
        check_rev = new_rev if change_type in ['A', 'M'] else old_rev
        max_size = self._get_max_file_size(file_info['rule_name'])
        if not self.git_handler.check_file_size(check_rev, file_path, max_size):
            logger.warning(f"文件 {file_path} 过大，跳过审查")
            return {
                'file': file_path,
                'success': False,
                'result': {
                    'issues': [{
                        'severity': 'warning',
                        'file': file_path,
                        'line': 0,
                        'message': f'文件过大(>{max_size}行)，已跳过审查',
                        'category': '系统限制'
                    }],
                    'summary': '文件过大'
                }
            }
        
        # 获取文件内容
        if review_type == 'unity_asset':
            diff_content = self._get_asset_content(old_rev, new_rev, file_path, change_type)
        else:
            diff_content = self._get_code_content(old_rev, new_rev, file_path, change_type)
        
        if not diff_content:
            logger.warning(f"无法获取文件内容: {file_path}")
            return {
                'file': file_path,
                'success': False,
                'result': {'issues': [], 'summary': '无法获取文件内容'}
            }
        
        review_result = self.llm_client.review_code(diff_content, file_path, review_type)
        
        for issue in review_result.get('issues', []):
            if not issue.get('file'):
                issue['file'] = file_path
        
        return {
            'file': file_path,
            'review_type': review_type,
            'success': True,
            'result': review_result
        }
    
    def _get_code_content(self, old_rev: str, new_rev: str, file_path: str, change_type: str) -> str:
        """
        获取代码文件内容
        
        Args:
            old_rev: 旧版本
            new_rev: 新版本
            file_path: 文件路径
            change_type: 变更类型 (A=新增, M=修改, D=删除)
            
        Returns:
            str: 文件diff或完整内容
        """
        try:
            if change_type == 'A':
                # 新增文件：直接获取完整内容
                content = self.git_handler.get_file_content(new_rev, file_path)
                if content:
                    return f"=== 新增文件 ===\n{file_path}\n\n{content}"
                return ""
            elif change_type == 'M':
                # 修改文件：获取diff
                return self.git_handler.get_file_diff(old_rev, new_rev, file_path)
            else:
                # 其他情况也尝试获取diff
                return self.git_handler.get_file_diff(old_rev, new_rev, file_path)
        except Exception as e:
            logger.error(f"获取代码内容失败 {file_path}: {e}")
            return ""
    
    def _get_asset_content(self, old_rev: str, new_rev: str, file_path: str, change_type: str) -> str:
        """
        获取asset文件内容（包含变更标记）
        
        对于asset文件，我们需要完整内容来理解配置，同时标注变更部分
        
        Args:
            old_rev: 旧版本
            new_rev: 新版本
            file_path: 文件路径
            change_type: 变更类型 (A=新增, M=修改, D=删除)
        """
        try:
            if change_type == 'A':
                # 新增文件：只获取新内容
                new_content = self.git_handler.get_file_content(new_rev, file_path)
                if new_content:
                    return f"=== 新增配置文件 ===\n{file_path}\n\n{new_content}"
                return ""
            elif change_type == 'M':
                # 修改文件：获取新旧内容和diff
                old_content = self.git_handler.get_file_content(old_rev, file_path)
                new_content = self.git_handler.get_file_content(new_rev, file_path)
                
                if not new_content:
                    return ""
                
                if not old_content:
                    return f"=== 新增配置文件 ===\n{file_path}\n\n{new_content}"
                
                diff = self.git_handler.get_file_diff(old_rev, new_rev, file_path)
                
                result = f"=== 配置文件变更 ===\n{file_path}\n\n"
                if diff:
                    result += f"变更说明:\n{diff}\n\n"
                result += f"完整配置内容:\n{new_content}"
                
                return result
            else:
                return ""
        except Exception as e:
            logger.error(f"获取Asset内容失败 {file_path}: {e}")
            return ""
    
    def _get_max_file_size(self, rule_name: str) -> int:
        """获取文件规则的最大行数限制"""
        for rule in self.file_rules:
            if rule.name == rule_name:
                return rule.max_file_size
        return 10000
    
    def _is_cached(self, commit_hash: str) -> bool:
        """检查commit是否已审查过"""
        if not self.cache_enabled:
            return False
        
        if not self.cache_file.exists():
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
                return commit_hash in cache.get('reviewed_commits', [])
        except:
            return False
    
    def _cache_commit(self, commit_hash: str):
        """缓存已审查的commit"""
        if not self.cache_enabled:
            return
        
        try:
            cache = {'reviewed_commits': []}
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
            
            if commit_hash not in cache['reviewed_commits']:
                cache['reviewed_commits'].append(commit_hash)
            
            cache['reviewed_commits'] = cache['reviewed_commits'][-1000:]
            
            self.cache_file.parent.mkdir(exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
                
        except Exception as e:
            logger.error(f"缓存commit失败: {e}")

