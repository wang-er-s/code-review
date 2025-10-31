import requests
import json
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class FeishuClient:
    """飞书消息发送客户端"""
    
    def __init__(self, config: Dict):
        self.webhook_url = config.get('webhook_url', '')
        self.enable = config.get('enable', True)
        self.mention_all = config.get('mention_all', False)
        self.show_code_snippet = config.get('show_code_snippet', True)
        self.max_snippet_lines = config.get('max_snippet_lines', 10)
        
        logger.info(f"飞书客户端初始化: enable={self.enable}")
    
    def send_review_report(self, commit_info: Dict, review_results: List[Dict]) -> bool:
        """
        发送代码审查报告到飞书
        
        Args:
            commit_info: 提交信息
            review_results: 审查结果列表
            
        Returns:
            bool: 是否发送成功
        """
        if not self.enable:
            logger.info("飞书通知已禁用，跳过发送")
            return True
        
        if not self.webhook_url or 'placeholder' in self.webhook_url:
            logger.warning("飞书webhook未配置或为占位符，跳过发送")
            return False
        
        try:
            card = self._build_message_card(commit_info, review_results)
            
            response = requests.post(
                self.webhook_url,
                json=card,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('StatusCode') == 0:
                    logger.info("飞书消息发送成功")
                    return True
                else:
                    logger.error(f"飞书消息发送失败: {result}")
                    return False
            else:
                logger.error(f"飞书API调用失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"发送飞书消息异常: {e}")
            return False
    
    def _build_message_card(self, commit_info: Dict, review_results: List[Dict]) -> Dict:
        """构建飞书消息卡片"""
        
        total_issues = sum(len(r.get('result', {}).get('issues', [])) for r in review_results)
        error_count = sum(len([i for i in r.get('result', {}).get('issues', []) 
                              if i.get('severity') == 'error']) for r in review_results)
        warning_count = sum(len([i for i in r.get('result', {}).get('issues', []) 
                                if i.get('severity') == 'warning']) for r in review_results)
        
        severity_color = 'red' if error_count > 0 else ('orange' if warning_count > 0 else 'green')
        
        elements = []
        
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📋 代码审查报告**"
            }
        })
        
        elements.append({
            "tag": "hr"
        })
        
        # 提取commit消息（避免f-string中使用反斜杠）
        commit_msg = commit_info.get('message', '').split('\n')[0][:100]
        
        commit_md = f"""**提交信息**
📝 Commit: `{commit_info.get('hash', '')[:8]}`
👤 作者: {commit_info.get('author', '未知')}
📅 时间: {commit_info.get('date', '未知')}
💬 消息: {commit_msg}"""
        
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": commit_md
            }
        })
        
        elements.append({
            "tag": "hr"
        })
        
        summary_md = f"""**审查统计**
📁 审查文件: {len(review_results)} 个
🔍 发现问题: {total_issues} 个
❌ 错误: {error_count} 个
⚠️ 警告: {warning_count} 个
ℹ️ 建议: {total_issues - error_count - warning_count} 个"""
        
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": summary_md
            }
        })
        
        if total_issues > 0:
            elements.append({
                "tag": "hr"
            })
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**📌 问题详情**"
                }
            })
            
            for review in review_results:
                file_path = review.get('file', '')
                issues = review.get('result', {}).get('issues', [])
                
                if not issues:
                    continue
                
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"\n**文件**: `{file_path}`"
                    }
                })
                
                for issue in issues[:10]:
                    severity_icon = {
                        'error': '❌',
                        'warning': '⚠️',
                        'info': 'ℹ️'
                    }.get(issue.get('severity', 'info'), 'ℹ️')
                    
                    line = issue.get('line', 0)
                    # 提取并清理消息（避免f-string中使用反斜杠）
                    raw_message = issue.get('message', '')
                    message = raw_message.replace('\n', ' ')[:200]
                    category = issue.get('category', '其他')
                    
                    issue_md = f"{severity_icon} **[{category}]** Line {line}: {message}"
                    
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": issue_md
                        }
                    })
                
                if len(issues) > 10:
                    elements.append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"_... 还有 {len(issues) - 10} 个问题未显示_"
                        }
                    })
        else:
            elements.append({
                "tag": "hr"
            })
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "✅ **太棒了！未发现明显问题**"
                }
            })
        
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "🤖 Git代码审查报告"
                    },
                    "template": severity_color
                },
                "elements": elements
            }
        }
        
        if self.mention_all:
            card["card"]["elements"].append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "<at id=all></at>"
                }
            })
        
        return card
    
    def send_error_notification(self, error_msg: str, commit_info: Dict = None) -> bool:
        """发送错误通知"""
        if not self.enable or not self.webhook_url:
            return False
        
        try:
            content = f"**❌ 代码审查失败**\n\n"
            if commit_info:
                content += f"Commit: `{commit_info.get('hash', '')[:8]}`\n"
            content += f"错误信息: {error_msg}"
            
            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": "代码审查系统错误"
                        },
                        "template": "red"
                    },
                    "elements": [{
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content
                        }
                    }]
                }
            }
            
            response = requests.post(self.webhook_url, json=card, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"发送错误通知失败: {e}")
            return False

