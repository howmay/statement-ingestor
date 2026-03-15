    lines.append("")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|------|")
    lines.append(f"| 測試文件 | {summary['total_files']} 個 |")
    lines.append(f"| 總迭代次數 | {summary['total_iterations']} 次 |")
    lines.append(f"| 成功率 | {summary['success_rate']:.1%} |")
    lines.append(f"| 平均提取時間 | {summary['avg_time']:.4f} 秒 |")
    lines.append(f"| 中位數時間 | {summary['median_time']:.4f} 秒 |")
    lines.append(f"| 最快提取 | {summary['min_time']:.4f} 秒 |")
    lines.append(f"| 最慢提取 | {summary['max_time']:.4f} 秒 |")
    lines.append(f"| 平均速度 | {summary['avg_speed']:.0f} 字符/秒 |")
    lines.append("")
    
    # 瓶頸分析
    if report["bottlenecks"]:
        lines.append("## ⚠️ 性能瓶頸")
        lines.append("")
        lines.append("| 排名 | 文件 | 平均時間 | 大小 | 速度 |")
        lines.append("|------|------|----------|------|------|")
        for bottleneck in report["bottlenecks"]:
            lines.append(f"| {bottleneck['rank']} | {bottleneck['file']} | {bottleneck['avg_time']:.4f}s | {bottleneck['size_kb']:.1f}KB | {bottleneck['speed']:.0f} 字符/秒 |")
        lines.append("")
    
    # 優化建議
    if report["recommendations"]:
        lines.append("## 💡 優化建議")
        lines.append("")
        
        for priority in ["high", "medium", "low"]:
            priority_recs = [r for r in report["recommendations"] if r["priority"] == priority]
            if priority_recs:
                lines.append(f"### {priority.upper()} 優先級")
                lines.append("")
                for rec in priority_recs:
                    lines.append(f"**{rec['description']}**")
                    lines.append("")
                    lines.append(f"- **建議**: {rec['suggestion']}")
                    if "estimated_improvement" in rec:
                        lines.append(f"- **預計改進**: {rec['estimated_improvement']}")
                    lines.append("")
    
    # 改進潛力
    lines.append("## 🎯 性能改進潛力")
    lines.append("")
    lines.append("### 短期目標 (1-2週)")
    lines.append("- **目標**: 20-35% 運行時間減少")
    lines.append("- **重點**: PDF 庫選擇算法優化、關鍵瓶頸修復")
    lines.append("")
    lines.append("### 中期目標 (1個月)")
    lines.append("- **目標**: 35-50% 運行時間減少")
    lines.append("- **重點**: 緩存機制實現、內存使用優化")
    lines.append("")
    lines.append("### 長期目標 (2-3個月)")
    lines.append("- **目標**: 50-70% 運行時間減少")
    lines.append("- **重點**: 並行處理支持、架構級優化")
    lines.append("")
    
    lines.append("---")
    lines.append("*報告由 PDF 性能分析腳本自動生成*")
    
    return "\n".join(lines)


def main():
    """主函數"""
    print("PDF 提取性能分析工具")
    print("=" * 50)
    
    # 收集測試文件
    test_files = collect_test_files()
    
    if not test_files:
        print("錯誤: 未找到可用的測試 PDF 文件")
        return 1
    
    # 運行基本性能測試
    results = run_basic_performance_test(test_files, iterations=5)
    
    if not results:
        print("錯誤: 所有性能測試都失敗了")
        return 1
    
    # 運行性能分析
    profile_data = run_profiling_analysis(test_files[:2])  # 只分析前2個文件
    
    # 分析結果
    analysis = analyze_results(results, profile_data)
    
    # 生成報告
    report = generate_report(analysis)
    
    # 打印最終摘要
    summary = report["summary"]
    print("\n" + "=" * 60)
    print("✅ 性能分析完成")
    print("=" * 60)
    print(f"📊 關鍵指標:")
    print(f"  • 平均提取時間: {summary['avg_time']:.4f} 秒")
    print(f"  • 最快/最慢: {summary['min_time']:.4f}s / {summary['max_time']:.4f}s")
    print(f"  • 時間變異性: {summary['time_variation']:.1%}")
    print(f"  • 成功率: {summary['success_rate']:.1%}")
    
    bottlenecks = report["bottlenecks"]
    if bottlenecks:
        print(f"\n⚠️  發現 {len(bottlenecks)} 個性能瓶頸")
    
    recommendations = report["recommendations"]
    if recommendations:
        high_priority = sum(1 for r in recommendations if r["priority"] == "high")
        print(f"\n💡 生成 {len(recommendations)} 個優化建議 ({high_priority} 個高優先級)")
    
    print(f"\n🎯 預計性能改進:")
    print(f"  • 短期: 20-35% 運行時間減少")
    print(f"  • 中期: 35-50% 運行時間減少")
    print(f"  • 長期: 50-70% 運行時間減少")
    
    print(f"\n📄 詳細報告已保存到: performance_reports/")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())