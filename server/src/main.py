#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git代码审查服务主入口

用法:
    python main.py <old_rev> <new_rev> <ref_name>
    
示例:
    python main.py abc123 def456 refs/heads/main
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# 将src目录添加到Python路径，以便导入其他模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from review_engine import ReviewEngine
from config1 import Config


def setup_logging(config: Config):
    """配置日志"""
    log_level = getattr(logging, config.logging.level)
    log_file = config.logging.file
    
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)
    
    # 配置文件handler（UTF-8）和控制台handler（避免编码问题）
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    
    # 控制台handler - Windows下使用errors='replace'避免编码错误
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    
    logging.basicConfig(
        level=log_level,
        handlers=[file_handler, console_handler]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info(f"Code Review Service Started - {datetime.now()}")
    return logger


def load_config(config_path: str = 'config/config.yaml') -> Config:
    """加载配置文件"""
    try:
        config = Config.from_yaml(config_path)
        
        # 验证配置
        errors = config.validate()
        if errors:
            print("配置验证失败:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            sys.exit(1)
        
        return config
    except Exception as e:
        print(f"加载配置文件失败 {config_path}: {e}", file=sys.stderr)
        sys.exit(1)


def validate_args(args: list) -> tuple:
    """验证命令行参数"""
    if len(args) < 3:
        print("用法: python main.py <old_rev> <new_rev> <ref_name>", file=sys.stderr)
        print("示例: python main.py abc123 def456 refs/heads/main", file=sys.stderr)
        sys.exit(1)
    
    old_rev = args[0]
    new_rev = args[1]
    ref_name = args[2]
    
    if len(old_rev) != 40 or len(new_rev) != 40:
        print(f"警告: commit hash长度不正确 (old={len(old_rev)}, new={len(new_rev)})", file=sys.stderr)
    
    return old_rev, new_rev, ref_name


def main():
    """主函数"""
    script_dir = Path(__file__).parent.parent
    os.chdir(script_dir)
    
    if len(sys.argv) < 4:
        old_rev, new_rev, ref_name = validate_args(sys.argv[1:])
    else:
        old_rev = sys.argv[1]
        new_rev = sys.argv[2]
        ref_name = sys.argv[3]
    
    config = load_config()
    logger = setup_logging(config)
    
    logger.info(f"接收到审查请求:")
    logger.info(f"  Old Rev: {old_rev}")
    logger.info(f"  New Rev: {new_rev}")
    logger.info(f"  Ref: {ref_name}")
    
    try:
        engine = ReviewEngine(config)
        
        success = engine.review_commit(old_rev, new_rev, ref_name)
        
        if success:
            logger.info("[SUCCESS] Code review completed")
            sys.exit(0)
        else:
            logger.error("[FAILED] Code review failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.warning("Review interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Review process exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

