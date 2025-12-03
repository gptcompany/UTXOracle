#!/usr/bin/env python3
"""
Simple pattern analysis from tool usage logs
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

def analyze_tool_usage():
    """Analyze tool usage from .claude/logs/*.json"""
    
    stats_dir = Path(".claude/logs")
    if not stats_dir.exists():
        print("No logs directory found")
        return
    
    # Collect all tool calls from session logs
    all_tools = []
    sessions = {}
    
    for log_file in stats_dir.glob("*_tool_usage.json"):
        session_id = log_file.stem.replace("_tool_usage", "")
        
        try:
            with open(log_file) as f:
                data = json.load(f)
                all_tools.extend(data)
                sessions[session_id] = len(data)
        except:
            continue
    
    if not all_tools:
        print("No tool usage data found")
        return
    
    # Analysis
    tool_counts = Counter(d['tool_name'] for d in all_tools)
    success_counts = defaultdict(lambda: {'total': 0, 'success': 0})
    
    for entry in all_tools:
        tool = entry['tool_name']
        success_counts[tool]['total'] += 1
        if entry.get('success', True):
            success_counts[tool]['success'] += 1
    
    # Top 10 tools
    top_tools = tool_counts.most_common(10)
    
    # MCP usage
    mcp_tools = [t for t in all_tools if t['tool_name'].startswith('mcp__')]
    mcp_servers = defaultdict(int)
    for tool in mcp_tools:
        server = tool['tool_name'].split('__')[1]
        mcp_servers[server] += 1
    
    # Report
    report = {
        "timestamp": datetime.now().isoformat(),
        "sessions_analyzed": len(sessions),
        "total_tool_calls": len(all_tools),
        "top_10_tools": [
            {
                "tool": tool,
                "count": count,
                "percentage": f"{count/len(all_tools)*100:.1f}%",
                "success_rate": f"{success_counts[tool]['success']/success_counts[tool]['total']*100:.0f}%"
            }
            for tool, count in top_tools
        ],
        "mcp_servers": {
            server: {
                "calls": count,
                "percentage": f"{count/len(all_tools)*100:.1f}%"
            }
            for server, count in mcp_servers.items()
        }
    }
    
    # Save report
    Path(".claude/reports").mkdir(exist_ok=True)
    report_file = Path(".claude/reports/analysis_latest.json")
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"✅ Analysis complete: {report_file}")
    print(f"\n📊 Summary:")
    print(f"  Sessions: {len(sessions)}")
    print(f"  Total tool calls: {len(all_tools)}")
    print(f"\n🔝 Top 5 Tools:")
    for item in report['top_10_tools'][:5]:
        print(f"  {item['tool']:30} {item['count']:4} calls ({item['percentage']:>6}) - {item['success_rate']} success")
    
    if mcp_servers:
        print(f"\n🔌 MCP Server Usage:")
        for server, data in report['mcp_servers'].items():
            print(f"  {server:20} {data['calls']:4} calls ({data['percentage']:>6})")
    
    return report

if __name__ == '__main__':
    analyze_tool_usage()
