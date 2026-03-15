#!/usr/bin/env python3
"""
Run performance tests and generate reports.
"""
import subprocess
import sys
import json
import os
from datetime import datetime
from pathlib import Path


def run_performance_tests():
    """Run performance tests and generate report."""
    
    # Create reports directory
    reports_dir = Path(__file__).parent.parent / 'performance_reports'
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f'performance_report_{timestamp}.json'
    
    print(f"Running performance tests...")
    print(f"Report will be saved to: {report_file}")
    
    # Run performance tests
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/performance/',
        '-v',
        '--tb=short',
        '--durations=10',
        '-q'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse test results
        test_results = {
            'timestamp': datetime.now().isoformat(),
            'command': ' '.join(cmd),
            'return_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'summary': {
                'passed': 0,
                'failed': 0,
                'skipped': 0,
                'total': 0
            },
            'tests': []
        }
        
        # Parse output to extract test results
        lines = result.stdout.split('\n')
        for line in lines:
            if 'PASSED' in line:
                test_results['summary']['passed'] += 1
                test_results['summary']['total'] += 1
                test_name = line.split('::')[-1].split(' ')[0]
                test_results['tests'].append({
                    'name': test_name,
                    'status': 'PASSED'
                })
            elif 'FAILED' in line:
                test_results['summary']['failed'] += 1
                test_results['summary']['total'] += 1
                test_name = line.split('::')[-1].split(' ')[0]
                test_results['tests'].append({
                    'name': test_name,
                    'status': 'FAILED'
                })
            elif 'SKIPPED' in line:
                test_results['summary']['skipped'] += 1
                test_results['summary']['total'] += 1
                test_results['tests'].append({
                    'name': line.split('::')[-1].split(' ')[0],
                    'status': 'SKIPPED'
                })
        
        # Save report
        with open(report_file, 'w') as f:
            json.dump(test_results, f, indent=2, default=str)
        
        # Print summary
        print(f"\n=== Performance Test Summary ===")
        print(f"Total tests: {test_results['summary']['total']}")
        print(f"Passed: {test_results['summary']['passed']}")
        print(f"Failed: {test_results['summary']['failed']}")
        print(f"Skipped: {test_results['summary']['skipped']}")
        
        if test_results['summary']['failed'] > 0:
            print(f"\nFailed tests:")
            for test in test_results['tests']:
                if test['status'] == 'FAILED':
                    print(f"  - {test['name']}")
        
        print(f"\nDetailed report saved to: {report_file}")
        
        return test_results['summary']['failed'] == 0
        
    except Exception as e:
        print(f"Error running performance tests: {e}")
        return False


def run_benchmarks():
    """Run benchmark tests."""
    
    print(f"\nRunning benchmark tests...")
    
    # Run benchmark tests
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/performance/test_benchmarks.py',
        '-v',
        '--tb=short',
        '-q'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Benchmark tests passed!")
            return True
        else:
            print(f"Benchmark tests failed:")
            print(result.stdout)
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"Error running benchmark tests: {e}")
        return False


def generate_performance_summary():
    """Generate performance summary from latest reports."""
    
    reports_dir = Path(__file__).parent.parent / 'performance_reports'
    benchmarks_dir = reports_dir / 'benchmarks'
    
    if not benchmarks_dir.exists():
        print("No benchmark reports found.")
        return
    
    # Find latest benchmark files
    benchmark_files = list(benchmarks_dir.glob('benchmark_*.json'))
    if not benchmark_files:
        print("No benchmark files found.")
        return
    
    # Sort by modification time
    benchmark_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    print(f"\n=== Latest Performance Benchmarks ===")
    
    for benchmark_file in benchmark_files[:3]:  # Show latest 3
        try:
            with open(benchmark_file, 'r') as f:
                benchmark = json.load(f)
            
            test_name = benchmark.get('test', 'unknown')
            timestamp = benchmark.get('timestamp', 'unknown')
            
            print(f"\n{test_name} ({timestamp}):")
            
            stats = benchmark.get('statistics', {})
            requirements = benchmark.get('requirements', {})
            
            for key, value in stats.items():
                if isinstance(value, (int, float)):
                    # Format based on value
                    if key.endswith('_time'):
                        if value < 0.001:
                            print(f"  {key}: {value*1000:.3f} ms")
                        else:
                            print(f"  {key}: {value:.6f} s")
                    elif key.endswith('_mb'):
                        print(f"  {key}: {value:.1f} MB")
                    elif key.endswith('_percent'):
                        print(f"  {key}: {value:.1f}%")
                    else:
                        print(f"  {key}: {value}")
                elif not isinstance(value, list):
                    print(f"  {key}: {value}")
            
            # Check requirements
            for req_key, req_value in requirements.items():
                if req_key.startswith('max_'):
                    stat_key = req_key[4:]  # Remove 'max_'
                    if stat_key in stats:
                        actual = stats[stat_key]
                        if actual <= req_value:
                            print(f"  ✓ {stat_key} meets requirement: {actual} <= {req_value}")
                        else:
                            print(f"  ✗ {stat_key} exceeds requirement: {actual} > {req_value}")
                elif req_key.startswith('min_'):
                    stat_key = req_key[4:]  # Remove 'min_'
                    if stat_key in stats:
                        actual = stats[stat_key]
                        if actual >= req_value:
                            print(f"  ✓ {stat_key} meets requirement: {actual} >= {req_value}")
                        else:
                            print(f"  ✗ {stat_key} below requirement: {actual} < {req_value}")
        
        except Exception as e:
            print(f"Error reading benchmark file {benchmark_file}: {e}")


def main():
    """Main function."""
    
    print("=" * 60)
    print("Performance Test Runner")
    print("=" * 60)
    
    # Run performance tests
    success = run_performance_tests()
    
    if success:
        # Run benchmarks
        benchmark_success = run_benchmarks()
        
        # Generate summary
        generate_performance_summary()
        
        if benchmark_success:
            print(f"\n✅ All performance tests and benchmarks passed!")
            return 0
        else:
            print(f"\n❌ Benchmark tests failed!")
            return 1
    else:
        print(f"\n❌ Performance tests failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())