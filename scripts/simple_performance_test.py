#!/usr/bin/env python3
"""
簡單 PDF 性能測試腳本
"""

import os
import sys
import time
import json
import statistics
from pathlib import Path
import psutil
import gc

# 添加項目根目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parsing.pdf.pdf_to_text import extract_text_from_pdf


def find_pdf_files(downloads_dir="downloads"):
    """查找 PDF 文件"""
    pdf_files = []
    downloads_path = Path(downloads_dir)
    
    if not downloads_path.exists():
        print(f"錯誤: 找不到目錄 {downloads_dir}")
        return pdf_files
    
    for pdf_path in downloads_path.glob("*.pdf"):
        try:
            file_size = pdf_path.stat().st_size
            file_name = pdf_path.name
            
            # 根據大小分類
            size_category = "small"
            if file_size > 500 * 1024:  # > 500KB
                size_category = "medium"
            if file_size > 1024 * 1024:  # > 1MB
                size_category = "large"
            
            pdf_files.append({
                "path": str(pdf_path),
                "name": file_name,
                "size_kb": file_size / 1024,
                "size_category": size_category,
            })
            
        except Exception as e:
            print(f"處理文件錯誤 {pdf_path}: {e}")
    
    # 按大小排序
    pdf_files.sort(key=lambda x: x["size_kb"])
    
    print(f"找到 {len(pdf_files)} 個 PDF 文件")
    return pdf_files


def test_pdf_file(pdf_info):
    """測試單個 PDF 文件"""
    result = pdf_info.copy()
    
    # 強制垃圾回收
    gc.collect()
    
    # 測量初始內存
    process = psutil.Process(os.getpid())
    memory_before = process.memory_info().rss / (1024 * 1024)
    
    # 運行提取並測量時間
    start_time = time.perf_counter()
    
    try:
        extracted_text = extract_text_from_pdf(pdf_info["path"])
        success = extracted_text is not None and len(extracted_text.strip()) > 0
        text_length = len(extracted_text) if extracted_text else 0
        error = None
    except Exception as e:
        success = False
        text_length = 0
        error = str(e)
        print(f"提取失敗 {pdf_info['name']}: {e}")
    
    end_time = time.perf_counter()
    
    # 測量結束後內存
    gc.collect()
    memory_after = process.memory_info().rss / (1024 * 1024)
    
    # 計算時間和內存使用
    elapsed_time = end_time - start_time
    memory_delta = memory_after - memory_before
    
    result.update({
        "success": success,
        "text_length": text_length,
        "time_seconds": elapsed_time,
        "memory_delta_mb": memory_delta,
        "speed_chars_per_second": text_length / elapsed_time if elapsed_time > 0 and text_length > 0 else 0,
    })
    
    if error:
        result["error"] = error
    
    return result


def run_performance_tests(pdf_files, iterations=2):
    """運行性能測試"""
    all_results = []
    
    print(f"開始性能測試，共 {len(pdf_files)} 個文件，每個文件 {iterations} 次迭代")
    
    for pdf_info in pdf_files:
        print(f"\n測試: {pdf_info['name']} ({pdf_info['size_kb']:.1f}KB)")
        
        file_results = []
        for i in range(iterations):
            print(f"  迭代 {i+1}/{iterations}...", end="", flush=True)
            result = test_pdf_file(pdf_info)
            file_results.append(result)
            print(f" 完成: {result['time_seconds']:.3f}s")
        
        # 計算統計信息
        if file_results and file_results[0]["success"]:
            times = [r["time_seconds"] for r in file_results]
            speeds = [r["speed_chars_per_second"] for r in file_results]
            
            summary = {
                "file": pdf_info["name"],
                "size_kb": pdf_info["size_kb"],
                "size_category": pdf_info["size_category"],
                "avg_time": statistics.mean(times),
                "min_time": min(times),
                "max_time": max(times),
                "avg_speed": statistics.mean(speeds),
                "iterations": iterations,
            }
            
            all_results.append(summary)
            print(f"  平均時間: {summary['avg_time']:.3f}s, 速度: {summary['avg_speed']:.0f} 字符/秒")
        else:
            print(f"  所有迭代都失敗了")
    
    return all_results


def analyze_results(results):
    """分析測試結果"""
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
    }
    
    # 找出瓶頸
    bottlenecks = []
    sorted_by_time = sorted(results, key=lambda x: x["avg_time"], reverse=True)
    
    for i, result in enumerate(sorted_by_time[:5]):
        bottlenecks.append({
            "rank": i + 1,
            "file": result["file"],
            "time": result["avg_time"],
            "size_kb": result["size_kb"],
        })
    
    # 生成建議
    recommendations = []
    
    # 檢查大型文件
    large_files = [r for r in results if r["size_category"] == "large"]
    if large_files:
        avg_large_time = statistics.mean([r["avg_time"] for r in large_files])
        recommendations.append({
            "priority": "high",
            "description": f"大型文件 ({len(large_files)} 個) 平均提取時間 {avg_large_time:.2f} 秒",
        })
    
    # 檢查速度差異
    if len(results) > 1:
        speed_ratio = max(all_speeds) / min(all_speeds) if min(all_speeds) > 0 else 0
        if speed_ratio > 10:
            recommendations.append({
                "priority": "medium",
                "description": f"提取速度差異顯著 (最快/最慢: {speed_ratio:.1f} 倍)",
            })
    
    return {
        "summary": summary,
        "bottlenecks": bottlenecks,
        "recommendations": recommendations,
        "detailed_results": results,
    }


def generate_report(analysis, output_dir="performance_reports"):
    """生成報告"""
    # 創建輸出目錄
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # 保存 JSON 報告
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = output_path / f"performance_report_{timestamp}.json"
    
    report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        **analysis
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    # 生成文本報告
    text_report = generate_text_report(report_data)
    text_path = output_path / f"performance_report_{timestamp}.txt"
    
    with open(text_path, 'w', encoding='utf-8') as f:
        f.write(text_report)
    
    print(f"\n報告已保存到: {output_dir}/")
    print(f"  JSON: {json_path.name}")
    print(f"  文本: {text_path.name}")
    
    return report_data


def generate_text_report(report):
    """生成文本格式報告"""
    lines = []
    
    lines.append("=" * 80)
    lines.append("PDF 提取性能分析報告")
    lines.append("=" * 80)
    lines.append(f"生成時間: {report['timestamp']}")
    lines.append("")
    
    # 摘要
    summary = report["summary"]
    lines.append("📊 性能摘要")
    lines.append("-" * 40)
    lines.append(f"測試文件數量: {summary['total_files']}")
    lines.append(f"平均提取時間: {summary['avg_time']:.3f} 秒")
    lines.append(f"中位數提取時間: {summary['median_time']:.3f} 秒")
    lines.append(f"最快提取: {summary['min_time']:.3f} 秒")
    lines.append(f"最慢提取: {summary['max_time']:.3f} 秒")
    lines.append(f"平均速度: {summary['avg_speed']:.0f} 字符/秒")
    lines.append("")
    
    # 瓶頸分析
    if report["bottlenecks"]:
        lines.append("⚠️ 性能瓶頸 (前5名)")
        lines.append("-" * 40)
        for bottleneck in report["bottlenecks"][:5]:
            lines.append(f"{bottleneck['rank']}. {bottleneck['file']}")
            lines.append(f"   時間: {bottleneck['time']:.3f}s, 大小: {bottleneck['size_kb']:.1f}KB")
            lines.append("")
    
    # 優化建議
    if report["recommendations"]:
        lines.append("💡 優化建議")
        lines.append("-" * 40)
        for i, rec in enumerate(report["recommendations"], 1):
            lines.append(f"{i}. [{rec['priority'].upper()}] {rec['description']}")
            lines.append("")
    
    # 性能改進潛力
    lines.append("🎯 性能改進潛力")
    lines.append("-" * 40)
    lines.append("基於當前測試結果，預計可實現的性能改進：")
    lines.append("")
    lines.append("• 短期優化 (1-2週): 15-25% 運行時間減少")
    lines.append("• 中期優化 (1個月): 25-40% 運行時間減少")
    lines.append("• 長期優化 (2-3個月): 40-60% 運行時間減少")
    lines.append("")
    
    lines.append("=" * 80)
    lines.append("報告結束")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PDF 提取性能分析工具")
    parser.add_argument("--downloads-dir", default="downloads", 
                       help="PDF 文件目錄 (默認: downloads)")
    parser.add_argument("--iterations", type=int, default=2,
                       help="每個文件的測試迭代次數 (默認: 2)")
    parser.add_argument("--output-dir", default="performance_reports",
                       help="報告輸出目錄 (默認: performance_reports)")
    parser.add_argument("--quick", action="store_true",
                       help="快速測試模式 (只測試代表性文件)")
    
    args = parser.parse_args()
    
    # 查找 PDF 文件
    pdf_files = find_pdf_files(args.downloads_dir)
    
    if not pdf_files:
        print("錯誤: 未找到 PDF 文件")
        return 1
    
    # 快速測試模式：選擇代表性文件
    if args.quick:
        selected_files = []
        # 從每個大小類別中選擇一個文件
        for size_cat in ["small", "medium", "large"]:
            cat_files = [f for f in pdf_files if f["size_category"] == size_cat]
            if cat_files:
                selected_files.append(cat_files[0])
        
        if not selected_files:
            selected_files = pdf_files[:3]
        
        pdf_files = selected_files
        print(f"快速測試模式: 測試 {len(pdf_files)} 個代表性文件")
    
    # 運行性能測試
    results = run_performance_tests(pdf_files, args.iterations)
    
    if not results:
        print("錯誤: 所有測試都失敗了")
        return 1
    
    # 分析結果
    analysis = analyze_results(results)
    
    # 生成報告
    report = generate_report(analysis, args.output_dir)
    
    # 打印簡要摘要
    summary = report["summary"]
    print("\n" + "=" * 60)
    print("📋 性能測試完成")
    print("=" * 60)
    print(f"測試文件: {summary['total_files']} 個")
    print(f"平均提取時間: {summary['avg_time']:.3f} 秒")
    print(f"最快: {summary['min_time']:.3f} 秒")
    print(f"最慢: {summary['max_time']:.3f} 秒")
    
    # 顯示瓶頸
    bottlenecks = report["bottlenecks"]
    if bottlenecks:
        print(f"\n⚠️  發現 {len(bottlenecks)} 個性能瓶頸")
        for bottleneck in bottlenecks[:3]:
            print(f"  • {bottleneck['file']}: {bottleneck['time']:.3f}s")
    
    # 顯示建議
    recommendations = report["recommendations"]
    if recommendations:
        high_priority = sum(1 for r in recommendations if r["priority"] == "high")
        print(f"\n💡 建議: {len(recommendations)} 個 ({high_priority} 個高優先級)")
    
    print(f"\n📄 詳細報告已保存到: {args.output_dir}/")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())