import subprocess
import json
import os
import logging
from typing import Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM CLI工具封装，负责调用外部LLM命令行工具进行代码审查"""
    
    def __init__(self, config: Dict):
        self.cli_path = config.get('cli_path', '')
        self.cli_args = config.get('cli_args', '')
        self.timeout = config.get('timeout', 300)
        self.prompt_templates = config.get('prompt_templates', {})
        self.project_root = config.get('project_root', '')  # 项目根目录
        
        self.temp_dir = Path('temp')
        self.temp_dir.mkdir(exist_ok=True)
        
        logger.info(f"LLM Client初始化: CLI={self.cli_path}")
        if self.project_root:
            logger.info(f"项目根目录: {self.project_root}")
    
    def review_code(self, code_diff: str, file_path: str, review_type: str) -> Dict:
        """
        调用LLM进行代码审查
        
        Args:
            code_diff: 代码diff内容
            file_path: 文件路径
            review_type: 审查类型 (code/unity_asset)
            
        Returns:
            Dict: 审查结果
        """
        try:
            prompt = self._build_prompt(code_diff, review_type)
            
            input_file = self.temp_dir / f"input_{os.getpid()}_{hash(file_path)}.txt"
            output_file = self.temp_dir / f"output_{os.getpid()}_{hash(file_path)}.json"
            
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
            result = self._call_llm_cli(str(input_file), str(output_file))
            
            try:
                input_file.unlink()
                output_file.unlink(missing_ok=True)
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"LLM审查失败 {file_path}: {e}")
            return {
                'issues': [{
                    'severity': 'error',
                    'file': file_path,
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
    

    def _call_llm_cli(self, input_file: str, output_file: str) -> Dict:
        """
        调用LLM CLI工具
        
        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            
        Returns:
            Dict: 解析后的审查结果
        """
        try:
            args = self.cli_args.format(
                input_file=input_file,
                output_file=output_file
            )
            
            cmd = f"{self.cli_path} {args}"
            logger.debug(f"执行LLM CLI: {cmd}")
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                logger.error(f"LLM CLI执行失败: {result.stderr}")
                return self._create_error_result(f"CLI执行失败: {result.stderr}")
            
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            if result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    logger.warning("CLI输出不是有效JSON，尝试从文本提取")
                    return self._parse_text_output(result.stdout)
            
            logger.warning("LLM CLI未返回结果")
            return {'issues': [], 'summary': '无审查结果'}
            
        except subprocess.TimeoutExpired:
            logger.error(f"LLM CLI超时 ({self.timeout}秒)")
            return self._create_error_result(f"LLM调用超时")
        except Exception as e:
            logger.error(f"调用LLM CLI异常: {e}")
            return self._create_error_result(str(e))
    
    def _create_error_result(self, error_msg: str) -> Dict:
        """创建错误结果"""
        return {
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
        
        if not os.path.exists(self.cli_path):
            logger.error(f"LLM CLI不存在: {self.cli_path}")
            return False
        
        return True

