import json, os, requests, hashlib, time
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "")
SEEN_FILE = "seen_posts.json"

INCLUDE_KEYWORDS = [
    "대학생","학부생","재학생","졸업예정자",
    "체육","스포츠","운동","예체능","체대",
    "체육학","스포츠학","운동학","재활",
    "스포츠의학","운동재활","운동처방",
    "스포츠마케팅","스포츠경영","스포츠산업",
    "피지컬","트레이닝","코칭",
cat > crawler.py << 'ENDOFFILE'
import json, os, requests, hashlib, time
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "")
SEEN_FILE = "seen_posts.json"

INCLUDE_KEYWORDS = [
    "대학생","학부생","재학생","졸업예정자",
    "체육","스포츠","운동","예체능","체대",
    "체육학","스포츠학","운동학","재활",
    "스포츠의학","운동재활","운동처방",
    "스포츠마케팅","스포츠경영","스포츠산업",
    "피지컬","트레이닝","코칭",
    "인턴","채용","모집","장학","대외활동","공모","서포터즈",
]
EXCLUDE_KEYWORDS = ["광고","스팸","도박","성인"]

def is_relevant(title):
    if any(kw in title for kw in EXCLUDE_KEYWORDS): return False
    return any(kw in title for kw in INCLUDE_KEYWORDS)

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f: json.dump(seen, f, ensure_ascii=False, indent=2)

def make_id(title, url=""): return hashlib.md5(f"{title}{url}".encode()).hexdigest()

def get_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    return webdriver.Chrome(options=opts)

def crawl_kusf():
    posts, driver = [], get_driver()
    try:
        driver.get("https://www.kusf.or.kr/news/news.html?board=notice&src_title=&search=%EB%AA%A8%EC%A7%91")
        time.sleep(3)
        for row in driver.find_elements(By.CSS_SELECTOR, "table tbody tr")[:30]:
            try:
                el = row.find_element(By.CSS_SELECTOR, "td a")
                cols = row.find_elements(By.TAG_NAME, "td")
                posts.append({"title": el.text.strip(), "url": el.get_attribute("href") or "", "date": cols[-1].text.strip() if cols else "", "source": "대학스포츠(KUSF)"})
            except: continue
    except Exception as e: print(f"[KUSF] {e}")
    finally: driver.quit()
    return posts

def crawl_kspo():
    posts = []
    try:
        r = requests.get("https://spobiz.kspo.or.kr/front/bbs/bbsList.do?boardId=BBS0001&topMenuSeq=2", headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.select("table tbody tr")[:30]:
            try:
                el = row.select_one("td.subject a") or row.select_one("td a")
                if not el: continue
                href = el.get("href","")
                if href and not href.startswith("http"): href = "https://spobiz.kspo.or.kr" + href
                tds = row.select("td")
                posts.append({"title": el.get_text(strip=True), "url": href, "date": tds[-1].get_text(strip=True) if tds else "", "source": "스포츠산업지원(KSPO)"})
            except: continue
    except Exception as e: print(f"[KSPO] {e}")
    return posts

def crawl_linkareer():
    posts, driver = [], get_driver()
    try:
        driver.get("https://linkareer.com/list/activity?filterBy_interestIDs=11&filterBy_interestIDs=10&filterType=INTEREST&orderBy_direction=DESC&orderBy_field=CREATED_AT&page=1")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/activity/']")))
        time.sleep(2)
        seen_hrefs = set()
        for card in driver.find_elements(By.CSS_SELECTOR, "a[href*='/activity/']")[:40]:
            try:
                href = card.get_attribute("href") or ""
                if not href or href in seen_hrefs: continue
                seen_hrefs.add(href)
                title = ""
                for el in card.find_elements(By.CSS_SELECTOR, "h3,h2,p,span"):
                    t = el.text.strip()
                    if t and len(t) > 5: title = t; break
                if title: posts.append({"title": title, "url": href, "date": "", "source": "링커리어"})
            except: continue
    except Exception as e: print(f"[링커리어] {e}")
    finally: driver.quit()
    return posts

def send_kakao(message):
    r = requests.post("https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {KAKAO_TOKEN}"},
        data={"template_object": json.dumps({"object_type":"text","text":message,"link":{"web_url":"https://linkareer.com","mobile_web_url":"https://linkareer.com"}})},
        timeout=10)
    print(f"[카카오] {r.status_code}: {r.text}")

def main():
    print(f"[{datetime.now()}] 시작")
    seen = load_seen()
    new_posts = []
    for fn in [crawl_kusf, crawl_kspo, crawl_linkareer]:
        try:
            for p in fn():
                pid = make_id(p["title"], p["url"])
                if pid not in seen:
                    if is_relevant(p["title"]): new_posts.append(p)
                    seen[pid] = {"title": p["title"], "date": str(datetime.now().date())}
        except Exception as e: print(f"[오류] {fn.__name__}: {e}")

    print(f"새 공지 {len(new_posts)}개")
    today = datetime.now().strftime("%Y년 %m월 %d일")

    if new_posts:
        msg = f"🏃 {today} 스포츠/체육 공지\n{'─'*25}\n\n"
        for p in new_posts:
            msg += f"📌 {p['title']}\n"
            msg += f"🏢 {p['source']}\n"
            if p.get('date'): msg += f"📅 {p['date']}\n"
            msg += f"🔗 {p['url']}\n\n"
        msg += f"{'─'*25}\n📊 총 {len(new_posts)}건"
    else:
        msg = f"🏃 {today} 스포츠/체육 공지\n\n오늘은 새로운 관련 공지가 없습니다 ✅"

    send_kakao(msg)
    save_seen(seen)
    print("완료!")

if __name__ == "__main__":
    main()
