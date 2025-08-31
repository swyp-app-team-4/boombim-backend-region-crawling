import os
import time
import re
import json
import pdfplumber
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import psycopg2
from datetime import datetime, date

# ======================
# DB 설정 (PostgreSQL)
# ======================
DB_CONFIG = {
    "host": "",   # ✅ NCP DB 주소
    "port": ,
    "user": "",
    "password": "",
    "dbname": ""
}

# ======================
# 다운로드 디렉토리 (Docker 내부)
# ======================
DOWNLOAD_DIR = "/app/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ======================
# Chrome 설정
# ======================
chrome_options = Options()
chrome_options.add_argument("--headless=new")   # 최신 headless 모드
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--remote-debugging-port=9222")

prefs = {"download.default_directory": DOWNLOAD_DIR}
chrome_options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)


def download_latest_pdf():
    url = "https://www.smpa.go.kr/user/nd54882.do"
    driver.get(url)
    time.sleep(2)

    first_post = driver.find_element(By.CSS_SELECTOR, "table tr td a")
    first_post.click()
    time.sleep(2)

    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(1)

    links = driver.find_elements(By.CSS_SELECTOR, "a.doc_link")
    pdf_link = None
    for l in links:
        if ".pdf" in l.text.lower():
            pdf_link = l
            break

    if not pdf_link:
        print("❌ PDF 파일 없음")
        return None

    pdf_link.click()

    for _ in range(30):
        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.lower().endswith(".pdf")]
        if files:
            break
        time.sleep(1)

    files = sorted(
        [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.lower().endswith(".pdf")],
        key=os.path.getctime,
        reverse=True
    )
    if not files:
        print("❌ 다운로드 실패")
        return None

    latest_file = files[0]
    print(f"📥 다운로드 완료: {latest_file}")
    return latest_file

def download_today_pdf():
    url = "https://www.smpa.go.kr/user/nd54882.do"
    driver.get(url)
    time.sleep(2)

    # 오늘 날짜 (YYMMDD) 문자열 만들기, 예: 250831
    today_str = datetime.today().strftime("%y%m%d")
    print(f"🔎 오늘 날짜 찾기: {today_str}")

    # 게시글 목록 가져오기
    posts = driver.find_elements(By.CSS_SELECTOR, "table tr td a")
    target_post = None
    for post in posts:
        print("DEBUG 게시글:", post.text)
        if today_str in post.text:   # 오늘 날짜 포함된 게시글 찾기
            target_post = post
            break

    if not target_post:
        print(f"❌ 오늘 날짜({today_str}) 게시글 없음")
        return None

    print(f"✅ 오늘 날짜 게시글 발견: {target_post.text}")
    target_post.click()
    time.sleep(2)

    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(1)

    # 첨부파일 중 PDF 링크 찾기
    links = driver.find_elements(By.CSS_SELECTOR, "a.doc_link")
    pdf_link = None
    for l in links:
        if ".pdf" in l.text.lower():
            pdf_link = l
            break

    if not pdf_link:
        print("❌ PDF 파일 없음")
        return None

    print(f"📎 PDF 다운로드 클릭: {pdf_link.text}")
    pdf_link.click()

    # 다운로드 대기
    for _ in range(30):
        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.lower().endswith(".pdf")]
        if files:
            break
        time.sleep(1)

    files = sorted(
        [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.lower().endswith(".pdf")],
        key=os.path.getctime,
        reverse=True
    )
    if not files:
        print("❌ 다운로드 실패")
        return None

    latest_file = files[0]
    print(f"📥 다운로드 완료: {latest_file}")
    return latest_file

def parse_meeting_table_pdf(file_path):
    meetings = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            for row in table[1:]:
                if not row or len(row) < 3:
                    continue

                time_text = row[0] or ""
                location_text = row[1] or ""
                people_text = row[2] or ""

                area_match = re.search(r"<(.*?)>", location_text)
                if area_match:
                    area = area_match.group(1).strip()
                    area = re.sub(r"\s*등$", "", area).strip()
                else:
                    area = ""

                pos_name = re.sub(r"<.*?>", "", location_text).strip()

                people_match = re.search(r"(\d{1,3}(?:,\d{3})*|\d+)", people_text)
                reported_people = int(people_match.group(1).replace(",", "")) if people_match else None

                meetings.append({
                    "time": time_text.strip(),
                    "location": pos_name,
                    "area": area,
                    "reported_people": reported_people
                })

    return meetings


def save_to_db(meetings):
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    sql = """
    INSERT INTO region (region_date, start_time, end_time, pos_name, area, people_cnt)
    VALUES (%s, %s, %s, %s, %s, %s)
    """

    today = date.today()

    for m in meetings:
        try:
            start_str, end_str = m["time"].split("~")
        except ValueError:
            print(f"⚠️ 시간 파싱 실패: {m['time']}")
            continue

        start_time = datetime.strptime(f"{today} {start_str.strip()}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{today} {end_str.strip()}", "%Y-%m-%d %H:%M")

        cursor.execute(sql, (
            today,
            start_time,
            end_time,
            m["location"],
            m["area"],
            m["reported_people"]
        ))

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ DB 저장 완료")


def main():
    file_path = download_today_pdf()
    if not file_path:
        return
    result = parse_meeting_table_pdf(file_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    save_to_db(result)


if __name__ == "__main__":
    main()
    driver.quit()
