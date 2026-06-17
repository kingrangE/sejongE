"""연구실/교수 파서 — 인공지능융합대학(MVP).

학과 페이지의 교수소개는 JS로 그려지지만, 데이터는 공개 API로 받을 수 있다(Playwright 불필요):
  POST /professor/getProfessorListKor.do  {menuCd, siteId, orderOption, deptNo}
응답 items[]에는 교수명·연구분야(resFld)·이메일·연구실 홈페이지(homepage1/2)가 들어있다.
학과 페이지에서 deptNo/menuCd를 추출해 학과별로 호출한다.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from sejong_rag.models import LabDoc
from sejong_rag.normalize.dedup import content_hash, stable_id

BASE_URL = "https://www.sejong.ac.kr"
COLLEGE = "인공지능융합대학"
PROFESSOR_API = f"{BASE_URL}/professor/getProfessorListKor.do"

# 인공지능융합대학 학과 slug (academics.do 기준, MVP)
AI_CONVERGENCE_SLUGS = [
    "electronics-and-information-engineering",  # AI융합전자공학과
    "computer-science-and-engineering",         # 컴퓨터공학과
    "computer-and-information-security",         # 정보보호학과
    "quantumai",                                # 양자지능정보학과
    "school-of-creative-studies",               # 창의소프트학부
    "intelligent-internet-of-things",           # 지능IoT학과
    "department-of-cyber-defense",              # 사이버국방학과
    "defenseai",                                # 국방AI로봇융합공학과
    "data-science",                             # 인공지능데이터사이언스학과
    "artificial-intelligence-and-robotics",     # AI로봇학과
    "intelligence-and-information-convergence",  # 지능정보융합학과
    "software",                                 # 콘텐츠소프트웨어학과
]

_MENUCD_RE = re.compile(r"""menuCd["']?\s*[:=]\s*["']?(\d+)""")
# 연구분야 구분자: 콤마/슬래시/가운뎃점/세미콜론/줄바꿈
_SPLIT_RE = re.compile(r"[,/·∙ㆍ;\n\r]+")
_BULLET_RE = re.compile(r"^[•▪◦·\-\s]+")


def dept_url(slug: str) -> str:
    return f"{BASE_URL}/kor/college/{slug}.do"


def extract_api_params(html: str) -> dict | None:
    """학과 페이지에서 교수 API 호출 파라미터 추출. 필수값 없으면 None."""
    soup = BeautifulSoup(html, "lxml")

    def val(sel: str, default: str = "") -> str:
        el = soup.select_one(sel)
        return (el.get("value") if el else None) or default

    dept_no = val("#paramsDeptNo")
    if not dept_no:
        return None
    m = _MENUCD_RE.search(html)
    return {
        "deptNo": dept_no,
        "menuCd": m.group(1) if m else "",
        "siteId": "kor",
        "orderOption": val("#orderOption", "D"),
        "selectOption": val("#selectOption", ""),
    }


def _areas(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    out = []
    for part in _SPLIT_RE.split(text):
        cleaned = _BULLET_RE.sub("", part).strip()
        if cleaned:
            out.append(cleaned)
    return out


def parse_professors(items: list[dict], *, source_url: str, crawled_at: str) -> list[LabDoc]:
    docs: list[LabDoc] = []
    for it in items:
        if it.get("showYn") == "N":
            continue
        name = (it.get("korNm") or "").strip()
        if not name:
            continue
        dept = (it.get("deptInfo") or it.get("majorKo") or "").strip()
        areas = _areas(it.get("resFld") or "")
        homepage = (it.get("homepage1") or it.get("homepage2") or "").strip() or None
        email = (it.get("email") or "").strip()
        degree = (it.get("finalDegree") or "").strip()

        parts = [f"{name} 교수 ({dept})"]
        if areas:
            parts.append("연구분야: " + ", ".join(areas))
        if degree:
            parts.append(degree)
        if homepage:
            parts.append(f"연구실 홈페이지: {homepage}")
        if email:
            parts.append(f"이메일: {email}")
        embedding_text = "\n".join(parts)

        key = str(it.get("proNo") or it.get("empNo") or name)
        docs.append(
            LabDoc(
                id=stable_id(source_url, key=key),
                source_url=source_url,
                source_site="labs",
                crawled_at=crawled_at,
                content_hash=content_hash(f"{name}|{dept}|{it.get('resFld')}|{homepage}|{email}"),
                text=embedding_text,
                embedding_text=embedding_text,
                lab_name="",
                professor_name=name,
                department=dept,
                college=COLLEGE,
                research_areas=areas,
                keywords=areas,
                homepage_url=homepage,
            )
        )
    return docs


def crawl(fetcher, crawled_at: str, slugs: list[str] | None = None) -> list[LabDoc]:
    """학과별로 페이지→API를 호출해 교수/연구실 문서를 모은다."""
    slugs = slugs or AI_CONVERGENCE_SLUGS
    out: list[LabDoc] = []
    for slug in slugs:
        url = dept_url(slug)
        try:
            html = fetcher.fetch(url, site="labs", cache_key=f"dept_{slug}")
            params = extract_api_params(html)
            if not params:
                continue
            body = fetcher.post(PROFESSOR_API, params, site="labs", referer=url)
            items = json.loads(body).get("items") or []
            out.extend(parse_professors(items, source_url=url, crawled_at=crawled_at))
        except Exception:
            # 한 학과 실패가 전체를 막지 않도록(원칙: 장애 격리)
            continue
    return out
