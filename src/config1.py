# -*- coding: utf-8 -*-
"""
配置类定义

将YAML配置解析为Python类，提供类型提示和验证
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import yaml


@dataclass
class FileRule:
    """文件审查规则"""
    name: str
    extensions: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    max_file_size: int = 10000
    review_type: str = "code"
    path_pattern: Optional[str] = None


@dataclass
class GitConfig:
    """Git仓库配置"""
    work_repo_path: str  # 工作仓库路径（用于审查和读取文档）


@dataclass
class ReviewConfig:
    """审查配置"""
    file_rules: List[FileRule]


@dataclass
class LLMConfig:
    """LLM配置"""
    cli_path: str
    cli_type: str = "codex"  # 'codex' 或 'generic'
    cli_args: str = "--input {input_file} --output {output_file}"
    timeout: int = 300
    prompt_templates: Dict[str, str] = field(default_factory=dict)
    codex_model: str = ""  # Codex 模型: gpt-5-codex, gpt-5 等（留空使用默认）


@dataclass
class FeishuConfig:
    """飞书配置"""
    webhook_url: str
    enable: bool = True
    mention_all: bool = False
    show_code_snippet: bool = True
    max_snippet_lines: int = 10


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    file: str = "logs/review.log"
    retention_days: int = 30


@dataclass
class AdvancedConfig:
    """高级配置"""
    enable_cache: bool = True
    cache_file: str = "temp/review_cache.json"
    max_files_per_commit: int = 50
    continue_on_error: bool = True


@dataclass
class Config:
    """完整配置"""
    git: GitConfig
    review: ReviewConfig
    llm: LLMConfig
    feishu: FeishuConfig
    logging: LoggingConfig
    advanced: AdvancedConfig
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'Config':
        """从YAML文件加载配置"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        return cls(
            git=GitConfig(**data['git']),
            review=ReviewConfig(
                file_rules=[FileRule(**rule) for rule in data['review']['file_rules']]
            ),
            llm=LLMConfig(**data['llm']),
            feishu=FeishuConfig(**data['feishu']),
            logging=LoggingConfig(**data['logging']),
            advanced=AdvancedConfig(**data['advanced'])
        )
    
    def validate(self) -> List[str]:
        """验证配置有效性，返回错误列表"""
        errors = []
        
        # 验证Git仓库路径
        if not Path(self.git.work_repo_path).exists():
            errors.append(f"工作仓库路径不存在: {self.git.work_repo_path}")
        
        # 检查工作仓库是否是有效的git仓库
        if Path(self.git.work_repo_path).exists():
            git_dir = Path(self.git.work_repo_path) / '.git'
            if not git_dir.exists():
                errors.append(f"工作仓库路径不是有效的Git仓库: {self.git.work_repo_path}")
        
        # 验证LLM CLI
        if not self.llm.cli_path:
            errors.append("LLM CLI路径未配置")
        
        # 验证文件规则
        if not self.review.file_rules:
            errors.append("未配置文件审查规则")
        
        for rule in self.review.file_rules:
            if not rule.extensions and not rule.path_pattern:
                errors.append(f"文件规则 '{rule.name}' 必须指定 extensions 或 path_pattern")
            if rule.review_type not in ['code', 'unity_asset']:
                errors.append(f"文件规则 '{rule.name}' 的 review_type 必须是 'code' 或 'unity_asset'")
        
        # 验证日志级别
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
        if self.logging.level not in valid_levels:
            errors.append(f"日志级别必须是 {valid_levels} 之一")
        
        return errors