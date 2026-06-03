"""
부동산 규제지역(조정대상지역 등) 변경 감지 및 관리 스크립트.
MOLIT 보도자료 또는 뉴스 API를 통해 변경 사항을 감지하고 Admin Inbox에 저장합니다.
"""
import json
import os
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# 설정
MANUAL_TABLE_PATH = Path("data/area_designations/manual_table.json")
INBOX_PATH = Path("data/area_designations/detection_inbox.json")
MOLIT_NEWS_URL = "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp" # 실제 경로에 맞춰 조정 필요

def fetch_molit_news():
    """국토교통부 보도자료 목록을 가져옵니다. (Simulated)"""
    # 실제 구현 시 requests.get(MOLIT_NEWS_URL) 사용
    # 여기서는 구조적 제안을 위해 로직만 포함
    print("MOLIT 보도자료를 조회 중...")
    return [
        {"title": "서울 서초·강남·송파·용산 제외 전국 규제지역 해제", "url": "https://www.molit.go.kr/...", "date": "2024-01-05"},
        {"title": "주택시장 안정을 위한 규제지역 지정 보도자료", "url": "https://www.molit.go.kr/...", "date": "2023-11-10"}
    ]

def filter_relevant_news(news_list):
    keywords = ["조정대상지역", "투기과열지구", "투기지역", "규제지역", "해제", "지정"]
    relevant = []
    for item in news_list:
        if any(kw in item["title"] for kw in keywords):
            relevant.append(item)
    return relevant

def extract_structured_data(news_item):
    """
    LLM을 사용하여 비정형 뉴스 제목/본문에서 정형 데이터를 추출합니다.
    (실제 구현 시 src.infra.llm_fn 등을 호출)
    """
    # Simulated extraction result
    return {
        "region": "서울특별시 용산구",
        "area_type": "투기과열지구",
        "status": "해제", # 지정 | 해제
        "effective_date": "2024-01-05",
        "announcement_no": "국토교통부공고 제2024-XXX호",
        "source_url": news_item["url"],
        "detected_at": datetime.now().isoformat()
    }

def update_inbox(candidates):
    if not INBOX_PATH.exists():
        inbox = []
    else:
        inbox = json.loads(INBOX_PATH.read_text(encoding="utf-8"))
    
    # 중복 체크 (url 기준)
    existing_urls = {item["source_url"] for item in inbox}
    new_count = 0
    for cand in candidates:
        if cand["source_url"] not in existing_urls:
            inbox.append(cand)
            new_count += 1
            
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INBOX_PATH.write_text(json.dumps(inbox, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"인박스 업데이트 완료: {new_count}개 신규 감지")

def main():
    news = fetch_molit_news()
    relevant = filter_relevant_news(news)
    
    candidates = []
    for item in relevant:
        # LLM 호출을 가정
        data = extract_structured_data(item)
        candidates.append(data)
        
    update_inbox(candidates)

if __name__ == "__main__":
    main()
