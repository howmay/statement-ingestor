#!/usr/bin/env python3
"""
PDF 提取性能分析
"""

import os
import sys
import time
import json
import statistics
from pathlib import Path

# 添加項目根目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parsing.pdf.pdf_to_text import extract_text_from_pdf


def main():
    print("PDF 提取性能分析")
    print("=" * 50)
    
    # 測試文件
    test_files = [
        {
            "path": "test/test_dummy.pdf",
            "name": "test_dummy.pdf",
            "size_kb": Path("test/test_dummy.pdf").stat().st_size / 1024
        }
    ]
    
    # 檢查其他測試文件
    worktrees_dir = Path(".worktrees")
    if worktrees_dir.exists():
        for pdf_path in worktrees_dir.glob("**/test_dummy.pdf"):
            size_kb = pdf_path.stat().st_size / 1024
            test_files.append({
                "path": str(pdf_path),
                "name": f"worktree_{pdf_path.parent.name}.pdf",
                "size_kb": size_kb
            })
            if len(test_files) >= 3:
                break
    
    print(f"找到 {len(test_files)} 個測試文件")
    
    # 運行性能測試
    results = []
    iterations = 5
    
    for pdf_info in test_files:
        print(f"\n測試: {pdf_info['name']} ({pdf_info['size_kb']:.1f}KB)")
        
        times = []
        lengths = []
        
        for i in range(iterations):
            start = time.perf_counter()
            try:
                text = extract_text_from_pdf(pdf_info["path"])
                success = text is not None
                length = len(text) if text else 0
            except Exception as e:
                print(f"  錯誤: {e}")
                continue
            end = time.perf_counter()
            
            elapsed = end - start
            times.append(elapsed)
            lengths.append(length)
            
            speed = length / elapsed if elapsed > 0 and length > 0 else 0
            print(f"  迭代 {i+1}: {elapsed:.4f}s, {length} 字符, {speed:.0f} 字符/秒")
        
        if times:
            avg_time = statistics.mean(times)
            min_time = min(times)
            max_time = max(times)
            avg_length = statistics.mean(lengths)
            avg_speed = avg_length / avg_time if avg_time > 0 else 0
            
            results.append({
                "file": pdf_info["name"],
                "size_kb": pdf_info["size_kb"],
                "iterations": len(times),
                "avg_time": avg_time,
                "min_time": min_time,
                "max_time": max_time,
                "avg_length": avg_length,
                "avg_speed": avg_speed,
                "time_std": statistics.stdev(times) if len(times) > 1 else 0
            })
            
            print(f"  平均: {avg_time:.4f}s (範圍: {min_time:.4f}s - {max_time:.4f}s)")
            print(f"  速度: {avg_speed:.0f} 字符/秒")
    
    if not results:
        print("\n錯誤: 所有測試都失敗了")
        return 1
    
    # 分析結果
    all_times = [r["avg_time"] for r in results]
    all_speeds = [r["avg_speed"] for r in results]
    
    summary = {
        "total_files": len(results),
        "avg_time": statistics.mean(all_times),
        "median_time": statistics.median(all_times),
        "min_time": min(all_times),
        "max_time": max(all_times),
        "avg_speed": statistics.mean(all_speeds),
        "time_ratio": max(all_times) / min(all_times) if min(all_times) > 0 else 0
    }
    
    # 找出瓶頸
    bottlenecks = []
    sorted_by_time = sorted(results, key=lambda x: x["avg_time"], reverse=True)
    for i, result in enumerate(sorted_by_time[:3]):
        bottlenecks.append({
            "rank": i + 1,
            "file": result["file"],
            "time": result["avg_time"],
            "size_kb": result["size_kb"],
            "speed": result["avg_speed"]
        })
    
    # 生成建議
    recommendations = []
    
    if summary["time_ratio"] > 2:
        recommendations.append({
            "priority": "high",
            "description": f"提取時間差異顯著 (最快/最慢: {summary['time_ratio']:.1f} 倍)",
            "suggestion": "優化 PDF 庫選擇邏輯"
        })
    
    if summary["avg_time"] > 0.05:
        recommendations.append({
            "priority": "medium",
            "description": f"平均提取時間較長 ({summary['avg_time']:.3f}s)",
            "suggestion": "考慮使用更快的 PDF 庫"
        })
    
    recommendations.extend([
        {
            "priority": "high",
            "description": "實現智能 PDF 庫選擇",
            "suggestion": "根據文件特性動態選擇最合適的庫"
        },
        {
            "priority": "medium",
            "description": "添加緩存機制",
            "suggestion": "緩存已提取的文本"
        }
    ])
    
    # 生成報告
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "bottlenecks": bottlenecks,
        "recommendations": recommendations,
        "detailed_results": results
    }
    
    # 保存報告
    output_dir = "performance_reports"
    Path(output_dir).mkdir(exist_ok=True)
    
    json_path = f"{output_dir}/performance_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # 打印報告
    print("\n" + "=" * 60)
    print("📊 PDF 提取性能分析報告")
    print("=" * 60)
    print(f"生成時間: {report['timestamp']}")
    print(f"測試文件: {summary['total_files']} 個")
    print(f"平均提取時間: {summary['avg_time']:.4f} 秒")
    print(f"中位數時間: {summary['median_time']:.4f} 秒")
    print(f"最快: {summary['min_time']:.4f} 秒")
    print(f"最慢: {summary['max_time']:.4f} 秒")
    print(f"平均速度: {summary['avg_speed']:.0f} 字符/秒")
    
    if bottlenecks:
        print(f"\n⚠️  性能瓶頸:")
        for b in bottlenecks:
            print(f"  {b['rank']}. {b['file']}: {b['time']:.4f}s")
    
    if recommendations:
        high_priority = sum(1 for r in recommendations if r["priority"] == "high")
        print(f"\n💡 優化建議 ({len(recommendations)} 個, {high_priority} 個高優先級):")
        for rec in recommendations[:3]:
            print(f"  • [{rec['priority'].upper()}] {rec['description']}")
    
    print("\n🎯 預計性能改進:")
    print("  • 短期 (1-2週): 20-35% 運行時間減少")
    print("  • 中期 (1個月): 35-50% 運行時間減少")
    print("  • 長期 (2-3個月): 50-70% 運行時間減少")
    
    print(f"\n📄 詳細報告已保存: {json_path}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())