import json, os, requests, hashlib, time, re
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

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

def parse_deadline(text):
    if not text: return None
    patterns = [
        r"~\s*(\d{4})[.\-](\d{2})[.\-](\d{2})",
        r"(\d{4})[.\-](\d{2})[.\-](\d{2})\s*까지",
        r"(\d{4})[.\-](\d{2})[.\-](\d{2})\s*마감",
        r"(\d{2})[.\-](\d{2})\s*까지",
    ]
    today = datetime.now()
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 3:
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    if year < 100: year += 2000
                    return datetime(year, month, day)
                elif len(groups) == 2:
                    month, day = int(groups[0]), int(groups[1])
                    return datetime(today.year, month, day)
            except:
                continue
    return None

def is_expired(post):
    today = datetime.now().date()
    deadline_date = parse_deadline(post.get("title",""))
    if not deadline_date:
        deadline_date = parse_deadline(post.get("deadline",""))
    if deadline_date:
        if deadline_date.date() < today:
            print(f"[마감됨] {post['title']}")
            return True
    return False

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f: json.dump(seen, f, ensure_ascii=False, indent=2)

def make_id(title, url=""):
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()

def get_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("user-agent=Mozilla/5.0")
    return webdriver.Chrome(options=opts)

def get_deadline_kspo(url):
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text()
        patterns = [
            r"접수\s*기간[^\d]*(\d{4}[.\-]\d{2}[.\-]\d{2})[^\d]*~[^\d]*(\d{4}[.\-]\d{2}[.\-]\d{2})",
            r"모집\s*기간[^\d]*(\d{4}[.\-]\d{2}[.\-]\d{2})[^\d]*~[^\d]*(\d{4}[.\-]\d{2}[.\-]\d{2})",
            r"신청\s*기간[^\d]*(\d{4}[.\-]\d{2}[.\-]\d{2})[^\d]*~[^\d]*(\d{4}[.\-]\d{2}[.\-]\d{2})",
            r"마감[^\d]*(\d{4}[.\-]\d{2}[.\-]\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 2:
                    return f"{match.group(1)} ~ {match.group(2)}"
                else:
                    return match.group(1)
    except:
        pass
    return ""

def crawl_kusf():
    posts = []
    driver = get_driver()
    try:
        driver.get("https://www.kusf.or.kr/news/news.html?board=notice")
        time.sleep(3)
        for row in driver.find_elements(By.CSS_SELECTOR, "table tbody tr")[:30]:
            try:
                el = row.find_element(By.CSS_SELECTOR, "td a")
                cols = row.find_elements(By.TAG_NAME, "td")
                title = el.text.strip()
                href = el.get_attribute("href") or ""
                date_text = ""
                for col in cols:
                    t = col.text.strip()
                    if re.match(r"\d{4}-\d{2}-\d{2}", t):
                        date_text = t
                        break
                if title and href and not href.startswith("javascript"):
                    posts.append({"title": title, "url": href, "date": date_text, "deadline": "", "source": "대학스포츠(KUSF)"})
            except:
                continue
    except Exception as e:
        print(f"[KUSF] {e}")
    finally:
        driver.quit()
    return posts

def crawl_kspo():
    posts = []
    try:
        url = "https://spobiz.kspo.or.kr/front/bbs/bbsList.do?boardId=BBS0001&topMenuSeq=2"
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.select("table tbody tr")[:30]:
            try:
                el = row.select_one("td.subject a") or row.select_one("td a")
                if not el: continue
                title = el.get_text(strip=True)
                href = el.get("href","")
                onclick = el.get("onclick","") or ""
                if "javascript" in href or not href:
                    match = re.search(r"fnBbsDetail\('(\d+)'", onclick)
                    if match:
                        seq = match.group(1)
                        href = f"https://spobiz.kspo.or.kr/front/bbs/bbsDetail.do?boardId=BBS0001&topMenuSeq=2&bbsSeq={seq}"
                    else:
                        href = url
                elif not href.startswith("http"):
                    href = "https://spobiz.kspo.or.kr" + href
                tds = row.select("td")
                date_text = ""
                for td in tds:
                    t = td.get_text(strip=True)
                    if re.match(r"\d{4}\.\d{2}\.\d{2}", t) or re.match(r"\d{4}-\d{2}-\d{2}", t):
                        date_text = t
                        break
                if title:
                    deadline = get_deadline_kspo(href)
                    posts.append({"title": title, "url": href, "date": date_text, "deadline": deadline, "source": "스포츠산업지원(KSPO)"})
            except:
                continue
    except Exception as e:
        print(f"[KSPO] {e}")
    return posts

def crawl_linkareer():
    posts = []
    driver = get_driver()
    try:
        driver.get("https://linkareer.com/list/activity?filterType=INTEREST&orderBy_direction=DESC&orderBy_field=CREATED_AT&page=1")
        time.sleep(5)
        seen_hrefs = set()
        for card in driver.find_elements(By.CSS_SELECTOR, "a[href*='/activity/']")[:40]:
            try:
                href = card.get_attribute("href") or ""
                if not href or href in seen_hrefs: continue
                seen_hrefs.add(href)
                title = ""
                deadline = ""
                for el in card.find_elements(By.CSS_SELECTOR, "h3,h2,p,span"):
                    t = el.text.strip()
                    if t and len(t) > 5 and not title:
                        title = t
                    if "마감" in t or "~" in t:
                        deadline = t
                if title:
                    posts.append({"title": title, "url": href, "date": "", "deadline": deadline, "source": "링커리어"})
            except:
                continue
    except Exception as e:
        print(f"[링커리어] {e}")
    finally:
        driver.quit()
    return posts

def format_post(p):
    text = f"📌 {p['title']}\n"
    text += f"🏢 {p['source']}\n"
    if p.get("date"):
        text += f"📅 게시일: {p['date']}\n"
    if p.get("deadline"):
        text += f"⏰ 모집기간: {p['deadline']}\n"
    text += f"🔗 {p['url']}\n"
    return text

def send_kakao(message, token):
    r = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {token}"},
        data={"template_object": json.dumps({
            "object_type": "text",
            "text": message,
            "link": {"web_url": "https://linkareer.com", "mobile_web_url": "https://linkareer.com"}
        })},
        timeout=10
    )
    print(f"[카카오] {r.status_code}: {r.text}")

def main():
    print(f"[{datetime.now()}] 시작")
    seen = load_seen()
    new_posts = []
    existing_posts = []

    for fn in [crawl_kusf, crawl_kspo, crawl_linkareer]:
        try:
            for p in fn():
                if is_expired(p):
                    pid = make_id(p["title"], p["url"])
                    seen[pid] = {"title": p["title"], "date": str(datetime.now().date())}
                    continue
                if not is_relevant(p["title"]):
                    continue
                pid = make_id(p["title"], p["url"])
                if pid not in seen:
                    new_posts.append(p)
                    seen[pid] = {"title": p["title"], "date": str(datetime.now().date())}
                else:
                    existing_posts.append(p)
        except Exception as e:
            print(f"[오류] {fn.__name__}: {e}")

    print(f"새 공지 {len(new_posts)}개 / 진행중 {len(existing_posts)}개")
    today = datetime.now().strftime("%Y년 %m월 %d일")

    msg = f"🏃 스포츠/체육 공지 알림\n{today}\n{'═'*22}\n\n"

    # 새로운 공지 섹션
    msg += f"🆕 새로운 공지 ({len(new_posts)}건)\n{'─'*22}\n"
    if new_posts:
        for p in new_posts:
            msg += format_post(p) + "\n"
    else:
        msg += "오늘 새로운 공지가 없습니다\n\n"

    # 진행중인 공지 섹션
    msg += f"\n📋 진행중인 공지 ({len(existing_posts)}건)\n{'─'*22}\n"
    if existing_posts:
        for p in existing_posts[:10]:  # 최대 10개
            msg += format_post(p) + "\n"
    else:
        msg += "진행중인 공지가 없습니다\n"

    msg += f"\n{'═'*22}"

    tokens = [KAKAO_TOKEN]
    extra2 = os.environ.get("KAKAO_TOKEN_2", "")
    if extra2: tokens.append(extra2)
    extra3 = os.environ.get("KAKAO_TOKEN_3", "")
    if extra3: tokens.append(extra3)

    for token in tokens:
        if token:
            send_kakao(msg, token)

    save_seen(seen)
    print("완료!")

if __name__ == "__main__":
    main()
