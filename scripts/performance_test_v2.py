    # 發現 PDF 文件
    pdf_files = discover_pdf_files(args.downloads_dir)
    
    if not pdf_files:
        logger.error("未找到 PDF 文件")
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
        logger.info(f"快速測試模式: 測試 {len(pdf_files)} 個代表性文件")
    
    # 運行性能測試
    logger.info(f"開始性能測試，共 {len(pdf_files)} 個文件")
    results = run_performance_tests(pdf_files, args.iterations)
    
    if not results:
        logger.error("所有測試都失敗了")
        return 1
    
    # 運行性能分析（如果啟用）
    profile_data = None
    if args.profile:
        profile_data = run_profiling(pdf_files)
    
    # 生成報告
    report = generate_report(results, profile_data, args.output_dir)
    
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