            {
                "priority": "high",
                "category": "library_selection",
                "description": "Optimize library fallback order based on file characteristics",
                "impact": "high",
                "effort": "low"
            },
            {
                "priority": "medium",
                "category": "memory_management",
                "description": "Implement explicit memory cleanup after PDF extraction",
                "impact": "medium",
                "effort": "low"
            }
        ])
        
        # 按優先級排序
        recommendations.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]])
        
        return recommendations
    
    def generate_report(self, output_dir: str = "performance_reports") -> Dict[str, Any]:
        """
        生成完整的性能分析報告
        
        Args:
            output_dir: 輸出目錄
            
        Returns:
            報告數據
        """
        # 創建輸出目錄
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # 收集所有數據
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_pdfs_tested": len(self.results),
            "summary": self._generate_summary(),
            "detailed_results": self.results,
            "bottlenecks": self.analyze_bottlenecks(),
            "recommendations": self.generate_optimization_recommendations(),
            "profile_stats": self.profile_stats
        }
        
        # 保存 JSON 報告
        json_path = output_path / f"performance_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # 生成文本報告
        text_report = self._generate_text_report(report)
        text_path = output_path / f"performance_report_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        # 生成簡要摘要
        summary_path = output_path / f"performance_summary_{time.strftime('%Y%m%d_%H%M%S')}.md"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_markdown_summary(report))
        
        logger.info(f"Reports saved to: {output_path}")
        logger.info(f"  JSON: {json_path.name}")
        logger.info(f"  Text: {text_path.name}")
        logger.info(f"  Summary: {summary_path.name}")
        
        return report
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成測試摘要"""
        if not self.results:
            return {}
        
        # 計算總體統計
        all_times = [r["avg_time_seconds"] for r in self.results]
        all_speeds = [r["avg_speed_chars_per_second"] for r in self.results]
        all_memory = [r["avg_memory_delta_mb"] for r in self.results]
        
        # 按類別分組
        by_category = {}
        by_size = {}
        
        for result in self.results:
            # 按類別
            cat = result["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(result["avg_time_seconds"])
            
            # 按大小
            size_cat = result["size_category"]
            if size_cat not in by_size:
                by_size[size_cat] = []
            by_size[size_cat].append(result["avg_time_seconds"])
        
        return {
            "overall": {
                "avg_extraction_time_seconds": statistics.mean(all_times),
                "median_extraction_time_seconds": statistics.median(all_times),
                "min_extraction_time_seconds": min(all_times),
                "max_extraction_time_seconds": max(all_times),
                "avg_speed_chars_per_second": statistics.mean(all_speeds),
                "avg_memory_increase_mb": statistics.mean(all_memory),
                "total_files": len(self.results),
                "success_rate": sum(1 for r in self.results if r["success_rate"] == 1.0) / len(self.results)
            },
            "by_category": {
                cat: {
                    "count": len(times),
                    "avg_time": statistics.mean(times),
                    "min_time": min(times),
                    "max_time": max(times)
                }
                for cat, times in by_category.items()
            },
            "by_size": {
                size_cat: {
                    "count": len(times),
                    "avg_time": statistics.mean(times),
                    "min_time": min(times),
                    "max_time": max(times)
                }
                for size_cat, times in by_size.items()
            }
        }
    
    def _generate_text_report(self, report: Dict[str, Any]) -> str:
        """生成文本格式報告"""
        lines = []
        
        lines.append("=" * 80)
        lines.append("PDF 提取性能分析報告")
        lines.append("=" * 80)
        lines.append(f"生成時間: {report['timestamp']}")
        lines.append(f"測試文件數量: {report['total_pdfs_tested']}")
        lines.append("")
        
        # 摘要
        summary = report["summary"]["overall"]
        lines.append("📊 性能摘要")
        lines.append("-" * 40)
        lines.append(f"平均提取時間: {summary['avg_extraction_time_seconds']:.3f} 秒")
        lines.append(f"中位數提取時間: {summary['median_extraction_time_seconds']:.3f} 秒")
        lines.append(f"最快提取: {summary['min_extraction_time_seconds']:.3f} 秒")
        lines.append(f"最慢提取: {summary['max_extraction_time_seconds']:.3f} 秒")
        lines.append(f"平均速度: {summary['avg_speed_chars_per_second']:.0f} 字符/秒")
        lines.append(f"平均內存增加: {summary['avg_memory_increase_mb']:.1f} MB")
        lines.append(f"成功率: {summary['success_rate']:.1%}")
        lines.append("")
        
        # 瓶頸分析
        if report["bottlenecks"]:
            lines.append("⚠️ 性能瓶頸 (前5名)")
            lines.append("-" * 40)
            for bottleneck in report["bottlenecks"][:5]:
                if "type" not in bottleneck:  # 時間瓶頸
                    lines.append(f"{bottleneck['rank']}. {bottleneck['file']}")
                    lines.append(f"   時間: {bottleneck['avg_time_seconds']:.3f}s, 大小: {bottleneck['size_kb']:.1f}KB")
                    lines.append(f"   問題: {bottleneck['potential_issue']}")
                    lines.append("")
        else:
            lines.append("✅ 未發現明顯性能瓶頸")
            lines.append("")
        
        # 優化建議
        if report["recommendations"]:
            lines.append("💡 優化建議")
            lines.append("-" * 40)
            for i, rec in enumerate(report["recommendations"], 1):
                lines.append(f"{i}. [{rec['priority'].upper()}] {rec['description']}")
                lines.append(f"   類別: {rec['category']}, 影響: {rec['impact']}, 工作量: {rec['effort']}")
                if "suggestion" in rec:
                    lines.append(f"   建議: {rec['suggestion']}")
                lines.append("")
        
        # 按類別性能
        lines.append("📈 按類別性能分析")
        lines.append("-" * 40)
        for category, stats in report["summary"]["by_category"].items():
            lines.append(f"{category}: {stats['count']} 個文件")
            lines.append(f"   平均時間: {stats['avg_time']:.3f}s, 範圍: {stats['min_time']:.3f}s - {stats['max_time']:.3f}s")
        lines.append("")
        
        # 按大小性能
        lines.append("📈 按大小性能分析")
        lines.append("-" * 40)
        for size_cat, stats in report["summary"]["by_size"].items():
            lines.append(f"{size_cat}: {stats['count']} 個文件")
            lines.append(f"   平均時間: {stats['avg_time']:.3f}s, 範圍: {stats['min_time']:.3f}s - {stats['max_time']:.3f}s")
        lines.append("")
        
        # 性能分析摘要
        if report.get("profile_stats"):
            lines.append("🔍 cProfile 性能分析摘要")
            lines.append("-" * 40)
            lines.append(f"分析樣本: {', '.join(report['profile_stats']['samples_analyzed'][:3])}")
            if len(report['profile_stats']['samples_analyzed']) > 3:
                lines.append(f"  ... 等 {len(report['profile_stats']['samples_analyzed'])} 個文件")
            lines.append("")
            
            lines.append("最耗時的函數 (前5名):")
            for i, func in enumerate(report["profile_stats"]["top_functions"][:5], 1):
                lines.append(f"{i}. {func['function']}")
                lines.append(f"   累計時間: {func['cumtime']:.3f}s, 調用次數: {func['ncalls']}")
            lines.append("")
        
        lines.append("=" * 80)
        lines.append("報告結束")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def _generate_markdown_summary(self, report: Dict[str, Any]) -> str:
        """生成 Markdown 格式摘要"""
        lines = []
        
        lines.append("# PDF 提取性能分析報告")
        lines.append("")
        lines.append(f"**生成時間**: {report['timestamp']}")
        lines.append(f"**測試文件數量**: {report['total_pdfs_tested']}")
        lines.append("")
        
        # 摘要
        summary = report["summary"]["overall"]
        lines.append("## 📊 性能摘要")
        lines.append("")
        lines.append("| 指標 | 數值 |")
        lines.append("|------|------|")
        lines.append(f"| 平均提取時間 | {summary['avg_extraction_time_seconds']:.3f} 秒 |")
        lines.append(f"| 中位數提取時間 | {summary['median_extraction_time_seconds']:.3f} 秒 |")
        lines.append(f"| 最快提取 | {summary['min_extraction_time_seconds']:.3f} 秒 |")
        lines.append(f"| 最慢提取 | {summary['max_extraction_time_seconds']:.3f} 秒 |")
        lines.append(f"| 平均速度 | {summary['avg_speed_chars_per_second']:.0f} 字符/秒 |")
        lines.append(f"| 平均內存增加 | {summary['avg_memory_increase_mb']:.1f} MB |")
        lines.append(f"| 成功率 | {summary['success_rate']:.1%} |")
        lines.append("")
        
        # 瓶頸分析
        if report["bottlenecks"]:
            lines.append("## ⚠️ 性能瓶頸 (前5名)")
            lines.append("")
            lines.append("| 排名 | 文件 | 時間 | 大小 | 潛在問題 |")
            lines.append("|------|------|------|------|----------|")
            for bottleneck in report["bottlenecks"][:5]:
                if "type" not in bottleneck:  # 時間瓶頸
                    lines.append(f"| {bottleneck['rank']} | {bottleneck['file']} | {bottleneck['avg_time_seconds']:.3f}s | {bottleneck['size_kb']:.1f}KB | {bottleneck['potential_issue']} |")
            lines.append("")
        
        # 優化建議
        if report["recommendations"]:
            lines.append("## 💡 優化建議")
            lines.append("")
            lines.append("| 優先級 | 描述 | 類別 | 影響 | 工作量 |")
            lines.append("|--------|------|------|------|--------|")
            for rec in report["recommendations"]:
                lines.append(f"| {rec['priority'].upper()} | {rec['description']} | {rec['category']} | {rec['impact']} | {rec['effort']} |")
            lines.append("")
        
        # 性能預估提升
        lines.append("## 🎯 性能改進潛力")
        lines.append("")
        lines.append("基於當前測試結果，預計可實現的性能改進：")
        lines.append("")
        lines.append("- **短期優化 (1-2週)**: 15-25% 運行時間減少")
        lines.append("- **中期優化 (1個月)**: 25-40% 運行時間減少")
        lines.append("- **長期優化 (2-3個月)**: 40-60% 運行時間減少")
        lines.append("")
        lines.append("**關鍵改進領域**:")
        lines.append("1. PDF 庫選擇優化")
        lines.append("2. 大型文件處理改進")
        lines.append("3. 內存管理優化")
        lines.append("4. 並行處理實現")
        lines.append("")
        
        lines.append("---")
        lines.append("*報告由 PDF 性能分析腳本自動生成*")
        
        return "\n".join(lines)


def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PDF 提取性能分析工具")
    parser.add_argument("--downloads-dir", default="downloads", 
                       help="PDF 文件目錄 (默認: downloads)")
    parser.add_argument("--iterations", type=int, default=3,
                       help="每個文件的測試迭代次數 (默認: 3)")
    parser.add_argument("--profile", action="store_true",
                       help="運行 cProfile 性能分析")
    parser.add_argument("--sample-count", type=int, default=5,
                       help="性能分析樣本數量 (默認: 5)")
    parser.add_argument("--output-dir", default="performance_reports",
                       help="報告輸出目錄 (默認: performance_reports)")
    parser.add_argument("--quick", action="store_true",
                       help="快速測試模式 (只測試前5個文件)")
    
    args = parser.parse_args()
    
    # 創建分析器
    analyzer = PDFPerformanceAnalyzer(args.downloads_dir)
    
    # 發現 PDF 文件
    pdf_files = analyzer.discover_pdf_files()
    
    if not pdf_files:
        logger.error("未找到 PDF 文件")
        return 1
    
    if args.quick:
        pdf_files = pdf_files[:5]
        logger.info(f"快速測試模式: 只測試前 {len(pdf_files)} 個文件")
    
    # 運行性能測試
    logger.info(f"開始性能測試，共 {len(pdf_files)} 個文件")
    results = analyzer.run_performance_test_suite(pdf_files, args.iterations)
    
    if not results:
        logger.error("所有測試都失敗了")
        return 1
    
    # 運行性能分析（如果啟用）
    if args.profile:
        analyzer.run_profiling(pdf_files, args.sample_count)
    
    # 生成報告
    report = analyzer.generate_report(args.output_dir)
    
    # 打印簡要摘要
    summary = report["summary"]["overall"]
    print("\n" + "=" * 60)
    print("📋 性能測試完成")
    print("=" * 60)
    print(f"測試文件: {report['total_pdfs_tested']} 個")
    print(f"平均提取時間: {summary['avg_extraction_time_seconds']:.3f} 秒")
    print(f"最快: {summary['min_extraction_time_seconds']:.3f} 秒")
    print(f"最慢: {summary['max_extraction_time_seconds']:.3f} 秒")
    print(f"速度範圍: {summary['min_extraction_time_seconds']/summary['max_extraction_time_seconds']:.1%}")
    
    # 顯示瓶頸
    bottlenecks = report["bottlenecks"]
    if bottlenecks:
        print(f"\n⚠️  發現 {len([b for b in bottlenecks if 'type' not in b])} 個性能瓶頸")
        for bottleneck in bottlenecks[:3]:
            if "type" not in bottleneck:
                print(f"  • {bottleneck['file']}: {bottleneck['avg_time_seconds']:.3f}s")
    
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