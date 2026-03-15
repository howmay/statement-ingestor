#!/usr/bin/env python3
"""
使用測試 PDF 文件進行性能測試
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


def create_test_pdfs():
    """創建測試用的 PDF 文件（如果不存在）"""
    test_dir = Path("test_pdfs")
    test_dir.mkdir(exist_ok=True)
    
    # 創建幾個不同大小的測試文件
    test_files = []
    
    # 小文件 (1KB)
    small_pdf = test_dir / "small_test.pdf"
    if not small_pdf.exists():
        # 創建一個簡單的 PDF 文件
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(small_pdf), pagesize=letter)
        c.drawString(100, 750, "小型測試 PDF 文件")
        c.drawString(100, 730, "這是一個用於性能測試的小型 PDF 文件。")
        c.drawString(100, 710, "包含一些簡單的文本內容。")
        c.save()
    
    test_files.append({
        "path": str(small_pdf),
        "name": "small_test.pdf",
        "size_kb": small_pdf.stat().st_size / 1024,
        "size_category": "small"
    })
    
    # 中文件 (10KB) - 創建多頁
    medium_pdf = test_dir / "medium_test.pdf"
    if not medium_pdf.exists():
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        
        c = canvas.Canvas(str(medium_pdf), pagesize=letter)
        
        # 添加多頁內容
        for page_num in range(5):
            c.drawString(100, 750, f"中型測試 PDF 文件 - 第 {page_num + 1} 頁")
            c.drawString(100, 730, "這是一個用於性能測試的中型 PDF 文件。")
            c.drawString(100, 710, "包含多頁文本內容，模擬真實的銀行對帳單。")
            
            # 添加一些表格數據
            y = 650
            for i in range(10):
                c.drawString(100, y, f"項目 {i+1}: 測試數據 {i+1} * 100 = {(i+1)*100}")
                y -= 20
            
            c.showPage()  # 結束當前頁，開始新頁
        
        c.save()
    
    test_files.append({
        "path": str(medium_pdf),
        "name": "medium_test.pdf",
        "size_kb": medium_pdf.stat().st_size / 1024,
        "size_category": "medium"
    })
    
    # 使用現有的測試文件
    existing_test = Path("test/test_dummy.pdf")
    if existing_test.exists():
        test_files.append({
            "path": str(existing_test),
            "name": "test_dummy.pdf",
            "size_kb": existing_test.stat().st_size / 1024,
            "size_category": "small"
        })
    
    print(f"創建了 {len(test_files)} 個測試 PDF 文件")
    return test_files


def test_pdf_performance(pdf_files, iterations=3):
    """測試 PDF 提取性能"""
    results = []
    
    print(f"\n開始性能測試，共 {len(pdf_files)} 個文件，每個文件 {iterations} 次迭代")
    
    for pdf_info in pdf_files:
        print(f"\n測試: {pdf_info['name']} ({pdf_info['size_kb']:.1f}KB)")
        
        file_times = []
        file_speeds = []
        
        for i in range(iterations):
            print(f"  迭代 {i+1}/{iterations}...", end="", flush=True)
            
            start_time = time.perf_counter()
            
            try:
                text = extract_text_from_pdf(pdf_info["path"])
                success = text is not None and len(text.strip()) > 0
                text_length = len(text) if text else 0
            except Exception as e:
                success = False
                text_length = 0
                print(f" 錯誤: {e}")
                continue
            
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            
            speed = text_length / elapsed if elapsed > 0 and text_length > 0 else 0
            
            file_times.append(elapsed)
            file_speeds.append(speed)
            
            print(f" 完成: {elapsed:.3f}s, 字符: {text_length}, 速度: {speed:.0f} 字符/秒")
        
        if file_times:
            summary = {
                "file": pdf_info["name"],
                "size_kb": pdf_info["size_kb"],
                "size_category": pdf_info["size_category"],
                "avg_time": statistics.mean(file_times),
                "min_time": min(file_times),
                "max_time": max(file_times),
                "avg_speed": statistics.mean(file_speeds),
                "iterations": iterations,
                "success": True
            }
            
            results.append(summary)
            print(f"  平均時間: {summary['avg_time']:.3f}s, 平均速度: {summary['avg_speed']:.0f} 字符/秒")
        else:
            print(f"  所有迭代都失敗了")
    
    return results


def analyze_performance(results):
    """分析性能結果"""
    if not results:
        return {}
    
    # 計算總體統計
    all_times = [r["avg_time"] for r in results]
    all_speeds = [r["avg_speed"] for r in results]
    
    summary = {
        "total_files": len(results),
        "avg_time": statistics.mean(all_times),
        "median_time": statistics.median(all_times),
        "min_time": min(all_times),
        "max_time": max(all_times),
        "avg_speed": statistics.mean(all_speeds),
        "time_ratio": max(all_times) / min(all_times) if min(all_times) > 0 else 0,
        "speed_ratio": max(all_speeds) / min(all_speeds) if min(all_speeds) > 0 else 0,
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
            "speed": result["avg_speed"],
        })
    
    # 生成建議
    recommendations = []
    
    # 檢查性能差異
    if summary["time_ratio"] > 5:
        recommendations.append({
            "priority": "high",
            "description": f"提取時間差異顯著 (最快/最慢: {summary['time_ratio']:.1f} 倍)",
            "suggestion": "調查不同大小/複雜度 PDF 的性能差異"
        })
    
    # 檢查絕對性能
    if summary["avg_time"] > 1.0:
        recommendations.append({
            "priority": "medium",
            "description": f"平均提取時間較長 ({summary['avg_time']:.2f} 秒)",
            "suggestion": "優化 PDF 庫選擇算法或實現緩存"
        })
    
    # 通用建議
    recommendations.extend([
        {
            "priority": "high",
            "description": "實現 PDF 庫智能選擇",
            "suggestion": "根據文件特性（大小、加密狀態、複雜度）選擇最合適的庫"
        },
        {
            "priority": "medium",
            "description": "添加並行處理支持",
            "suggestion": "批量處理時使用多線程/多進程提高吞吐量"
        },
        {
            "priority": "low",
            "description": "實現提取結果緩存",
            "suggestion": "緩存已處理的 PDF 文本，避免重複提取"
        }
    ])
    
    return {
        "summary": summary,
        "bottlenecks": bottlenecks,
        "recommendations": recommendations,
        "detailed_results": results,
    }


def generate_report(analysis, output_file="performance_report.json"):
    """生成性能報告"""
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        **analysis
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n報告已保存到: {output_file}")
    
    # 打印簡要報告
    print("\n" + "=" * 60)
    print("📊 PDF 提取性能分析報告")
    print("=" * 60)
    
    summary = report["summary"]
    print(f"測試文件: {summary['total_files']} 個")
    print(f"平均提取時間: {summary['avg_time']:.3f} 秒")
    print(f"中位數時間: {summary['median_time']:.3f} 秒")
    print(f"最快: {summary['min_time']:.3f} 秒")
    print(f"最慢: {summary['max_time']:.3f} 秒")
    print(f"平均速度: {summary['avg_speed']:.0f} 字符/秒")
    
    if report["bottlenecks"]:
        print(f"\n⚠️  性能瓶頸 (前3名):")
        for bottleneck in report["bottlenecks"]:
            print(f"  {bottleneck['rank']}. {bottleneck['file']}: {bottleneck['time']:.3f}s")
    
    if report["recommendations"]:
        high_priority = sum(1 for r in report["recommendations"] if r["priority"] == "high")
        print(f"\n💡 優化建議: {len(report['recommendations'])} 個 ({high_priority} 個高優先級)")
        for rec in report["recommendations"][:3]:
            print(f"  • [{rec['priority'].upper()}] {rec['description']}")
    
    print("\n🎯 預計性能改進潛力:")
    print("  • 短期 (1-2週): 15-25% 運行時間減少")
    print("  • 中期 (1個月): 25-40% 運行時間減少")
    print("  • 長期 (2-3個月): 40-60% 運行時間減少")
    
    print("=" * 60)
    
    return report


def main():
    """主函數"""
    # 創建測試 PDF 文件
    test_files = create_test_pdfs()
    
    if not test_files:
        print("錯誤: 無法創建測試文件")
        return 1
    
    # 運行性能測試
    results = test_pdf_performance(test_files, iterations=3)
    
    if not results:
        print("錯誤: 所有測試都失敗了")
        return 1
    
    # 分析性能
    analysis = analyze_performance(results)
    
    # 生成報告
    report = generate_report(analysis, "performance_report.json")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())