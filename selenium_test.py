import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
import json
from urllib.parse import urljoin, urlparse
import difflib

def analyze_website(url, headless=True, wait_time=8):
    """
    Advanced analysis to determine if Selenium is needed for web scraping.
    Uses multiple detection methods for higher accuracy.
    """
    result = {
        "url": url,
        "needs_selenium": False,
        "confidence": 0,
        "requests_len": 0,
        "selenium_len": 0,
        "frameworks_detected": [],
        "reasons": [],
        "content_analysis": {},
        "dynamic_indicators": []
    }
    
    # --- Step 1: Load with Requests ---
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        html_requests = response.text
        result["requests_len"] = len(html_requests)
        
        # Parse with BeautifulSoup for better analysis
        soup_requests = BeautifulSoup(html_requests, 'html.parser')
        
    except Exception as e:
        result["needs_selenium"] = True
        result["reasons"].append(f"Requests failed: {e}")
        result["confidence"] = 90
        return result
    
    # --- Step 2: Pre-analysis of HTML content ---
    dynamic_indicators = analyze_html_indicators(html_requests)
    result["dynamic_indicators"] = dynamic_indicators
    
    # If strong indicators of dynamic content, likely needs Selenium
    if len(dynamic_indicators) >= 3:
        result["needs_selenium"] = True
        result["reasons"].append("Multiple dynamic content indicators found")
        result["confidence"] = 85
    
    # --- Step 3: Load with Selenium ---
    driver = None
    try:
        options = Options()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.get(url)
        
        # Wait for page to load and check for dynamic content
        WebDriverWait(driver, 10).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
        
        # Additional wait for dynamic content
        time.sleep(wait_time)
        
        html_selenium = driver.page_source
        result["selenium_len"] = len(html_selenium)
        
        # Parse selenium content
        soup_selenium = BeautifulSoup(html_selenium, 'html.parser')
        
        # --- Framework Detection ---
        frameworks = detect_js_frameworks(driver, html_selenium)
        result["frameworks_detected"] = frameworks
        
    except Exception as e:
        if driver:
            driver.quit()
        result["needs_selenium"] = True
        result["reasons"].append(f"Selenium failed: {e}")
        result["confidence"] = 70
        return result
    
    # --- Step 4: Advanced Content Analysis ---
    content_analysis = compare_content_quality(soup_requests, soup_selenium, url)
    result["content_analysis"] = content_analysis
    
    # --- Step 5: Decision Logic ---
    decision_score = calculate_selenium_need_score(
        result["requests_len"],
        result["selenium_len"],
        frameworks,
        dynamic_indicators,
        content_analysis
    )
    
    result["needs_selenium"] = decision_score > 50
    result["confidence"] = abs(decision_score - 50) + 50  # Convert to confidence percentage
    
    # Add detailed reasons
    if decision_score > 50:
        result["reasons"] = generate_reasons_for_selenium(frameworks, dynamic_indicators, content_analysis)
    else:
        result["reasons"] = ["Static HTML provides sufficient content for scraping"]
    
    if driver:
        driver.quit()
    
    return result

def analyze_html_indicators(html):
    """Analyze HTML for indicators that suggest dynamic content loading."""
    indicators = []
    html_lower = html.lower()
    
    # Check for SPA indicators
    spa_patterns = [
        r'<div[^>]*id=["\']root["\']',
        r'<div[^>]*id=["\']app["\']',
        r'<div[^>]*id=["\']main["\']',
        r'<div[^>]*class=["\'][^"\']*app[^"\']*["\']'
    ]
    
    for pattern in spa_patterns:
        if re.search(pattern, html_lower):
            indicators.append("SPA root element detected")
            break
    
    # Check for loading indicators
    if any(term in html_lower for term in ['loading...', 'please wait', 'spinner', 'skeleton']):
        indicators.append("Loading indicators found")
    
    # Check for AJAX/fetch calls
    ajax_patterns = [
        r'\.fetch\s*\(',
        r'XMLHttpRequest',
        r'axios\.',
        r'jquery.*ajax',
        r'api/.*endpoint'
    ]
    
    for pattern in ajax_patterns:
        if re.search(pattern, html_lower):
            indicators.append("AJAX/API calls detected")
            break
    
    # Check for lazy loading
    if re.search(r'data-src|lazy.*load|intersection.*observer', html_lower):
        indicators.append("Lazy loading detected")
    
    # Check for virtual scrolling or infinite scroll
    if re.search(r'virtual.*scroll|infinite.*scroll', html_lower):
        indicators.append("Virtual/infinite scrolling detected")
    
    return list(set(indicators))

def detect_js_frameworks(driver, html):
    """Enhanced framework detection."""
    frameworks = []
    html_lower = html.lower()
    
    # Check via JavaScript execution
    try:
        # React detection
        react_check = driver.execute_script("""
            return !!(window.React || window.ReactDOM || 
                     document.querySelector('[data-reactroot]') ||
                     document.querySelector('[data-react-helmet]') ||
                     !!document.querySelector('script').innerHTML.includes('React'));
        """)
        if react_check:
            frameworks.append("React")
        
        # Angular detection
        angular_check = driver.execute_script("""
            return !!(window.ng || window.angular || window.Zone ||
                     document.querySelector('[ng-app]') ||
                     document.querySelector('[data-ng-app]') ||
                     document.querySelector('app-root'));
        """)
        if angular_check:
            frameworks.append("Angular")
        
        # Vue detection
        vue_check = driver.execute_script("""
            return !!(window.Vue || document.querySelector('[data-v-]') ||
                     document.querySelector('#app').__vue__);
        """)
        if vue_check:
            frameworks.append("Vue")
        
        # jQuery detection (often used with dynamic content)
        jquery_check = driver.execute_script("return !!(window.jQuery || window.$);")
        if jquery_check:
            frameworks.append("jQuery")
            
    except Exception:
        pass
    
    # Fallback: text-based detection
    framework_patterns = {
        'React': [r'react', r'reactdom', r'jsx', r'data-reactroot'],
        'Angular': [r'angular', r'@angular', r'ng-app', r'app-root'],
        'Vue': [r'vue\.js', r'vuejs', r'v-if', r'v-for'],
        'jQuery': [r'jquery', r'\$\('],
        'Next.js': [r'next\.js', r'_next'],
        'Nuxt': [r'nuxt', r'__nuxt'],
        'Svelte': [r'svelte'],
        'Ember': [r'ember']
    }
    
    for framework, patterns in framework_patterns.items():
        if framework not in frameworks:
            for pattern in patterns:
                if re.search(pattern, html_lower):
                    frameworks.append(framework)
                    break
    
    return list(set(frameworks))

def compare_content_quality(soup_requests, soup_selenium, url):
    """Compare the actual useful content between requests and selenium."""
    analysis = {
        "text_diff_ratio": 0,
        "element_count_diff": 0,
        "important_content_missing": False,
        "new_content_types": []
    }
    
    try:
        # Extract meaningful content
        requests_text = extract_meaningful_content(soup_requests)
        selenium_text = extract_meaningful_content(soup_selenium)
        
        # Calculate text similarity
        similarity = difflib.SequenceMatcher(None, requests_text, selenium_text).ratio()
        analysis["text_diff_ratio"] = 1 - similarity
        
        # Count important elements
        important_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'td', 'span', 'div']
        
        requests_elements = sum(len(soup_requests.find_all(tag)) for tag in important_tags)
        selenium_elements = sum(len(soup_selenium.find_all(tag)) for tag in important_tags)
        
        if requests_elements > 0:
            analysis["element_count_diff"] = (selenium_elements - requests_elements) / requests_elements
        
        # Check for important content missing in requests version
        selenium_headings = [h.get_text().strip() for h in soup_selenium.find_all(['h1', 'h2', 'h3'])]
        requests_headings = [h.get_text().strip() for h in soup_requests.find_all(['h1', 'h2', 'h3'])]
        
        missing_headings = set(selenium_headings) - set(requests_headings)
        if len(missing_headings) > len(selenium_headings) * 0.3:  # More than 30% headings missing
            analysis["important_content_missing"] = True
        
        # Check for new content types in Selenium version
        selenium_forms = len(soup_selenium.find_all('form'))
        requests_forms = len(soup_requests.find_all('form'))
        if selenium_forms > requests_forms:
            analysis["new_content_types"].append("forms")
        
        selenium_buttons = len(soup_selenium.find_all('button'))
        requests_buttons = len(soup_requests.find_all('button'))
        if selenium_buttons > requests_buttons * 1.5:
            analysis["new_content_types"].append("interactive_elements")
            
    except Exception as e:
        print(f"Error in content comparison: {e}")
    
    return analysis

def extract_meaningful_content(soup):
    """Extract meaningful text content, excluding scripts, styles, etc."""
    # Remove script and style elements
    for script in soup(["script", "style", "meta", "link", "noscript"]):
        script.decompose()
    
    # Get text and clean it
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = ' '.join(chunk for chunk in chunks if chunk)
    
    return text

def calculate_selenium_need_score(requests_len, selenium_len, frameworks, indicators, content_analysis):
    """Calculate a score to determine if Selenium is needed (0-100)."""
    score = 0
    
    # Framework scoring
    framework_weights = {
        'React': 35,
        'Angular': 35,
        'Vue': 35,
        'Next.js': 30,
        'Nuxt': 30,
        'Svelte': 25,
        'Ember': 25,
        'jQuery': 15
    }
    
    for framework in frameworks:
        score += framework_weights.get(framework, 10)
    
    # Dynamic indicators scoring
    score += len(indicators) * 8
    
    # Content analysis scoring
    if content_analysis.get("text_diff_ratio", 0) > 0.3:  # 30% text difference
        score += 25
    
    if content_analysis.get("element_count_diff", 0) > 0.5:  # 50% more elements
        score += 20
    
    if content_analysis.get("important_content_missing", False):
        score += 30
    
    score += len(content_analysis.get("new_content_types", [])) * 15
    
    # Length-based scoring (less weight than before)
    if selenium_len > requests_len * 2:
        score += 20
    elif selenium_len > requests_len * 1.5:
        score += 10
    
    # Cap the score at 100
    return min(score, 100)

def generate_reasons_for_selenium(frameworks, indicators, content_analysis):
    """Generate human-readable reasons why Selenium is needed."""
    reasons = []
    
    if frameworks:
        reasons.append(f"JavaScript frameworks detected: {', '.join(frameworks)}")
    
    if indicators:
        reasons.append(f"Dynamic content indicators: {', '.join(indicators)}")
    
    if content_analysis.get("text_diff_ratio", 0) > 0.3:
        reasons.append("Significant content difference between static and dynamic versions")
    
    if content_analysis.get("important_content_missing", False):
        reasons.append("Important content (headings, structure) missing in static version")
    
    if content_analysis.get("new_content_types"):
        reasons.append(f"Additional interactive elements found: {', '.join(content_analysis['new_content_types'])}")
    
    if not reasons:
        reasons.append("Content is significantly enhanced by JavaScript execution")
    
    return reasons

def batch_analyze_websites(urls, output_file=None, max_workers=3, progress_callback=None):
    """
    Analyze multiple websites in batch with optional parallel processing.
    
    :param urls: List of URLs or path to file containing URLs
    :param output_file: Optional path to save results as JSON/CSV
    :param max_workers: Number of parallel workers (default: 3)
    :param progress_callback: Optional callback function for progress updates
    :return: List of analysis results
    """
    import concurrent.futures
    import csv
    import os
    from datetime import datetime
    
    # Handle URLs input
    if isinstance(urls, str) and os.path.isfile(urls):
        with open(urls, 'r') as f:
            url_list = [line.strip() for line in f if line.strip()]
    elif isinstance(urls, str):
        url_list = [url.strip() for url in urls.split(',') if url.strip()]
    else:
        url_list = urls
    
    # Clean and validate URLs
    clean_urls = []
    for url in url_list:
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        clean_urls.append(url)
    
    results = []
    total_urls = len(clean_urls)
    
    print(f"\n🚀 Starting batch analysis of {total_urls} websites...")
    print(f"🔧 Using {max_workers} parallel workers")
    print("=" * 80)
    
    def analyze_single_with_progress(url_index_tuple):
        url, index = url_index_tuple
        try:
            result = analyze_website(url)
            result['processed_at'] = datetime.now().isoformat()
            result['batch_index'] = index + 1
            
            # Progress callback
            if progress_callback:
                progress_callback(index + 1, total_urls, result)
            else:
                status = "✅ YES" if result['needs_selenium'] else "❌ NO"
                print(f"[{index + 1:3d}/{total_urls}] {status} | {result['confidence']:3.0f}% | {url}")
            
            return result
        except Exception as e:
            error_result = {
                'url': url,
                'needs_selenium': True,
                'confidence': 0,
                'error': str(e),
                'processed_at': datetime.now().isoformat(),
                'batch_index': index + 1
            }
            print(f"[{index + 1:3d}/{total_urls}] ❌ ERROR | {url} - {str(e)}")
            return error_result
    
    # Process URLs with threading
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        url_index_pairs = [(url, i) for i, url in enumerate(clean_urls)]
        future_to_url = {executor.submit(analyze_single_with_progress, pair): pair[0] 
                        for pair in url_index_pairs}
        
        for future in concurrent.futures.as_completed(future_to_url):
            result = future.result()
            results.append(result)
    
    # Sort results by batch_index to maintain order
    results.sort(key=lambda x: x.get('batch_index', 0))
    
    print("=" * 80)
    print("📊 BATCH ANALYSIS SUMMARY")
    print("=" * 80)
    
    selenium_needed = sum(1 for r in results if r.get('needs_selenium', False))
    static_sufficient = total_urls - selenium_needed
    avg_confidence = sum(r.get('confidence', 0) for r in results) / len(results) if results else 0
    
    print(f"Total websites analyzed: {total_urls}")
    print(f"✅ Need Selenium: {selenium_needed} ({selenium_needed/total_urls*100:.1f}%)")
    print(f"❌ Static sufficient: {static_sufficient} ({static_sufficient/total_urls*100:.1f}%)")
    print(f"📈 Average confidence: {avg_confidence:.1f}%")
    
    # Framework statistics
    all_frameworks = []
    for r in results:
        all_frameworks.extend(r.get('frameworks_detected', []))
    
    if all_frameworks:
        from collections import Counter
        framework_counts = Counter(all_frameworks)
        print(f"\n🔧 Most detected frameworks:")
        for framework, count in framework_counts.most_common(5):
            print(f"   • {framework}: {count} sites")
    
    # Save results if requested
    if output_file:
        save_results(results, output_file)
        print(f"\n💾 Results saved to: {output_file}")
    
    return results

def save_results(results, output_file):
    """Save analysis results to JSON or CSV file."""
    import json
    
    file_ext = output_file.lower().split('.')[-1]
    
    if file_ext == 'json':
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    
    elif file_ext == 'csv':
        import csv
        
        if not results:
            return
        
        fieldnames = [
            'url', 'needs_selenium', 'confidence', 'requests_len', 'selenium_len',
            'frameworks_detected', 'reasons', 'processed_at', 'batch_index'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                # Convert lists to strings for CSV
                row = result.copy()
                row['frameworks_detected'] = ', '.join(result.get('frameworks_detected', []))
                row['reasons'] = ' | '.join(result.get('reasons', []))
                writer.writerow(row)
    else:
        # Default to JSON
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

def interactive_menu():
    """Interactive menu for different analysis modes."""
    print("\n🔹 SELENIUM DETECTION ANALYZER")
    print("=" * 50)
    print("Choose analysis mode:")
    print("1. Single website")
    print("2. Multiple websites (manual input)")
    print("3. Batch from file")
    print("4. Quick test with sample URLs")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == '1':
        # Single website analysis
        url = input("\nEnter website URL: ").strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        print(f"\n🔄 Analyzing {url}...")
        analysis = analyze_website(url)
        display_single_result(analysis)
    
    elif choice == '2':
        # Multiple websites manual input
        print("\nEnter URLs (one per line, press Enter twice to finish):")
        urls = []
        while True:
            url = input().strip()
            if not url:
                break
            urls.append(url)
        
        if urls:
            save_choice = input("\nSave results to file? (y/n): ").strip().lower()
            output_file = None
            if save_choice == 'y':
                output_file = input("Enter filename (e.g., results.json or results.csv): ").strip()
            
            results = batch_analyze_websites(urls, output_file)
            display_batch_summary(results)
    
    elif choice == '3':
        # Batch from file
        file_path = input("\nEnter path to file containing URLs: ").strip()
        
        if not os.path.isfile(file_path):
            print("❌ File not found!")
            return
        
        workers = input("Number of parallel workers (default 3): ").strip()
        workers = int(workers) if workers.isdigit() else 3
        
        output_file = input("Save results to (optional, e.g., results.json): ").strip()
        output_file = output_file if output_file else None
        
        results = batch_analyze_websites(file_path, output_file, max_workers=workers)
        display_batch_summary(results)
    
    elif choice == '4':
        # Quick test with sample URLs
        sample_urls = [
            "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "https://docs.python.org/3/",
            "https://stackoverflow.com/questions/tagged/python",
            "https://www.bbc.com/news",
            "https://example.com"
        ]
        
        print("\n🧪 Testing with sample URLs...")
        results = batch_analyze_websites(sample_urls)
        display_batch_summary(results)
    
    else:
        print("❌ Invalid choice!")

def display_single_result(analysis):
    """Display results for a single website analysis."""
    print("\n" + "=" * 60)
    print("🔹 SELENIUM DETECTION ANALYSIS")
    print("=" * 60)
    print(f"URL: {analysis['url']}")
    print(f"Needs Selenium: {'✅ YES' if analysis['needs_selenium'] else '❌ NO'}")
    print(f"Confidence: {analysis['confidence']:.1f}%")
    print("\n📊 Content Metrics:")
    print(f"  • Requests content length: {analysis['requests_len']:,} chars")
    print(f"  • Selenium content length: {analysis['selenium_len']:,} chars")
    
    if analysis['frameworks_detected']:
        print(f"\n🔧 JavaScript Frameworks: {', '.join(analysis['frameworks_detected'])}")
    
    if analysis['dynamic_indicators']:
        print(f"\n⚡ Dynamic Content Indicators:")
        for indicator in analysis['dynamic_indicators']:
            print(f"  • {indicator}")
    
    print(f"\n💡 Reasons:")
    for reason in analysis['reasons']:
        print(f"  • {reason}")
    
    print("\n" + "=" * 60)

def display_batch_summary(results):
    """Display summary of batch results with detailed breakdown."""
    print("\n📋 DETAILED RESULTS:")
    print("-" * 80)
    
    selenium_sites = [r for r in results if r.get('needs_selenium', False)]
    static_sites = [r for r in results if not r.get('needs_selenium', False)]
    
    print(f"\n✅ SITES NEEDING SELENIUM ({len(selenium_sites)}):")
    for result in selenium_sites:
        frameworks = ', '.join(result.get('frameworks_detected', []))
        frameworks_str = f" | {frameworks}" if frameworks else ""
        print(f"   • {result['url']} ({result.get('confidence', 0):.0f}%){frameworks_str}")
    
    print(f"\n❌ SITES WITH STATIC CONTENT ({len(static_sites)}):")
    for result in static_sites:
        print(f"   • {result['url']} ({result.get('confidence', 0):.0f}%)")

# --- Main execution ---
if __name__ == "__main__":
    import os
    interactive_menu()