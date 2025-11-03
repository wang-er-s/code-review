# -*- coding: utf-8 -*-
import subprocess
import json
import os
import logging
import shlex
import re
from typing import Dict, List, Optional
from pathlib import Path

from config1 import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM CLI工具封装，负责调用外部LLM命令行工具进行代码审查
    
    支持 OpenAI Codex CLI 和其他通用 CLI 工具
    """
    
    def __init__(self, config: LLMConfig, project_root: str = ''):
        """
        初始化LLM客户端
        
        Args:
            config: LLM配置对象
            project_root: 项目根目录（可选）
        """
        self.cli_path = config.cli_path
        self.cli_type = config.cli_type
        self.cli_args = config.cli_args
        self.timeout = config.timeout
        self.prompt_templates = config.prompt_templates
        self.project_root = project_root
        
        # Codex 特定配置
        self.codex_model = config.codex_model
        
        self.temp_dir = Path('temp')
        self.temp_dir.mkdir(exist_ok=True)
        
        logger.info(f"LLM Client初始化: CLI={self.cli_path}, 类型={self.cli_type}")
        if self.project_root:
            logger.info(f"项目根目录: {self.project_root}")
        if self.cli_type == 'codex':
            logger.info(f"Codex 模型: {self.codex_model or '默认'}")
    
    def review_code(self, code_diff: str, review_type: str = 'code') -> Dict:
        """
        调用LLM进行代码审查
        
        Args:
            code_diff: 代码diff内容（包含需要审查的内容，如果是批量审查，内容中已包含文件路径信息）
            review_type: 审查类型 (code/unity_asset)
            
        Returns:
            Dict: 审查结果
        """
        try:
            prompt = self._build_prompt(code_diff, review_type)
            # 直接传递prompt内容，不需要创建临时文件
            result = self._call_llm_cli(prompt)
            return result
            
        except Exception as e:
            # 尝试提取文件路径用于错误信息
            try:
                file_match = re.search(r'文件:\s*([^\n]+)', code_diff)
                identifier = file_match.group(1).strip() if file_match else "未知文件"
            except:
                identifier = "未知文件"
            logger.error(f"LLM审查失败 {identifier}: {e}")
            return {
                'success': False,  # 标识这是一个错误结果
                'error': True,      # 标识这是一个系统错误
                'issues': [{
                    'severity': 'error',
                    'file': identifier,
                    'line': 0,
                    'message': f'LLM调用失败: {str(e)}',
                    'category': '系统错误'
                }],
                'summary': 'LLM审查失败'
            }
    
    def _build_prompt(self, content: str, review_type: str) -> str:
        """构造审查prompt"""
        template_path = self.prompt_templates.get(review_type, '')
        
        if template_path and os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
        else:
            template = self._get_default_template(review_type)
        
        # 添加项目根目录信息
        project_info = ""
        if self.project_root:
            project_info = f"\n\n【项目根目录】\n{self.project_root}\n\n你可以在审查时参考项目中的其他文件、文档和配置。\n"
        
        if review_type == 'code':
            result = template.replace('{code_diff}', content)
        elif review_type == 'unity_asset':
            result = template.replace('{asset_diff}', content)
        else:
            result = template.replace('{content}', content)
        
        # 在最前面添加项目信息
        if project_info:
            result = project_info + result
        
        return result
    

    def _call_llm_cli(self, prompt_content: str) -> Dict:
        """
        调用LLM CLI工具
        
        Args:
            prompt_content: prompt内容字符串
            
        Returns:
            Dict: 解析后的审查结果
        """
        if self.cli_type == 'codex':
            return self._call_codex_cli(prompt_content)
        raise Exception("不支持的CLI类型: " + self.cli_type)
    
    def _call_codex_cli(self, prompt_content: str) -> Dict:
        """
        调用 OpenAI Codex CLI
        
        参考: https://developers.openai.com/codex/cli/
        
        Args:
            prompt_content: prompt内容字符串
            
        Returns:
            Dict: 解析后的审查结果
        """
        try:
            # 构建 Codex CLI 命令
            # 使用 exec 命令进行非交互式执行
            cmd_parts = [self.cli_path, 'exec']
            
            # 添加模型参数（如果指定）
            if self.codex_model:
                cmd_parts.extend(['--model', self.codex_model])
            
            # 通过 stdin 传递 prompt
            logger.debug(f"执行 Codex CLI: {' '.join(cmd_parts)} [prompt from stdin]")
            
            # 执行命令，通过stdin传递prompt
            # Codex exec 会读取 stdin 作为 prompt
            result = subprocess.run(
                cmd_parts,
                input=prompt_content,
                capture_output=True,
                text=True,
                timeout=self.timeout + 10,  # 给一点额外时间
                encoding='utf-8',
                cwd=self.project_root if self.project_root else None
            )
            
            # 检查退出码
            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else result.stdout
                logger.error(f"Codex CLI执行失败 (退出码 {result.returncode}): {error_msg}")
                return self._create_error_result(f"CLI执行失败: {error_msg[:500]}")
            
            # 解析输出
            output = result.stdout.strip()
            if not output:
                logger.warning("Codex CLI 未返回结果")
                return {'success': True, 'issues': [], 'summary': '无审查结果'}
            
            # Codex 的输出可能是文本或 JSON，尝试解析
            result_dict = self._parse_codex_output(output)
            # 确保正常结果有 success 字段
            if 'success' not in result_dict:
                result_dict['success'] = True
            return result_dict
            
        except subprocess.TimeoutExpired:
            logger.error(f"Codex CLI 超时 ({self.timeout}秒)")
            return self._create_error_result("LLM调用超时")
        except FileNotFoundError:
            logger.error(f"Codex CLI 未找到: {self.cli_path}")
            return self._create_error_result(
                f"CLI工具未找到: {self.cli_path}。请确保已安装: npm install -g @openai/codex 或 brew install codex"
            )
        except Exception as e:
            logger.error(f"调用 Codex CLI 异常: {e}")
            return self._create_error_result(str(e))
    
    def _parse_codex_output(self, output: str) -> Dict:
        """
        解析 Codex CLI 的输出
        
        Codex 的输出可能是：
        1. 纯JSON格式
        2. Markdown格式包含JSON代码块
        3. 普通文本（需要转换为结构化格式）
        
        Args:
            output: CLI输出文本
            
        Returns:
            Dict: 解析后的审查结果
        """
        # 首先尝试直接解析JSON
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass
        
        # 尝试从Markdown代码块中提取JSON
        import re
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',  # ```json {...} ```
            r'```\s*(\{.*?\})\s*```',      # ``` {...} ```
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, output, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        # 尝试在整个输出中查找JSON对象（从第一个 { 到最后一个 }）
        try:
            start_idx = output.find('{')
            end_idx = output.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = output[start_idx:end_idx + 1]
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass
        
        # 如果找不到JSON，尝试从文本中提取结构化信息
        logger.warning("无法从 Codex 输出中提取JSON，使用文本解析")
        return self._parse_text_output(output)
   
    def _create_error_result(self, error_msg: str) -> Dict:
        """创建错误结果"""
        return {
            'success': False,  # 标识这是一个错误结果
            'error': True,     # 标识这是一个系统错误
            'issues': [{
                'severity': 'error',
                'file': '',
                'line': 0,
                'message': error_msg,
                'category': '系统错误'
            }],
            'summary': '审查失败'
        }
    
    def _parse_text_output(self, text: str) -> Dict:
        """尝试从文本输出中提取审查结果"""
        return {
            'success': True,  # 文本输出也算成功（虽然可能不理想）
            'issues': [{
                'severity': 'info',
                'file': '',
                'line': 0,
                'message': text[:500],
                'category': '文本输出'
            }],
            'summary': '已转换为文本格式'
        }
    
    def validate_cli(self) -> bool:
        """验证CLI工具是否可用"""
        if not self.cli_path:
            logger.error("未配置LLM CLI路径")
            return False
        
        if self.cli_type == 'codex':
            # 对于 Codex，检查命令是否在PATH中
            try:
                result = subprocess.run(
                    [self.cli_path, '--help'],
                    capture_output=True,
                    timeout=5,
                    text=True
                )
                if result.returncode == 0 or 'codex' in result.stderr.lower() or 'codex' in result.stdout.lower():
                    logger.info("Codex CLI 验证成功")
                    return True
                else:
                    logger.warning(f"Codex CLI 可能未正确安装: {self.cli_path}")
                    return False
            except FileNotFoundError:
                logger.error(f"Codex CLI 未找到: {self.cli_path}")
                logger.error("请安装: npm install -g @openai/codex 或 brew install codex")
                return False
            except Exception as e:
                logger.warning(f"验证 Codex CLI 时出错: {e}")
                # 不强制失败，允许继续尝试
                return True
        else:
            # 通用CLI验证
            if not os.path.exists(self.cli_path):
                logger.error(f"LLM CLI不存在: {self.cli_path}")
                return False
        
        return True

