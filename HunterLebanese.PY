import requests
import pandas as pd
from bs4 import BeautifulSoup
from typing import Generator, Any
from datetime import datetime

# ------------------------------
# Generator to fetch job listings
# ------------------------------
def fetch_job(*, page: int, max_pages: int = 5) -> Generator[Any, None, None]:
    while True:
        if page > max_pages:
            break
        
        print("Fetching page:", page)
        url = f"https://huntinglebanese.com/en/careers/jobs/list?page={page}"
        response = requests.get(url)
        if response.status_code != 200:
            break
        
        yield response.content
        page += 1


# ------------------------------
# Function to fetch details for each job
# ------------------------------
def fetch_details(link: str) -> dict:
    local_response = requests.get(link)
    if local_response.status_code != 200:
        return {
            "description": None,
            "category": None,
            "employment_type": None,
            "job_type": None,
            "date_posted": None,
            "salary": None
        }

    soup = BeautifulSoup(local_response.content, "html.parser")

    # Remove scripts/styles
    for s in soup(["script", "style"]):
        s.decompose()

    # --------------------------
    # Extract Job Details (label-value pairs)
    # --------------------------
    job_details = {}
    for li in soup.select(".block-cv-content ul.tablecol li"):
        label = li.select_one(".label-cv")
        value = li.select_one(".value-cv")
        if label and value:
            key = label.get_text(strip=True).replace(":", "")
            val = value.get_text(strip=True)
            job_details[key] = val

    category = job_details.get("Job Category")
    employment_type = job_details.get("Employment Type")
    job_type = job_details.get("Job Duration")
    salary = job_details.get("Monthly Salary in USD")  # may be None

    # --------------------------
    # Extract Job Description
    # --------------------------
    description_block = None
    for block in soup.select(".block-cv"):
        title = block.select_one(".block-cv-title h2")
        if title and "Job Description" in title.get_text(strip=True):
            description_block = block
            break

    description = None
    if description_block:
        paragraphs = description_block.select(".block-cv-content p")
        description = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    # --------------------------
    # Extract Date Posted (first <li class="col-sm-6"> with Posted On)
    # --------------------------
    date_posted = None
    posted_li = soup.select_one('li.col-sm-6 .labelnewjob')
    if posted_li and "Posted On" in posted_li.get_text():
        date_text = posted_li.parent.get_text(strip=True).replace("Posted On:", "")
        try:
            date_obj = datetime.strptime(date_text, "%Y-%m-%d")
            date_posted = date_obj.date().isoformat()
        except ValueError:
            date_posted = None

    return {
        "description": description,
        "category": category,
        "employment_type": employment_type,
        "job_type": job_type,
        "date_posted": date_posted,
        "salary": salary,
    }

# ------------------------------
# Main Scraping Logic
# ------------------------------
jobs = []
for job in fetch_job(page=1, max_pages=11):
    job = job.decode("utf-8")
    soup = BeautifulSoup(job, "html.parser")

    for li in soup.select("li"):
        title_tag = li.select_one(".text .title a")
        country_tag = li.select_one(".text .country a")
        name_tag = li.select_one(".text .name a")

        title = title_tag.get_text(strip=True) if title_tag else None
        link = title_tag["href"] if title_tag and title_tag.has_attr("href") else None
        country = country_tag.get_text(strip=True) if country_tag else None
        name = name_tag.get_text(strip=True) if name_tag else None

        if (title is None) or (link is None) or (str(country).lower().strip() != "lebanon") or (name is None):
            continue

        full_link = f"https://huntinglebanese.com/{link}"
        details = fetch_details(full_link)

        jobs.append({
            "title": title,
            "link": full_link,
            "country": country,
            "name": name
        } | details)

# ------------------------------
# Save results
# ------------------------------
df = pd.DataFrame(jobs)
df.to_csv("hunting.csv", index=False)
print("Saved")
