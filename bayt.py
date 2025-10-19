import time
import random
import json
import pandas as pd
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import cloudscraper
from pathlib import Path

# ---------------- CONFIG ---------------- #
BASE_URL = "https://www.bayt.com"
LISTING_URL = BASE_URL + "/en/lebanon/jobs/?page={}"
MAX_PAGES = 19
OUTPUT_CSV = "bayt_jobs_bs12.csv"

USE_PROXY = False  # Set True if you have Tor/residential proxy
PROXIES = {
    "http": "socks5://127.0.0.1:9050",
    "https": "socks5://127.0.0.1:9050"
}

COOKIE_FILE = "bayt_cookies.json"  # export from Cookie-Editor (Chrome)

PAGE_DELAY_RANGE = (5, 10)
JOB_DELAY_RANGE = (5, 9)

# ----------------------------------------- #

def load_cookies():
    if not Path(COOKIE_FILE).exists():
        print("⚠️ Cookie file not found. You might face 403s.")
        return {}
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    cookies = {c["name"]: c["value"] for c in raw if "bayt.com" in c.get("domain", "")}
    print(f"✅ Loaded {len(cookies)} cookies")
    return cookies

def make_scraper():
    ua = UserAgent()
    scraper = cloudscraper.create_scraper(delay=random.uniform(1.0, 3.0))
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": BASE_URL + "/en/lebanon/jobs/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": ua.random,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    scraper.headers.update(headers)
    return scraper

def fetch_html(url, cookies, proxies=None):
    for attempt in range(3):
        try:
            scraper = make_scraper()
            resp = scraper.get(url, cookies=cookies, proxies=proxies, timeout=30)
            if resp.status_code == 200:
                return resp.text
            else:
                print(f"⚠️ Got status {resp.status_code} on {url}. Retrying...")
        except Exception as e:
            print(f"⚠️ Error fetching {url}: {e}")
        time.sleep(random.uniform(3, 7))
    return None

def extract_job_links(html):
    soup = BeautifulSoup(html, "html.parser")
    job_links = []
    for a in soup.select("h2.col.u-stretch.t-large.m0.t-nowrap-d.t-trim a[data-js-aid='jobID']"):
        href = a.get("href")
        if href:
            if not href.startswith("http"):
                href = BASE_URL + href
            job_links.append(href)
    if not job_links:
        for a in soup.select("a[href*='/jobs/']"):
            href = a.get("href")
            if href and "/jobs/" in href:
                job_links.append(BASE_URL + href if not href.startswith("http") else href)
    return list(set(job_links))

def extract_listing_info_from_link(soup, link):
    """Extract Job Title, Date, Link, Company from listing page correctly"""
    li_tag = soup.find("a", href=lambda x: x and link.replace(BASE_URL, "") in x)
    title = li_tag.get_text(strip=True) if li_tag else ""

    # Get the parent <li> container to search company/date
    li_parent = li_tag.find_parent("li") if li_tag else None

    # Correct company extraction
    company = ""
    if li_parent:
        company_tag = li_parent.select_one("div.job-company-location-wrapper a.t-default.t-bold")
        if company_tag:
            company = company_tag.get_text(strip=True)
    if not company:
        company = "Confidential"  # ✅ If empty, set as Confidential

    # Correct date extraction
    date_posted = ""
    if li_parent:
        date_tag = li_parent.select_one("div.jb-date span")
        if date_tag:
            date_posted = date_tag.get_text(strip=True)

    return {
        "Job Title": title,
        "Date Posted": date_posted,
        "Link": link,
        "Company": company,
        "Salary": "",
        "Description": ""
    }

def parse_job_page(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # --- Salary ---
    salary_div = soup.select_one("div[data-automation-id='id_salary_range'] span.u-stretch")
    salary = salary_div.get_text(strip=True) if salary_div else "Unspecified"

    # --- Company ---
    company_tag = soup.select_one("div.col.is-8-d ul.list.is-basic li a.t-default.t-bold")
    company = company_tag.get_text(strip=True) if company_tag else "Confidential"

    # --- Job Description ---
    description_text = ""
    # Look for the main Job Description container
    job_section = soup.find(lambda tag: tag.name in ["h2","h3","h4"] and "Job description" in tag.get_text())
    if job_section:
        parts = []
        for elem in job_section.find_all_next():
            text = elem.get_text(" ", strip=True)
            if not text:
                continue
            # Stop collecting when we reach known footer/irrelevant markers
            stop_keywords = ["Loading...", "Email to Friend", "Send Me Similar Jobs", 
                             "Save", "Follow This Company", "Print", "Compare your profile"]
            if any(keyword in text for keyword in stop_keywords):
                break
            parts.append(text)
        description_text = " ".join(parts)
        # Clean multiple spaces
        description_text = " ".join(description_text.split())

    return {
        "Salary": salary,
        "Company": company,
        "Description": description_text
    }

def save_job(job):
    df = pd.DataFrame([job])
    write_header = not Path(OUTPUT_CSV).exists()
    df.to_csv(OUTPUT_CSV, mode="a", header=write_header, index=False, encoding="utf-8-sig")
    print(f"💾 Saved job: {job.get('Job Title','')}")

def run():
    cookies = load_cookies()
    proxies = PROXIES if USE_PROXY else None

    all_job_links = []

    # Step 1: Extract Job Title, Date Posted, Link, Company from listings
    for page_num in range(1, MAX_PAGES + 1):
        print(f"\n🌍 Fetching listing page {page_num}")
        html = fetch_html(LISTING_URL.format(page_num), cookies, proxies)
        if not html:
            print(f"❌ Failed to load listing page {page_num}")
            continue

        job_links = extract_job_links(html)
        print(f"🔗 Found {len(job_links)} job links")
        all_job_links.extend(job_links)

        soup = BeautifulSoup(html, "html.parser")
        for job_link in job_links:
            job = extract_listing_info_from_link(soup, job_link)
            save_job(job)

        time.sleep(random.uniform(*PAGE_DELAY_RANGE))

    # Step 2: Visit each job link to get Salary, Company, Description
    df = pd.read_csv(OUTPUT_CSV)
    for idx, job_link in enumerate(df["Link"], start=1):
        print(f"\n➡️ Fetching job page {idx}/{len(df)}: {job_link}")
        job_html = fetch_html(job_link, cookies, proxies)
        if not job_html:
            print("⚠️ Skipping job (no HTML)")
            continue
        details = parse_job_page(job_html, job_link)
        for key, val in details.items():
            df.loc[df["Link"] == job_link, key] = val
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"💾 Updated job: {df.loc[df['Link'] == job_link, 'Job Title'].values[0]}")
        time.sleep(random.uniform(*JOB_DELAY_RANGE))

    print("\n✅ Finished scraping all pages!")

if __name__ == "__main__":
    run()
