# -*- coding: utf-8 -*-
import logging
import json
import os
from typing import Dict, List
from pathlib import Path

from git_handler import GitHandler
from llm_client import LLMClient
from feishu_client import FeishuClient
from config1 import Config

logger = logging.getLogger(__name__)


class ReviewEngine:
    """代码审查引擎，协调整个审查流程"""
    
    def __init__(self, config: Config):
        self.config = config
        
        self.git_handler = GitHandler(
            config.git.work_repo_path,
        )
        
        # 获取项目根目录
        project_root = self.git_handler.get_project_root()
        
        # 直接使用Config对象初始化客户端
        self.llm_client = LLMClient(config.llm, project_root=project_root)
        self.feishu_client = FeishuClient(config.feishu)
        
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
        
        if not changed_files or len(changed_files) == 0:
            logger.info("没有需要审查的文件变更")
            self._cache_commit(new_rev)
            return True
        
        if len(changed_files) > self.max_files:
            logger.warning(f"变更文件数 {len(changed_files)} 超过限制 {self.max_files}")
            return True
        
        # 将文件按审查类型分组
        files_by_type = {}
        
        for file_info in changed_files:
            review_type = file_info['review_type']
            if review_type not in files_by_type:
                files_by_type[review_type] = []
            files_by_type[review_type].append(file_info)
        
        review_results = []
        success_count = 0
        
        # 按类型批量审查文件（每种类型一起审查）
        for review_type, file_list in files_by_type.items():
            try:
                logger.info(f"批量审查 {len(file_list)} 个{review_type}类型文件")
                type_results = self._review_multiple_files(old_rev, new_rev, file_list, review_type)
                review_results.extend(type_results)
                success_count += sum(1 for r in type_results if r.get('success', False))
            except Exception as e:
                logger.error(f"批量审查{review_type}类型文件失败: {e}")
                if not self.continue_on_error:
                    self.feishu_client.send_error_notification(str(e), commit_info)
                    return False
        
        logger.info(f"审查完成: 成功 {success_count}/{len(changed_files)} 个文件")
        
        self.feishu_client.send_review_report(commit_info, review_results)
        
        # 只有当所有文件都审查成功时才缓存（避免缓存失败的审查结果）
        if success_count == len(changed_files):
            self._cache_commit(new_rev)
        else:
            logger.warning(f"审查未完全成功 ({success_count}/{len(changed_files)})，不缓存结果")
        
        return success_count > 0
    
    def _review_multiple_files(self, old_rev: str, new_rev: str, file_list: List[Dict], review_type: str) -> List[Dict]:
        """
        批量审查多个同类型文件（同类型文件一起审查）
        
        Args:
            old_rev: 旧版本
            new_rev: 新版本
            file_list: 文件信息列表（必须是同一review_type）
            review_type: 审查类型 (code/unity_asset等)
            
        Returns:
            List[Dict]: 审查结果列表
        """
        if not file_list:
            return []
        
        # 收集所有文件的内容
        all_content_parts = []
        valid_files = []
        
        for file_info in file_list:
            file_path = file_info['path']
            change_type = file_info.get('change_type', 'M')
            
            # 删除的文件跳过
            if change_type == 'D':
                logger.info(f"文件已删除，跳过审查: {file_path}")
                continue
            
            # 检查文件大小
            check_rev = new_rev if change_type in ['A', 'M'] else old_rev
            max_size = self._get_max_file_size(file_info['rule_name'])
            if not self.git_handler.check_file_size(check_rev, file_path, max_size):
                logger.warning(f"文件 {file_path} 过大，跳过审查")
                continue
            
            # 获取文件内容
            content = self._get_file_content(old_rev, new_rev, file_path, change_type, review_type)
            
            if not content:
                logger.warning(f"无法获取文件内容: {file_path}")
                continue
            
            # 添加文件内容到合并内容中，用分隔符分开
            all_content_parts.append(f"\n{'='*80}")
            all_content_parts.append(f"文件: {file_path}")
            all_content_parts.append(f"变更类型: {change_type}")
            all_content_parts.append(f"{'='*80}\n")
            all_content_parts.append(content)
            all_content_parts.append("\n")
            
            valid_files.append(file_info)
        
        if not valid_files:
            logger.warning(f"没有有效的{review_type}类型文件需要审查")
            return []
        
        # 合并所有文件内容
        combined_content = "\n".join(all_content_parts)
        
        # 添加整体说明
        header = f"""
本次审查包含 {len(valid_files)} 个相关的文件，这些文件功能相关联，请整体分析：

文件列表：
"""
        for idx, file_info in enumerate(valid_files, 1):
            header += f"{idx}. {file_info['path']} ({file_info.get('change_type', 'M')})\n"
        
        header += f"\n{'='*80}\n"
        
        combined_content = header + combined_content
        
        # 调用LLM进行批量审查
        logger.info(f"发送 {len(valid_files)} 个{review_type}类型文件进行批量审查")
        review_result = self.llm_client.review_code(
            combined_content, 
            review_type=review_type
        )
        
        # 检查是否是错误结果
        if review_result.get('error', False) or not review_result.get('success', True):
            logger.error(f"批量审查失败: {review_result.get('summary', '未知错误')}")
            # 返回错误结果
            return [{
                'file': f'批量审查({review_type})',
                'review_type': review_type,
                'success': False,
                'result': review_result
            }]
        
        # 解析审查结果，尝试将问题分配到对应的文件
        issues = review_result.get('issues', [])
        
        # 创建文件路径到问题的映射
        file_issues_map = {f['path']: [] for f in valid_files}
        unassigned_issues = []
        
        for issue in issues:
            issue_file = issue.get('file', '')
            assigned = False
            
            # 尝试将问题分配到具体的文件
            for file_info in valid_files:
                file_path = file_info['path']
                # 如果问题指定的文件路径匹配或包含该文件路径
                if issue_file and file_path in issue_file:
                    if not issue.get('file'):
                        issue['file'] = file_path
                    file_issues_map[file_path].append(issue)
                    assigned = True
                    break
            
            # 如果没有分配成功，加入未分配列表
            if not assigned:
                # 如果问题没有指定文件，尝试分配给第一个文件
                if not issue_file and valid_files:
                    issue['file'] = valid_files[0]['path']
                    file_issues_map[valid_files[0]['path']].append(issue)
                else:
                    unassigned_issues.append(issue)
        
        # 为每个文件创建结果对象
        results = []
        for file_info in valid_files:
            file_path = file_info['path']
            file_issues = file_issues_map[file_path]
            
            results.append({
                'file': file_path,
                'review_type': review_type,
                'success': True,
                'result': {
                    'issues': file_issues,
                    'summary': f"批量审查的一部分 ({len(file_issues)} 个问题)"
                }
            })
        
        # 如果有问题没有分配到文件，创建一个汇总结果
        if unassigned_issues:
            results.append({
                'file': '整体评价',
                'review_type': review_type,
                'success': True,
                'result': {
                    'issues': unassigned_issues,
                    'summary': review_result.get('summary', '批量审查完成')
                }
            })
        
        logger.info(f"批量审查完成，共发现 {len(issues)} 个问题")
        return results
    
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
        diff_content = self._get_file_content(old_rev, new_rev, file_path, change_type, review_type)
        
        if not diff_content:
            logger.warning(f"无法获取文件内容: {file_path}")
            return {
                'file': file_path,
                'success': False,
                'result': {'issues': [], 'summary': '无法获取文件内容'}
            }
        
        review_result = self.llm_client.review_code(diff_content, review_type)
        
        # 检查是否是错误结果
        if review_result.get('error', False) or not review_result.get('success', True):
            logger.error(f"文件审查失败 {file_path}: {review_result.get('summary', '未知错误')}")
            return {
                'file': file_path,
                'review_type': review_type,
                'success': False,
                'result': review_result
            }
        
        for issue in review_result.get('issues', []):
            if not issue.get('file'):
                issue['file'] = file_path
        
        return {
            'file': file_path,
            'review_type': review_type,
            'success': True,
            'result': review_result
        }
    
    def _get_file_content(self, old_rev: str, new_rev: str, file_path: str, change_type: str, review_type: str = 'code') -> str:
        """
        获取文件内容（统一方法，支持不同类型的文件）
        
        Args:
            old_rev: 旧版本
            new_rev: 新版本
            file_path: 文件路径
            change_type: 变更类型 (A=新增, M=修改, D=删除)
            review_type: 审查类型 (code/unity_asset等)，用于决定输出格式
            
        Returns:
            str: 文件diff或完整内容
        """
        try:
            # 判断是否需要包含完整内容（asset类型需要）
            include_full_content = (review_type == 'unity_asset')
            file_type_label = "配置文件" if include_full_content else "文件"
            
            if change_type == 'A':
                # 新增文件：获取完整内容
                content = self.git_handler.get_file_content(new_rev, file_path)
                if content:
                    return f"=== 新增{file_type_label} ===\n{file_path}\n\n{content}"
                return ""
            elif change_type == 'M':
                # 修改文件
                if include_full_content:
                    # asset类型：获取diff和完整内容
                    old_content = self.git_handler.get_file_content(old_rev, file_path)
                    new_content = self.git_handler.get_file_content(new_rev, file_path)
                    
                    if not new_content:
                        return ""
                    
                    if not old_content:
                        return f"=== 新增{file_type_label} ===\n{file_path}\n\n{new_content}"
                    
                    diff = self.git_handler.get_file_diff(old_rev, new_rev, file_path)
                    
                    result = f"=== {file_type_label}变更 ===\n{file_path}\n\n"
                    if diff:
                        result += f"变更说明:\n{diff}\n\n"
                    result += f"完整配置内容:\n{new_content}"
                    
                    return result
                else:
                    # code类型：只返回diff
                    return self.git_handler.get_file_diff(old_rev, new_rev, file_path)
            else:
                # 其他情况
                if include_full_content:
                    return ""
                else:
                    # code类型：尝试获取diff
                    return self.git_handler.get_file_diff(old_rev, new_rev, file_path)
        except Exception as e:
            logger.error(f"获取文件内容失败 {file_path}: {e}")
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

