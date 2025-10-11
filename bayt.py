# bayt_scraper_final.py
# Requirements: pip install selenium
# Make sure Tor is running: socks5 proxy on 127.0.0.1:9050
# Make sure chromedriver for your Chrome is placed at C:\Windows\chromedriver.exe

import os
import json
import csv
import time
import random
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ------------- CONFIG -------------
CHROMEDRIVER_PATH = r"C:\Windows\chromedriver.exe"   # use your chromedriver here
TOR_SOCKS = "socks5://127.0.0.1:9050"                # ensure Tor is running
OUTPUT_CSV = "bayt_job1.csv"
PROGRESS_FILE = "progress.json"
BASE_LISTING_TEMPLATE = "https://www.bayt.com/en/lebanon/jobs/?page={page}"
START_PAGE = 1
PAGE_LOAD_TIMEOUT = 20
JOB_LOAD_TIMEOUT = 12
DELAY_BETWEEN_JOBS = (1.5, 3.5)
DELAY_BETWEEN_PAGES = (4, 8)
LONG_BREAK_EVERY = 4
LONG_BREAK = (12, 22)
CSV_FIELDS = ["job_id", "job_title", "company", "date_posted", "salary", "job_description", "job_url", "scraped_at"]

# small pool of user agents (expand if you want)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7339.208 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# ------------- helpers -------------
def rnd(a, b):
    time.sleep(random.uniform(a, b))

def get_random_ua():
    return random.choice(USER_AGENTS)

def read_progress():
    if Path(PROGRESS_FILE).is_file():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def write_progress(d):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f)

def append_to_csv(rows, csv_path=OUTPUT_CSV):
    file_exists = Path(csv_path).is_file()
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        for r in rows:
            writer.writerow(r)

def ensure_empty_temp_profile():
    # create a fresh temp directory for Chrome user-data-dir
    td = tempfile.mkdtemp(prefix="chrome_profile_")
    return td

def safe_quit(driver):
    try:
        driver.quit()
    except:
        pass

# ------------- webdriver factory -------------
def create_driver(user_agent=None, user_data_dir=None, proxy=TOR_SOCKS):
    ua = user_agent or get_random_ua()
    ud = user_data_dir or ensure_empty_temp_profile()

    options = Options()
    # pass flags similar to your manual launch
    options.add_argument(f"--user-data-dir={ud}")
    options.add_argument("--incognito")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument(f"--user-agent={ua}")
    options.add_argument(f"--proxy-server={proxy}")
    options.add_argument("--start-maximized")

    # stability flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # On Windows sometimes required:
    options.add_argument("--disable-features=RendererCodeIntegrity")

    # Create service with explicit path (Selenium 4)
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    return driver, ud

# ------------- parsing helpers -------------
def parse_job_detail_in_sidebar(driver):
    """Given the listing driver where job details are loaded into a side panel,
    parse the title, company, date posted, salary, description, job_url, id."""
    out = {k: "Not specified" for k in CSV_FIELDS}
    out["scraped_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # job url fallback
        try:
            easy = driver.find_element(By.CSS_SELECTOR, "a.external-job-apply")
            out["job_url"] = easy.get_attribute("href") or driver.current_url
        except:
            out["job_url"] = driver.current_url

        # title
        try:
            t = driver.find_element(By.CSS_SELECTOR, "#jobViewJobTitle").text.strip()
            if t:
                out["job_title"] = t
        except:
            pass

        # company
        try:
            comp = driver.find_element(By.CSS_SELECTOR, ".card-content a.t-default.t-bold").text.strip()
            if comp:
                out["company"] = comp
        except:
            pass

        # date posted
        try:
            dp = driver.find_element(By.CSS_SELECTOR, "#jb-widget-posted-date").text.strip()
            if dp:
                out["date_posted"] = dp
        except:
            try:
                dp = driver.find_element(By.CSS_SELECTOR, "span[data-automation-jobactivedate]").text.strip()
                if dp:
                    out["date_posted"] = dp
            except:
                pass

        # salary
        try:
            sal = driver.find_element(By.CSS_SELECTOR, "[data-automation-id='id_salary_range'] .u-stretch").text.strip()
            if sal:
                out["salary"] = sal
            else:
                out["salary"] = "Not specified"
        except:
            out["salary"] = "Not specified"

        # job description: find h3 'Job Description' then gather siblings until break markers
        try:
            header = None
            headers = driver.find_elements(By.CSS_SELECTOR, "h3")
            for h in headers:
                if "job description" in (h.text or "").lower():
                    header = h
                    break
            if header:
                parts = []
                # gather following siblings until end marker
                sibling = None
                try:
                    sibling = header.find_element(By.XPATH, "following-sibling::*[1]")
                except:
                    sibling = None
                while sibling:
                    txt = (sibling.text or "").strip()
                    # break conditions
                    if any(marker.lower() in txt.lower() for marker in ["preferred candidate", "skills", "company", "compare your profile", "company profile", "applicant-compare"]):
                        break
                    if txt:
                        parts.append(txt)
                    # next sibling
                    try:
                        sibling = sibling.find_element(By.XPATH, "following-sibling::*[1]")
                    except:
                        break
                out["job_description"] = "\n\n".join([p for p in parts if p]) or "Not specified"
            else:
                # fallback to larger container
                try:
                    cont = driver.find_element(By.CSS_SELECTOR, ".u-scrolly")
                    out["job_description"] = cont.text.strip() or "Not specified"
                except:
                    out["job_description"] = "Not specified"
        except Exception:
            out["job_description"] = "Not specified"

        # try to get job_id from url
        try:
            job_url = out.get("job_url","")
            possible_id = job_url.rstrip("/").split("-")[-1]
            if possible_id.isdigit():
                out["job_id"] = possible_id
        except:
            pass

    except Exception as e:
        print("[!] parse_job_detail_in_sidebar error:", e)
    return out

def is_blocked(driver):
    src = driver.page_source.lower()
    if "access denied" in src or "captcha" in src or "please verify" in src:
        return True
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "li[data-js-job]")
        if not elems:
            return True
    except:
        return True
    return False

# ------------- core scraping logic -------------
def scrape_listing_pages(start_page=START_PAGE):
    prog = read_progress()
    last_done = prog.get("last_completed_page", 0)
    page = start_page if last_done < start_page else last_done + 1
    total_saved = 0

    while True:
        listing_url = BASE_LISTING_TEMPLATE.format(page=page)
        print("\n" + "="*60)
        print(f"🌍 Starting listing page {page} -> {listing_url}")

        # fresh driver & profile per page (helps avoid crashes & rotates UA)
        user_agent = get_random_ua()
        user_profile = ensure_empty_temp_profile()
        driver = None
        try:
            driver, profile_dir = create_driver(user_agent=user_agent, user_data_dir=user_profile, proxy=TOR_SOCKS)
        except Exception as e:
            print("[!] Failed to start driver:", e)
            # cleanup temp dir
            try:
                shutil.rmtree(user_profile, ignore_errors=True)
            except:
                pass
            # small delay then try next iteration (or break)
            time.sleep(4)
            break

        try:
            wait = WebDriverWait(driver, PAGE_LOAD_TIMEOUT)
            driver.get(listing_url)
            # wait for job items
            try:
                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-js-job]")))
            except Exception:
                print("⚠️ Listing page items not loaded or timed out.")
                # check if site redirected back to an earlier page (last page)
                cur_url = driver.current_url
                if "?page=" in cur_url:
                    try:
                        cur_page = int(cur_url.split("page=")[-1].split("&")[0])
                        if cur_page < page:
                            print(f"[+] Redirected to page {cur_page} (requested page {page}) -> reached last page. Stopping.")
                            safe_quit(driver)
                            shutil.rmtree(user_profile, ignore_errors=True)
                            break
                    except:
                        pass
                # check for block
                if is_blocked(driver):
                    print("[!] Block detected on listing page. Quitting this page and retrying later.")
                    safe_quit(driver)
                    shutil.rmtree(user_profile, ignore_errors=True)
                    time.sleep(6)
                    # do not increment page, try again (or exit)
                    break
                # otherwise continue with whatever elements found or break
            # get job elements
            job_items = driver.find_elements(By.CSS_SELECTOR, "li[data-js-job]")
            if not job_items:
                print("[!] No job items found on this page; stopping.")
                safe_quit(driver)
                shutil.rmtree(user_profile, ignore_errors=True)
                break

            print(f"🧾 Found {len(job_items)} job entries on page {page}")

            # iterate job items
            page_rows = []
            for j_idx, job_li in enumerate(job_items, start=1):
                try:
                    # scroll into view
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", job_li)
                    time.sleep(random.uniform(0.5, 1.2))

                    # try clicking the job to load sidebar / details
                    clicked = False
                    try:
                        clickable = job_li.find_element(By.CSS_SELECTOR, "h2 a")
                        driver.execute_script("arguments[0].click();", clickable)
                        clicked = True
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", job_li)
                            clicked = True
                        except Exception:
                            clicked = False

                    if not clicked:
                        print(f"[!] Could not click job {j_idx} on page {page}, skipping.")
                        continue

                    # wait for job detail title to update
                    try:
                        WebDriverWait(driver, JOB_LOAD_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#jobViewJobTitle")))
                    except:
                        # allow best-effort parse even if timeout
                        print("[!] Warning: job detail title didn't appear within timeout; attempting to parse anyway.")

                    # detect block after opening
                    if is_blocked(driver):
                        print("[!] Block detected after opening job. Aborting page.")
                        raise RuntimeError("blocked")

                    job_data = parse_job_detail_in_sidebar(driver)
                    page_rows.append(job_data)
                    total_saved += 1
                    print(f"[+] Page {page} Job {j_idx}/{len(job_items)} scraped: {job_data.get('job_title','')[:70]}")
                    # append immediately
                    append_to_csv([job_data], OUTPUT_CSV)

                    # human-like waits between jobs
                    time.sleep(random.uniform(*DELAY_BETWEEN_JOBS))
                except RuntimeError:
                    # blocked
                    break
                except Exception as e:
                    print("[!] Error scraping job item:", e)
                    continue

            # mark page completed only if at least one job was saved
            if page_rows:
                write_progress({"last_completed_page": page})
                print(f"[+] Completed page {page} -> progress saved.")

            # attempt to click next button on listing (in the same driver)
            try:
                # Wait a bit before finding next
                time.sleep(random.uniform(1.0, 2.0))
                next_btn = driver.find_element(By.CSS_SELECTOR, "li.pagination-next a")
                if next_btn and next_btn.is_displayed():
                    # click next
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                    time.sleep(random.uniform(0.8, 1.6))
                    ActionChains(driver).move_to_element(next_btn).click(next_btn).perform()
                    print(f"➡️ Clicked Next to go to page {page+1}.")
                    # cleanup current driver (we will create a fresh driver for next page)
                    safe_quit(driver)
                    shutil.rmtree(user_profile, ignore_errors=True)
                    # human wait between page transitions
                    time.sleep(random.uniform(*DELAY_BETWEEN_PAGES))
                    # occasionally a longer break
                    if page % LONG_BREAK_EVERY == 0:
                        print("💤 Taking a longer break to be friendly...")
                        time.sleep(random.uniform(*LONG_BREAK))
                    page += 1
                    continue
                else:
                    print("[+] No next button displayed -> finished.")
                    safe_quit(driver)
                    shutil.rmtree(user_profile, ignore_errors=True)
                    break
            except Exception:
                # no next button -> finish
                print("[+] No next page found (or clickable) -> finished.")
                safe_quit(driver)
                shutil.rmtree(user_profile, ignore_errors=True)
                break

        except Exception as e:
            print("[!] Unexpected error on listing page:", e)
            safe_quit(driver)
            shutil.rmtree(user_profile, ignore_errors=True)
            # break out to avoid infinite loops; you may want to retry instead
            break

    print("\nDone. Total rows appended:", total_saved)

# ------------- run -------------
if __name__ == "__main__":
    # decide start page: can set START_PAGE manually or rely on progress.json
    scrape_listing_pages(start_page=1)
