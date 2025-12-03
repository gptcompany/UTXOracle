#!/usr/bin/env python3
"""
UTXOracle Batch Processing Script
Runs UTXOracle for multiple dates with browser suppression and parallel execution
"""

import asyncio
import subprocess
import os
import sys
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

class UTXOracleBatchProcessor:
    def __init__(self, utxoracle_path=None, max_workers=4):
        self.utxoracle_path = utxoracle_path or "/media/sam/1TB/UTXOracle/UTXOracle.py"
        self.max_workers = max_workers
        self.results = []
        
    def run_utxoracle_single(self, date_str, data_dir=None):
        """Run UTXOracle for a single date with browser suppression"""
        cmd = ["python3", self.utxoracle_path, "-d", date_str, "--no-browser"]
        
        if data_dir:
            cmd.extend(["-p", data_dir])
            
        try:
            print(f"Processing {date_str}...")
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Extract price from output
                output_lines = result.stdout.split('\n')
                price_line = [line for line in output_lines if 'price: $' in line]
                price = price_line[0] if price_line else "Price not found"
                
                return {
                    'date': date_str,
                    'status': 'success',
                    'price': price,
                    'html_file': f"UTXOracle_{date_str.replace('/', '-')}.html"
                }
            else:
                return {
                    'date': date_str,
                    'status': 'error',
                    'error': result.stderr,
                    'html_file': None
                }
                
        except subprocess.TimeoutExpired:
            return {
                'date': date_str,
                'status': 'timeout',
                'error': 'Process timed out after 5 minutes',
                'html_file': None
            }
        except Exception as e:
            return {
                'date': date_str,
                'status': 'error',
                'error': str(e),
                'html_file': None
            }
            
    def generate_date_range(self, start_date, end_date):
        """Generate list of dates between start and end"""
        start = datetime.strptime(start_date, "%Y/%m/%d")
        end = datetime.strptime(end_date, "%Y/%m/%d")
        
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y/%m/%d"))
            current += timedelta(days=1)
            
        return dates
        
    def run_parallel_batch(self, dates, data_dir=None):
        """Run UTXOracle for multiple dates in parallel"""
        print(f"Starting batch processing for {len(dates)} dates with {self.max_workers} workers")
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_date = {
                executor.submit(self.run_utxoracle_single, date, data_dir): date 
                for date in dates
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_date):
                date = future_to_date[future]
                try:
                    result = future.result()
                    self.results.append(result)
                    
                    if result['status'] == 'success':
                        print(f"✓ {date}: {result['price']}")
                    else:
                        print(f"✗ {date}: {result['status']} - {result.get('error', '')}")
                        
                except Exception as e:
                    print(f"✗ {date}: Exception - {str(e)}")
                    self.results.append({
                        'date': date,
                        'status': 'exception',
                        'error': str(e),
                        'html_file': None
                    })
                    
        return self.results
        
    def generate_summary_report(self, output_file="batch_summary.html"):
        """Generate HTML summary report of batch results"""
        successful = [r for r in self.results if r['status'] == 'success']
        failed = [r for r in self.results if r['status'] != 'success']
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>UTXOracle Batch Processing Summary</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .stat-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #007bff; }}
        .results-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        .results-table th, .results-table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        .results-table th {{ background-color: #f8f9fa; }}
        .success {{ color: #28a745; }}
        .error {{ color: #dc3545; }}
        .html-link {{ color: #007bff; text-decoration: none; }}
        .html-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>UTXOracle Batch Processing Summary</h1>
            <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{len(self.results)}</div>
                <div>Total Processed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number success">{len(successful)}</div>
                <div>Successful</div>
            </div>
            <div class="stat-card">
                <div class="stat-number error">{len(failed)}</div>
                <div>Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(successful)/len(self.results)*100:.1f}%</div>
                <div>Success Rate</div>
            </div>
        </div>
        
        <h2>Results</h2>
        <table class="results-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Status</th>
                    <th>Price</th>
                    <th>HTML File</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
"""
        
        for result in sorted(self.results, key=lambda x: x['date']):
            status_class = 'success' if result['status'] == 'success' else 'error'
            html_link = f'<a href="{result["html_file"]}" class="html-link">{result["html_file"]}</a>' if result['html_file'] else 'N/A'
            
            html_content += f"""
                <tr>
                    <td>{result['date']}</td>
                    <td class="{status_class}">{result['status']}</td>
                    <td>{result.get('price', 'N/A')}</td>
                    <td>{html_link}</td>
                    <td>{result.get('error', '')}</td>
                </tr>
"""
        
        html_content += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        
        with open(output_file, 'w') as f:
            f.write(html_content)
            
        print(f"Summary report generated: {output_file}")
        return output_file


def main():
    if len(sys.argv) < 3:
        print("Usage: python utxoracle_batch.py <start_date> <end_date> [data_dir] [max_workers]")
        print("Example: python utxoracle_batch.py 2024/01/01 2024/01/07")
        sys.exit(1)
        
    start_date = sys.argv[1]
    end_date = sys.argv[2]
    data_dir = sys.argv[3] if len(sys.argv) > 3 else None
    max_workers = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    
    processor = UTXOracleBatchProcessor(max_workers=max_workers)
    
    # Generate date range
    dates = processor.generate_date_range(start_date, end_date)
    
    # Run batch processing
    results = processor.run_parallel_batch(dates, data_dir)
    
    # Generate summary report
    summary_file = processor.generate_summary_report()
    
    # Print final summary
    successful = len([r for r in results if r['status'] == 'success'])
    total = len(results)
    
    print(f"\nBatch processing complete!")
    print(f"Processed: {total} dates")
    print(f"Successful: {successful}")
    print(f"Failed: {total - successful}")
    print(f"Success rate: {successful/total*100:.1f}%")
    print(f"Summary report: {summary_file}")

if __name__ == "__main__":
    main()
