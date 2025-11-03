#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审查机器端HTTP服务

接收来自客户端的通知，触发代码审查
"""

import sys
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import yaml
from flask import Flask, request, jsonify

# 将src目录添加到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from review_engine import ReviewEngine
from config1 import Config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局变量：审查引擎
review_engine: Optional[ReviewEngine] = None
server_config: Dict = {}


def load_config(config_path: str = 'config/config.yaml') -> Config:
    """加载配置文件"""
    try:
        config = Config.from_yaml(config_path)
        
        # 加载服务端配置
        global server_config
        with open(config_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)
            server_config = yaml_data.get('review_server', {})
        
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败 {config_path}: {e}")
        raise


def init_review_engine(config: Config):
    """初始化审查引擎"""
    global review_engine
    try:
        review_engine = ReviewEngine(config)
        logger.info("审查引擎初始化成功")
    except Exception as e:
        logger.error(f"初始化审查引擎失败: {e}")
        raise


@app.route('/review', methods=['POST'])
def handle_review_request():
    """
    处理审查请求
    
    请求格式:
    {
        "repository_url": "git@server:/path/to/repo.git",
        "branch": "MergeBattle",
        "old_rev": "abc123...",
        "new_rev": "def456...",
        "ref_name": "refs/heads/MergeBattle",
        "commits": [...],
        "push_time": "2024-01-01T12:00:00Z"
    }
    """
    try:
        # 解析请求数据
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求数据格式错误：缺少JSON数据'
            }), 400
        
        # 验证必要字段
        required_fields = ['branch', 'old_rev', 'new_rev', 'ref_name']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'message': f'请求数据格式错误：缺少必要字段 {field}'
                }), 400
        
        branch = data['branch']
        old_rev = data['old_rev']
        new_rev = data['new_rev']
        ref_name = data['ref_name']
        commits = data.get('commits', [])
        
        logger.info(f"收到审查请求: 分支={branch}, old_rev={old_rev[:8]}, new_rev={new_rev[:8]}, commits={len(commits)}")
        
        # 检查分支过滤
        review_branches = server_config.get('review_branches', [])
        if review_branches and branch not in review_branches:
            logger.info(f"分支 {branch} 不在审查列表中，跳过")
            return jsonify({
                'status': 'skipped',
                'message': f'分支 {branch} 不在审查列表中'
            }), 200
        
        # 检查审查引擎是否已初始化
        if not review_engine:
            return jsonify({
                'status': 'error',
                'message': '审查引擎未初始化'
            }), 500
        
        # 更新工作仓库
        logger.info(f"更新工作仓库分支: {branch}")
        if not review_engine.git_handler.update_working_repo(branch):
            logger.error("工作仓库更新失败")
            return jsonify({
                'status': 'error',
                'message': '工作仓库更新失败'
            }), 500
        
        # 执行审查
        logger.info(f"开始审查: {old_rev[:8]}..{new_rev[:8]}")
        success = review_engine.review_commit(old_rev, new_rev, ref_name)
        
        if success:
            logger.info("审查完成: 成功")
            return jsonify({
                'status': 'success',
                'message': '审查完成',
                'old_rev': old_rev[:8],
                'new_rev': new_rev[:8],
                'branch': branch
            }), 200
        else:
            logger.warning("审查完成: 失败")
            return jsonify({
                'status': 'failed',
                'message': '审查失败（请查看日志）',
                'old_rev': old_rev[:8],
                'new_rev': new_rev[:8],
                'branch': branch
            }), 200
            
    except Exception as e:
        logger.error(f"处理审查请求异常: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'服务器内部错误: {str(e)}'
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        'status': 'ok',
        'service': 'review_server',
        'timestamp': datetime.now().isoformat()
    }), 200


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='审查机器端HTTP服务')
    parser.add_argument(
        '--config',
        default='config/config.yaml',
        help='配置文件路径（默认: config/config.yaml）'
    )
    parser.add_argument(
        '--host',
        help='监听地址（覆盖配置文件）'
    )
    parser.add_argument(
        '--port',
        type=int,
        help='监听端口（覆盖配置文件）'
    )
    
    args = parser.parse_args()
    
    # 切换到脚本所在目录的父目录（项目根目录）
    script_dir = Path(__file__).parent.parent
    os.chdir(script_dir)
    
    # 加载配置
    logger.info(f"加载配置文件: {args.config}")
    config = load_config(args.config)
    
    # 初始化审查引擎
    logger.info("初始化审查引擎...")
    init_review_engine(config)
    
    # 获取监听地址和端口
    host = args.host or server_config.get('host', '0.0.0.0')
    port = args.port or server_config.get('port', 5000)
    
    logger.info("=" * 60)
    logger.info(f"审查服务器启动")
    logger.info(f"监听地址: http://{host}:{port}")
    logger.info(f"审查端点: http://{host}:{port}/review")
    logger.info(f"健康检查: http://{host}:{port}/health")
    logger.info("=" * 60)
    
    # 启动Flask服务
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    main()

