import asyncio
import httpx
import random
import argparse
import sys
from datetime import datetime

def get_args():
    parser = argparse.ArgumentParser(description="WPR - WordPress Reaper")
    parser.add_argument("-t", "--target", help="Target URL", required=True)
    parser.add_argument("-c", "--concurrency", type=int, help="Concurrency", default=25)
    return parser.parse_args()

def get_wordlist():
    try:
        with open("db.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        sys.exit(1)

async def check_year_exists(client, target, year):
    url = f"{target}/wp-content/uploads/{year}/"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    try:
        res = await client.head(url, headers={"User-Agent": ua}, timeout=5.0, follow_redirects=True)
        return res.status_code == 200
    except:
        return False

async def scan(client, sem, url, is_dir=False):
    async with sem:
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/123.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
        ]
        headers = {"User-Agent": random.choice(ua_list)}
        try:
            if is_dir:
                res = await client.get(url, headers=headers, timeout=10.0, follow_redirects=True)
                if res.status_code == 429:
                    await asyncio.sleep(3)
                    return await scan(client, sem, url, is_dir)
                if res.status_code == 200 and "Index of" in res.text:
                    print(f"[!] DIRECTORY LISTING EXPOSED: {url}")
                    with open("results.txt", "a") as f: f.write(f"[DIR] {url}\n")
            else:
                res = await client.head(url, headers=headers, timeout=10.0, follow_redirects=True)
                if res.status_code == 429:
                    await asyncio.sleep(3)
                    return await scan(client, sem, url, is_dir)
                if res.status_code == 200:
                    ctype = res.headers.get("Content-Type", "").lower()
                    if "text/html" in ctype and not (url.endswith('.html') or url.endswith('.htm')): return
                    print(f"[+] FOUND: {url}")
                    with open("results.txt", "a") as f: f.write(url + "\n")
        except:
            pass

async def main():
    args = get_args()
    words = get_wordlist()
    target = args.target.rstrip('/')
    current_year = datetime.now().year
    
    limits = httpx.Limits(max_keepalive_connections=args.concurrency, max_connections=args.concurrency)
    async with httpx.AsyncClient(http2=True, limits=limits, verify=False, timeout=None) as client:
        print(f"[*] Starting binary search for start year...")
        
        low = 2000
        high = current_year
        start_year = current_year
        
        while low <= high:
            mid = (low + high) // 2
            if await check_year_exists(client, target, mid):
                start_year = mid
                high = mid - 1
            else:
                low = mid + 1
        
        print(f"[+] Detected start year: {start_year}")

        sem = asyncio.Semaphore(args.concurrency)
        tasks = []
        m_variants = [f"{i:02d}" for i in range(1, 13)] + \
                     ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        
        main_uploads = f"{target}/wp-content/uploads/"
        tasks.append(scan(client, sem, main_uploads, is_dir=True))
        for file in words: tasks.append(scan(client, sem, main_uploads + file))

        for year in range(start_year, current_year + 1):
            for variant in m_variants:
                base_url = f"{target}/wp-content/uploads/{year}/{variant}/"
                tasks.append(scan(client, sem, base_url, is_dir=True))
                for file in words: tasks.append(scan(client, sem, base_url + file))
        
        print(f"[*] Scanning {len(tasks)} paths from {start_year} to {current_year}...")
        await asyncio.gather(*tasks)

    print("[*] Completed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
