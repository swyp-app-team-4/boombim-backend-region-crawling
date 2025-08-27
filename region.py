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
import psycopg2   # ✅ PostgreSQL 드라이버
from datetime import datetime, date

# ======================
# DB 설정 (PostgreSQL)
# ======================
DB_CONFIG = {
    "host": "localhost",
    "port": "ㅇ",
    "user": "",
    "password": "", # 베낄테면 베껴라!!
    "dbname": ""   # PostgreSQL은 database 대신 dbname
}

# ======================
# Chrome 설정
# ======================
chrome_options = Options()
# chrome_options.add_argument("--headless")  # 필요 시 주석 해제
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

DOWNLOAD_DIR = r"C:\Users\chltm\Downloads"  # 네 PC 다운로드 폴더


def download_latest_pdf():
    """게시판에서 최신 글 첨부파일 (PDF만 Selenium 클릭으로 다운로드)"""
    url = "https://www.smpa.go.kr/user/nd54882.do"
    driver.get(url)
    time.sleep(2)

    # 최신 글 클릭
    first_post = driver.find_element(By.CSS_SELECTOR, "table tr td a")
    first_post.click()
    time.sleep(2)

    # 👉 새 탭 전환
    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(1)

    # 첨부파일 찾기
    links = driver.find_elements(By.CSS_SELECTOR, "a.doc_link")
    pdf_link = None
    for l in links:
        if ".pdf" in l.text.lower():
            pdf_link = l
            break

    if not pdf_link:
        print("❌ PDF 파일 없음")
        return None

    # 🔥 실제 클릭으로 다운로드 실행
    pdf_link.click()
    time.sleep(5)  # 다운로드 기다리기

    # 방금 다운로드된 최신 PDF 찾기
    files = sorted(
        [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.lower().endswith(".pdf")],
        key=os.path.getctime,
        reverse=True
    )
    latest_file = files[0]
    print(f"📥 다운로드 완료: {latest_file}")
    return latest_file


def parse_meeting_table_pdf(file_path):
    """PDF 테이블 → JSON 파싱"""
    meetings = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            # 첫 행은 헤더니까 스킵
            for row in table[1:]:
                if not row or len(row) < 3:
                    continue

                time_text = row[0] or ""
                location_text = row[1] or ""
                people_text = row[2] or ""

                # 괄호 안 내용 제거
                location_text = re.sub(r"<.*?>", "", location_text).strip()

                # 인원 숫자만 추출
                people_match = re.search(r"(\d{1,3}(?:,\d{3})*|\d+)", people_text)
                reported_people = int(people_match.group(1).replace(",", "")) if people_match else None

                meetings.append({
                    "time": time_text.strip(),
                    "location": location_text,
                    "reported_people": reported_people
                })

    return meetings


def save_to_db(meetings):
    """PostgreSQL DB 저장"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    sql = """
    INSERT INTO region (region_date, start_time, end_time, pos_name, people_cnt)
    VALUES (%s, %s, %s, %s, %s)
    """

    today = date.today()

    for m in meetings:
        # "09:00~12:00" → 시작/끝 시간
        try:
            start_str, end_str = m["time"].split("~")
        except ValueError:
            print(f"⚠️ 시간 파싱 실패: {m['time']}")
            continue

        start_time = datetime.strptime(f"{today} {start_str.strip()}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{today} {end_str.strip()}", "%Y-%m-%d %H:%M")

        cursor.execute(sql, (
            today,                  # region_date
            start_time,             # start_time
            end_time,               # end_time
            m["location"],          # pos_name
            m["reported_people"]    # people_cnt
        ))

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ DB 저장 완료")


def main():
    file_path = download_latest_pdf()
    if not file_path:
        return

    result = parse_meeting_table_pdf(file_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    save_to_db(result)


if __name__ == "__main__":
    main()
    driver.quit()
