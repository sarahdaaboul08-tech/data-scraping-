import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import random
import os

# -------------------------
# Selenium setup
# -------------------------
options = Options()
options.headless = False  # Set True for headless mode
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 20)

BASE_URL = "https://huntinglebanese.com"
csv_file = "huntinglebanese_jobs.csv"

# Loop through pages 2 to 12
for page_num in range(3, 13):
    print(f"Processing page {page_num}...")
    page_url = BASE_URL + f"/en/careers/jobs/search-form-home?keyword=&country=&page={page_num}"
    driver.get(page_url)
    time.sleep(5)  # Wait for initial page load

    # Scroll to load all job links
    for _ in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2, 4))

    # Wait for job links to appear
    try:
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/en/careers/jobs/show/']")))
    except:
        print(f"No jobs found on page {page_num}")
        continue

    # Collect all job URLs (remove duplicates)
    job_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/en/careers/jobs/show/']")
    job_urls = list(dict.fromkeys([link.get_attribute("href") for link in job_links]))
    print(f"Found {len(job_urls)} jobs on page {page_num}")

    page_jobs = []  # store jobs for current page

    # Visit each job page and scrape details
    for idx, job_url in enumerate(job_urls, 1):
        print(f"Scraping job {idx}/{len(job_urls)}: {job_url}")
        driver.get(job_url)
        time.sleep(2)  # wait 2 seconds for page to load

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(1)

        try:
            title = driver.find_element(By.CSS_SELECTOR, "div.block-job-right h1").text.strip()
        except:
            title = "N/A"

        try:
            company = driver.find_element(By.CSS_SELECTOR, "div.block-job-right h3").text.strip()
        except:
            company = "N/A"

        try:
            date_posted = "N/A"
            posted_elements = driver.find_elements(By.CSS_SELECTOR, "div.block-job-right li.col-sm-6")
            for el in posted_elements:
                label = el.find_element(By.CSS_SELECTOR, "span.labelnewjob").text.strip()
                if "Posted On" in label:
                    date_posted = el.text.replace(label, "").strip()
                    break
        except:
            date_posted = "N/A"

        try:
            description = ""
            blocks = driver.find_elements(By.CSS_SELECTOR, "div.block-cv")
            for block in blocks:
                try:
                    h2_text = block.find_element(By.CSS_SELECTOR, "div.block-cv-title > h2").text.strip()
                    if "Job Description" in h2_text:
                        description = block.find_element(By.CSS_SELECTOR, "div.block-cv-content").text.strip()
                        break
                except:
                    continue
            if not description:
                description = "N/A"
        except:
            description = "N/A"

        try:
            salary = "N/A"
            salary_blocks = driver.find_elements(By.CSS_SELECTOR, "div.block-cv")
            for block in salary_blocks:
                try:
                    labels = block.find_elements(By.CSS_SELECTOR, "span.label-cv")
                    values = block.find_elements(By.CSS_SELECTOR, "span.value-cv")
                    for lbl, val in zip(labels, values):
                        if "Monthly Salary" in lbl.text:
                            salary = val.text.strip()
                            break
                except:
                    continue
        except:
            salary = "N/A"

        page_jobs.append({
            "Title": title,
            "Company": company,
            "Date Posted": date_posted,
            "Salary": salary,
            "Description": description,
            "URL": job_url
        })

        time.sleep(random.uniform(1, 2))  # polite delay

    # Save current page jobs to CSV
    df = pd.DataFrame(page_jobs)
    if os.path.exists(csv_file):
        df.to_csv(csv_file, mode='a', header=False, index=False)
    else:
        df.to_csv(csv_file, index=False)

driver.quit()
print("Scraping complete!")
