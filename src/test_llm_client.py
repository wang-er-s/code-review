#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Client 测试脚本

用法:
    python test_llm_client.py [选项]

示例:
    # 使用配置文件中的设置
    python test_llm_client.py

    # 测试自定义代码
    python test_llm_client.py --code "def test(): return 1"

    # 测试 Codex CLI
    python test_llm_client.py --cli-type codex

    # 测试通用 CLI
    python test_llm_client.py --cli-type generic --cli-path "python" --cli-args "mock_llm_cli.py --input {input_file} --output {output_file}"
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import LLMClient
from config1 import LLMConfig, Config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def load_config_from_file(config_path: str = 'config/config.yaml') -> LLMConfig:
    """从配置文件加载 LLM 配置"""
    try:
        config = Config.from_yaml(config_path)
        return config.llm
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        raise


def create_test_config(args) -> LLMConfig:
    """创建测试配置"""
    if args.config:
        return load_config_from_file(args.config)
    
    # 从配置文件加载
    try:
        return load_config_from_file()
    except:
        pass
    
    # 使用命令行参数创建配置
    prompt_templates = {}
    if args.prompt_template:
        prompt_templates['code'] = args.prompt_template
    
    # 根据 CLI 类型设置默认路径
    default_cli_path = 'codex'
    default_cli_type = 'codex'
    
    return LLMConfig(
        cli_path=args.cli_path or default_cli_path,
        cli_type=args.cli_type or default_cli_type,
        cli_args=args.cli_args or '',
        timeout=args.timeout or 300,
        prompt_templates=prompt_templates,
        codex_model=args.codex_model or ''
    )


def test_validate_cli(client: LLMClient):
    """测试 CLI 验证"""
    print("\n" + "="*60)
    print("测试 1: CLI 工具验证")
    print("="*60)
    
    is_valid = client.validate_cli()
    
    if is_valid:
        print("✅ CLI 工具验证通过")
    else:
        print("❌ CLI 工具验证失败")
        print("   请检查 CLI 工具是否正确安装和配置")
    
    return is_valid


def test_review_code(client: LLMClient, code_diff: str, file_path: str = "test.py", review_type: str = "code"):
    """测试代码审查"""
    print("\n" + "="*60)
    print("测试 2: 代码审查")
    print("="*60)
    print(f"文件路径: {file_path}")
    print(f"审查类型: {review_type}")
    print(f"代码内容:\n{code_diff[:200]}...")
    print("-"*60)
    
    try:
        result = client.review_code(code_diff, file_path, review_type)
        
        print("\n审查结果:")
        print(f"  问题数量: {len(result.get('issues', []))}")
        print(f"  总结: {result.get('summary', '无')}")
        
        issues = result.get('issues', [])
        if issues:
            print("\n问题详情:")
            for i, issue in enumerate(issues[:10], 1):  # 最多显示10个问题
                severity = issue.get('severity', 'unknown')
                severity_icon = {
                    'error': '❌',
                    'warning': '⚠️',
                    'info': 'ℹ️'
                }.get(severity, '❓')
                
                print(f"\n  {i}. {severity_icon} [{severity.upper()}] {issue.get('category', '未知')}")
                print(f"     文件: {issue.get('file', file_path)}")
                print(f"     行号: {issue.get('line', 0)}")
                print(f"     消息: {issue.get('message', '')[:100]}")
            
            if len(issues) > 10:
                print(f"\n  ... 还有 {len(issues) - 10} 个问题未显示")
        else:
            print("  ✅ 未发现问题")
        
        return result
        
    except Exception as e:
        print(f"❌ 代码审查失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description='LLM Client 测试脚本')
    
    # 配置选项
    parser.add_argument('--config', type=str, help='配置文件路径 (默认: config/config.yaml)')
    parser.add_argument('--cli-type', choices=['codex', 'generic'], help='CLI 类型')
    parser.add_argument('--cli-path', type=str, help='CLI 工具路径')
    parser.add_argument('--cli-args', type=str, help='CLI 参数模板')
    parser.add_argument('--timeout', type=int, help='超时时间（秒）')
    parser.add_argument('--codex-model', type=str, help='Codex 模型 (gpt-5-codex, gpt-5 等)')
    parser.add_argument('--prompt-template', type=str, help='Prompt 模板路径')
    parser.add_argument('--project-root', type=str, help='项目根目录')
    
    # 测试选项
    parser.add_argument('--code', type=str, help='要审查的代码内容')
    parser.add_argument('--file', type=str, help='代码文件路径（读取文件内容）')
    parser.add_argument('--review-type', choices=['code', 'unity_asset'], default='code', help='审查类型')
    parser.add_argument('--skip-validation', action='store_true', help='跳过 CLI 验证')
    
    args = parser.parse_args()
    
    print("="*60)
    print("LLM Client 测试工具")
    print("="*60)
    
    # 创建配置
    try:
        llm_config = create_test_config(args)
        print(f"\n配置信息:")
        print(f"  CLI 类型: {llm_config.cli_type}")
        print(f"  CLI 路径: {llm_config.cli_path}")
        print(f"  超时时间: {llm_config.timeout}秒")
        if llm_config.cli_type == 'codex':
            print(f"  Codex 模型: {llm_config.codex_model or '默认'}")
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return 1
    
    # 创建客户端
    project_root = args.project_root or os.getcwd()
    client = LLMClient(llm_config, project_root=project_root)
    
    # 测试 CLI 验证
    if not args.skip_validation:
        if not test_validate_cli(client):
            print("\n⚠️  警告: CLI 验证失败，但继续测试...")
    
    # 准备测试代码
    code_diff = ""
    file_path = "test.py"
    
    if args.file:
        # 从文件读取
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                code_diff = f.read()
            file_path = args.file
        except Exception as e:
            print(f"❌ 读取文件失败: {e}")
            return 1
    elif args.code:
        # 使用命令行参数
        code_diff = args.code
    else:
        # 使用默认测试代码
        code_diff = """def calculate_total(items):
    total = 0
    for item in items:
        total += item.price
    return total

class Order:
    def __init__(self, items):
        self.items = items
    
    def get_total(self):
        return calculate_total(self.items)
"""
        print("\n使用默认测试代码...")
    
    # 测试代码审查
    result = test_review_code(client, code_diff, file_path, args.review_type)
    
    # 总结
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)
    
    if result:
        print("✅ 测试成功")
        return 0
    else:
        print("❌ 测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())

