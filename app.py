import os
import io
import datetime
import pandas as pd
import streamlit as st
from PIL import Image

# -------------------------------------------------------------
# 1. 페이지 기본 설정 및 스타일
# -------------------------------------------------------------
st.set_page_config(
    page_title="만족도 조사 집계 시스템",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS (카드 스타일, 깔끔한 UI)
st.markdown("""
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-box {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 12px;
        border-left: 4px solid #3B82F6;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .score-badge {
        font-size: 1.1rem;
        font-weight: 600;
        color: #2563EB;
    }
</style>
""", unsafe_allow_html=True)

CSV_FILE = "survey_data.csv"

SCORE_COLUMNS = [
    "소통_설명및협의",
    "소통_공사기간준수",
    "품질_계약내용실행",
    "품질_설계개선",
    "안전_안전사고예방",
    "기타_민원관리",
    "종합_전반적만족도"
]

ALL_COLUMNS = [
    "등록일시",
    "발주사",
    "공사명",
    "계약기간",
    "담당자소속",
    "담당자이름",
    *SCORE_COLUMNS,
    "합계",
    "평균"
]

# -------------------------------------------------------------
# 2. 데이터 불러오기 및 저장 함수 (구글 시트 & 로컬 CSV 하이브리드)
# -------------------------------------------------------------
def is_gsheets_enabled() -> bool:
    """Streamlit Secrets에 gsheets 설정이 존재하는지 확인합니다."""
    try:
        if hasattr(st, "secrets") and "connections" in st.secrets:
            return "gsheets" in st.secrets["connections"]
        return False
    except BaseException:
        return False

def get_gsheets_connection():
    """구글 시트 커넥션 인스턴스를 반환합니다."""
    try:
        from streamlit_gsheets import GSheetsConnection
        return st.connection("gsheets", type=GSheetsConnection)
    except BaseException:
        return None

def load_survey_data() -> pd.DataFrame:
    """구글 스프레드시트 또는 로컬 CSV 파일에서 누적된 설문 데이터를 불러옵니다."""
    # 1. 구글 스프레드시트 연동 활성화 시 우선 로드
    if is_gsheets_enabled():
        try:
            conn = get_gsheets_connection()
            if conn:
                df = conn.read(ttl=3) # 3초 캐시로 빠른 실시간 반응
                if df is not None and not df.empty:
                    # 필수 컬럼 보정
                    for col in ALL_COLUMNS:
                        if col not in df.columns:
                            df[col] = None
                    df = df.dropna(subset=["발주사", "공사명"], how="all")
                    return df[ALL_COLUMNS].reset_index(drop=True)
        except BaseException as e:
            st.warning(f"구글 시트 읽기 실패 (로컬 CSV로 대체합니다): {e}")

    # 2. 로컬 CSV 파일 로드 (기본)
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
            for col in ALL_COLUMNS:
                if col not in df.columns:
                    df[col] = None
            return df[ALL_COLUMNS]
        except Exception as e:
            st.error(f"데이터 파일을 읽는 중 오류가 발생했습니다: {e}")
            return pd.DataFrame(columns=ALL_COLUMNS)
    else:
        return pd.DataFrame(columns=ALL_COLUMNS)

def save_survey_entry(entry_dict: dict) -> bool:
    """구글 시트 및 로컬 CSV에 설문 데이터를 누적 저장합니다."""
    df_new = pd.DataFrame([entry_dict])
    csv_saved = False

    # 1. 로컬 CSV 파일에 백업 저장
    try:
        if not os.path.exists(CSV_FILE):
            df_new.to_csv(CSV_FILE, mode="w", index=False, encoding="utf-8-sig")
        else:
            df_new.to_csv(CSV_FILE, mode="a", index=False, header=False, encoding="utf-8-sig")
        csv_saved = True
    except PermissionError:
        st.error("⚠️ 'survey_data.csv' 파일이 엑셀 등 다른 프로그램에서 열려 있습니다. 파일을 닫은 후 다시 저장해 주세요.")
        return False
    except Exception as e:
        st.warning(f"로컬 파일 저장 알림: {e}")

    # 2. 구글 스프레드시트 연동 시 클라우드 시트에 동기화
    if is_gsheets_enabled():
        try:
            conn = get_gsheets_connection()
            if conn:
                current_df = conn.read(ttl=0)
                if current_df is None or current_df.empty:
                    updated_df = df_new[ALL_COLUMNS]
                else:
                    updated_df = pd.concat([current_df, df_new], ignore_index=True)[ALL_COLUMNS]
                conn.update(data=updated_df)
                return True
        except Exception as e:
            st.error(f"구글 시트 저장 실패: {e}")
            return csv_saved

    return csv_saved

def delete_survey_entry(row_index: int) -> bool:
    """구글 시트 및 로컬 CSV에서 지정된 인덱스의 데이터를 삭제합니다."""
    # 1. 로컬 CSV에서 삭제
    try:
        if os.path.exists(CSV_FILE):
            df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
            if 0 <= row_index < len(df):
                df = df.drop(index=row_index).reset_index(drop=True)
                df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    except Exception:
        pass

    # 2. 구글 시트에서 삭제
    if is_gsheets_enabled():
        try:
            conn = get_gsheets_connection()
            if conn:
                df = conn.read(ttl=0)
                if df is not None and 0 <= row_index < len(df):
                    df = df.drop(index=row_index).reset_index(drop=True)[ALL_COLUMNS]
                    conn.update(data=df)
                    return True
        except Exception as e:
            st.error(f"구글 시트 삭제 오류: {e}")
            return False

    return True

# -------------------------------------------------------------
# 3. PDF / 이미지 뷰어 헬퍼 함수
# -------------------------------------------------------------
def get_pdf_page_images(pdf_bytes):
    """PyMuPDF(fitz)를 이용해 PDF 각 페이지를 PIL 이미지 리스트로 변환합니다."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_images = []
        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            # 해상도 150 DPI 정도로 선명하게 렌더링
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            page_images.append(img)
        return page_images
    except Exception as e:
        st.warning(f"PDF 미리보기 변환 중 알림: {e}")
        return None

def extract_text_from_file(uploaded_file) -> str:
    """PDF 또는 이미지 파일에서 텍스트를 추출합니다 (디지털 텍스트 + Windows 로컬 OCR)."""
    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        uploaded_file.seek(0)
        file_ext = uploaded_file.name.split(".")[-1].lower()
        full_text = ""

        if file_ext == "pdf":
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                text = page.get_text()
                if text and text.strip():
                    full_text += text + "\n"

            # 디지털 텍스트가 없는 스캔본 PDF인 경우 Windows 로컬 OCR 수행
            if not full_text.strip():
                try:
                    import winocr
                    for page_idx in range(len(doc)):
                        page = doc.load_page(page_idx)
                        pix = page.get_pixmap(dpi=200)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        res = winocr.recognize_pil_sync(img, lang="ko")
                        full_text += res.get("text", "") + "\n"
                except Exception:
                    pass

        elif file_ext in ["png", "jpg", "jpeg"]:
            try:
                import winocr
                img = Image.open(io.BytesIO(file_bytes))
                res = winocr.recognize_pil_sync(img, lang="ko")
                full_text = res.get("text", "")
            except Exception:
                pass

        return full_text.strip()
    except Exception as ex:
        st.error(f"문서 읽기 중 오류 발생: {ex}")
        return ""

def parse_survey_text(text: str) -> dict:
    """추출된 텍스트에서 발주사(발주처), 공사명, 기간, 담당자 소속(소속), 담당자 이름(작성자), 만족도 점수를 지능적으로 추출합니다."""
    import re
    result = {
        "발주사": "",
        "공사명": "",
        "계약기간": "",
        "담당자소속": "",
        "담당자이름": "",
        "소통_설명및협의": 5,
        "소통_공사기간준수": 5,
        "품질_계약내용실행": 5,
        "품질_설계개선": 5,
        "안전_안전사고예방": 5,
        "기타_민원관리": 5,
        "종합_전반적만족도": 5
    }

    if not text:
        return result

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 1. 기본 정보 정밀 파싱 (발주처->발주사, 소속->담당자소속, 작성자->담당자이름)
    keywords = [
        ("발주사", ["발주처", "발주사", "고객사", "원청사", "업체명", "회사명"]),
        ("공사명", ["공사명", "사업명", "프로젝트명", "현장명", "건명", "계약건명"]),
        ("계약기간", ["계약기간", "공사기간", "공기", "기간"]),
        ("담당자소속", ["소속", "담당자소속", "담당자 소속", "부서", "담당부서"]),
        ("담당자이름", ["작성자", "담당자이름", "담당자 이름", "담당자명", "성명", "성함", "평가자"])
    ]

    # 각 줄에서 키워드 위치를 분석하여 같은 줄에 여러 키워드가 있는 표 형태도 정확히 분리 추출
    for i, line in enumerate(lines):
        found_tokens = []
        for field_name, kw_list in keywords:
            for kw in kw_list:
                pattern = r'(?<![가-힣a-zA-Z0-9])' + re.escape(kw) + r'(?![가-힣a-zA-Z0-9])'
                for match in re.finditer(pattern, line):
                    found_tokens.append((match.start(), match.end(), field_name, kw))
                    break # 해당 필드의 첫 매칭만 등록

        found_tokens.sort(key=lambda x: x[0])

        if found_tokens:
            for idx, (start, end, field_name, kw) in enumerate(found_tokens):
                val_start = end
                val_end = found_tokens[idx + 1][0] if idx + 1 < len(found_tokens) else len(line)
                raw_val = line[val_start:val_end].strip()
                clean_val = re.sub(r'^[:：\-\s|]+', '', raw_val).strip()
                clean_val = re.sub(r'[:：,;|]+$', '', clean_val).strip()

                # 현재 줄에 값이 없고 키워드만 단독으로 있는 경우 다음 줄 확인 (위아래 셀로 분리된 표 형태)
                if not clean_val and len(found_tokens) == 1 and i + 1 < len(lines):
                    next_line = lines[i + 1]
                    is_another_kw = False
                    for _, kw_list2 in keywords:
                        for kw2 in kw_list2:
                            if next_line.startswith(kw2):
                                is_another_kw = True
                                break
                    if not is_another_kw:
                        clean_val = re.sub(r'^[:：\-\s|]+', '', next_line).strip()
                        clean_val = re.sub(r'[:：,;|]+$', '', clean_val).strip()

                if clean_val and not result[field_name]:
                    result[field_name] = clean_val

    # 2. 정규식 패턴 보조 탐색 (누락된 항목이 있을 때 2차 보완)
    fallback_patterns = {
        "발주사": [r"(?:발주처|발주사|고객사)\s*[:：\-]?\s*([^\n\r,]+)"],
        "공사명": [r"(?:공사명|사업명|현장명)\s*[:：\-]?\s*([^\n\r,]+)"],
        "계약기간": [r"(?:계약기간|공사기간|기간)\s*[:：\-]?\s*([0-9]{4}[.\-/년\s0-9~동일]+)"],
        "담당자소속": [r"(?:소속|부서|담당부서)\s*[:：\-]?\s*([^\n\r,]+)"],
        "담당자이름": [r"(?:작성자|성명|담당자명|성함)\s*[:：\-]?\s*([^\n\r,]+)"]
    }
    for field, p_list in fallback_patterns.items():
        if not result[field]:
            for p in p_list:
                m = re.search(p, text)
                if m:
                    val = re.sub(r'^[:：\-\s|]+', '', m.group(1)).strip()
                    val = re.sub(r'[:：,;|]+$', '', val).strip()
                    if val:
                        result[field] = val
                        break

    # 3. 7개 평가 항목 점수 인식 (키워드 탐색 및 1~5점 검출)
    score_keywords = {
        "소통_설명및협의": ["설명", "협의", "설명및협의"],
        "소통_공사기간준수": ["기간준수", "공사기간", "공기", "납기", "일정"],
        "품질_계약내용실행": ["계약내용", "실행", "품질"],
        "품질_설계개선": ["설계개선", "설계", "개선"],
        "안전_안전사고예방": ["안전", "사고예방", "재해"],
        "기타_민원관리": ["민원", "소음", "분진"],
        "종합_전반적만족도": ["종합", "전반", "만족도"]
    }

    for line in lines:
        for score_key, kw_list in score_keywords.items():
            if any(kw in line for kw in kw_list):
                digits = re.findall(r"\b([1-5])\b", line)
                if "①" in line or "1점" in line: digits = ["1"]
                elif "②" in line or "2점" in line: digits = ["2"]
                elif "③" in line or "3점" in line: digits = ["3"]
                elif "④" in line or "4점" in line: digits = ["4"]
                elif "⑤" in line or "5점" in line: digits = ["5"]

                if digits:
                    try:
                        result[score_key] = int(digits[-1])
                    except Exception:
                        pass

    return result

# -------------------------------------------------------------
# 4. 좌측 사이드바: 파일 업로드 & 입력 폼
# -------------------------------------------------------------
with st.sidebar:
    st.header("📝 설문지 입력 & 파일 확인")
    st.caption("지류 설문지 스캔본/사진을 올리고 바로 입력하세요.")

    # 1) 파일 업로더
    uploaded_file = st.file_uploader(
        "지류 설문지 첨부 (PNG, JPG, PDF)",
        type=["png", "jpg", "jpeg", "pdf"],
        help="업로드한 설문지 문서를 바로 아래에서 확인하면서 점수를 입력할 수 있습니다."
    )

    # 2) 파일 미리보기 (PDF 또는 이미지)
    if uploaded_file is not None:
        with st.expander("📄 첨부된 설문지 미리보기", expanded=True):
            file_ext = uploaded_file.name.split(".")[-1].lower()
            if file_ext in ["png", "jpg", "jpeg"]:
                try:
                    img = Image.open(uploaded_file)
                    st.image(img, caption=f"첨부: {uploaded_file.name}", use_container_width=True)
                except Exception as ex:
                    st.error(f"이미지를 불러올 수 없습니다: {ex}")
            elif file_ext == "pdf":
                pdf_bytes = uploaded_file.read()
                pdf_images = get_pdf_page_images(pdf_bytes)
                if pdf_images:
                    if len(pdf_images) == 1:
                        st.image(pdf_images[0], caption="설문지 1페이지", use_container_width=True)
                    else:
                        page_choice = st.selectbox(
                            "확인할 페이지 선택",
                            options=range(1, len(pdf_images) + 1),
                            format_func=lambda x: f"{x} / {len(pdf_images)} 페이지"
                        )
                        st.image(pdf_images[page_choice - 1], caption=f"{page_choice}페이지", use_container_width=True)
                else:
                    st.info("PDF 파일이 업로드되었습니다. (미리보기를 지원하지 않는 포맷이거나 텍스트 문서입니다)")

    st.markdown("---")
    st.subheader("⚡ 설문지 자동 인식 & 반영")
    st.caption("업로드한 설문지 문서를 시스템이 읽어서 아래 폼에 자동으로 채웁니다.")

    if uploaded_file is not None:
        col_ocr_act, col_ocr_reset = st.columns([3, 1])
        with col_ocr_act:
            btn_ocr = st.button("🔍 문서 내용 읽어서 폼에 반영하기", type="primary", use_container_width=True)
        with col_ocr_reset:
            if st.button("초기화", use_container_width=True, help="자동 입력된 내용을 비웁니다"):
                for k in ["auto_client", "auto_project", "auto_period", "auto_dept", "auto_name", "ocr_text", "auto_scores"]:
                    st.session_state.pop(k, None)
                st.rerun()

        if btn_ocr:
            with st.spinner("📄 문서에서 텍스트와 설문 항목을 읽어오는 중입니다..."):
                extracted_text = extract_text_from_file(uploaded_file)
                if extracted_text:
                    parsed = parse_survey_text(extracted_text)
                    st.session_state["auto_client"] = parsed.get("발주사", "")
                    st.session_state["auto_project"] = parsed.get("공사명", "")
                    st.session_state["auto_period"] = parsed.get("계약기간", "")
                    st.session_state["auto_dept"] = parsed.get("담당자소속", "")
                    st.session_state["auto_name"] = parsed.get("담당자이름", "")
                    st.session_state["auto_scores"] = {
                        col: parsed.get(col, 5) for col in SCORE_COLUMNS
                    }
                    st.session_state["ocr_text"] = extracted_text
                    st.success("✅ 문서 내용을 성공적으로 읽었습니다! 아래 입력 폼을 확인해 주세요.")
                    st.rerun()
                else:
                    st.warning("⚠️ 문서에서 텍스트를 감지하지 못했습니다. 직접 입력해 주세요.")

        if st.session_state.get("ocr_text"):
            with st.expander("📝 문서에서 추출된 원본 텍스트 보기"):
                st.text_area("추출 텍스트", st.session_state["ocr_text"], height=130, disabled=True)
    else:
        st.info("💡 파일을 위에 첨부하시면 [문서 내용 읽어서 폼에 반영하기] 버튼이 활성화됩니다.")

    st.markdown("---")
    st.subheader("📋 설문 내용 확인 및 표에 반영")

    default_client = st.session_state.get("auto_client", "")
    default_project = st.session_state.get("auto_project", "")
    default_period = st.session_state.get("auto_period", "")
    default_dept = st.session_state.get("auto_dept", "")
    default_name = st.session_state.get("auto_name", "")
    saved_scores = st.session_state.get("auto_scores", {})

    # 3) 입력 폼 (st.form)
    with st.form(key="survey_input_form", clear_on_submit=False):
        st.markdown("**[1] 공사 및 담당자 정보**")
        client = st.text_input("발주사 (발주처) *", value=default_client, placeholder="예: (주)한국건설").strip()
        project_name = st.text_input("공사명 *", value=default_project, placeholder="예: 신축 물류센터 전기공사").strip()
        period = st.text_input("계약기간 (공사기간)", value=default_period, placeholder="예: 2026.01.01 ~ 2026.06.30").strip()
        dept = st.text_input("담당자 소속 (소속)", value=default_dept, placeholder="예: 시설관리팀").strip()
        manager_name = st.text_input("담당자 이름 (작성자)", value=default_name, placeholder="예: 홍길동 팀장").strip()

        st.markdown("---")
        st.markdown("**[2] 만족도 평가 점수 (각 1~5점)**")
        st.caption("1점: 매우불만 | 3점: 보통 | 5점: 매우만족")

        # 7개 평가 점수 입력 (문서 인식 점수 자동 반영)
        score_communication_1 = st.radio(
            "1. [소통] 설명 및 협의",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("소통_설명및협의", 5) - 1)),
            horizontal=True
        )
        score_communication_2 = st.radio(
            "2. [소통] 공사기간 준수",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("소통_공사기간준수", 5) - 1)),
            horizontal=True
        )
        score_quality_1 = st.radio(
            "3. [품질] 계약내용 실행",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("품질_계약내용실행", 5) - 1)),
            horizontal=True
        )
        score_quality_2 = st.radio(
            "4. [품질] 설계 개선",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("품질_설계개선", 5) - 1)),
            horizontal=True
        )
        score_safety = st.radio(
            "5. [안전] 안전사고 예방",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("안전_안전사고예방", 5) - 1)),
            horizontal=True
        )
        score_etc = st.radio(
            "6. [기타] 민원 관리",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("기타_민원관리", 5) - 1)),
            horizontal=True
        )
        score_overall = st.radio(
            "7. [종합] 전반적 만족도",
            options=[1, 2, 3, 4, 5],
            index=max(0, min(4, saved_scores.get("종합_전반적만족도", 5) - 1)),
            horizontal=True
        )

        st.markdown("---")
        submitted = st.form_submit_button("💾 확인 후 표에 저장(반영)하기", use_container_width=True, type="primary")

        if submitted:
            # 필수 항목 검증
            if not client or not project_name:
                st.error("⚠️ '발주사'와 '공사명'은 필수 입력 항목입니다.")
            else:
                # 점수 리스트
                scores = [
                    score_communication_1,
                    score_communication_2,
                    score_quality_1,
                    score_quality_2,
                    score_safety,
                    score_etc,
                    score_overall
                ]

                # 자동 계산: 합계 및 평균 (소수점 첫째 자리)
                total_sum = sum(scores)
                avg_score = round(total_sum / len(scores), 1)
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                new_data = {
                    "등록일시": now_str,
                    "발주사": client,
                    "공사명": project_name,
                    "계약기간": period,
                    "담당자소속": dept,
                    "담당자이름": manager_name,
                    "소통_설명및협의": score_communication_1,
                    "소통_공사기간준수": score_communication_2,
                    "품질_계약내용실행": score_quality_1,
                    "품질_설계개선": score_quality_2,
                    "안전_안전사고예방": score_safety,
                    "기타_민원관리": score_etc,
                    "종합_전반적만족도": score_overall,
                    "합계": total_sum,
                    "평균": avg_score
                }

                if save_survey_entry(new_data):
                    for k in ["auto_client", "auto_project", "auto_period", "auto_dept", "auto_name", "ocr_text", "auto_scores"]:
                        st.session_state.pop(k, None)
                    st.success(f"✅ 표에 반영 완료! (합계: {total_sum}점, 평균: {avg_score}점)")
                    st.rerun()

# -------------------------------------------------------------
# 5. 메인 화면: 실시간 누적 집계표 및 요약 통계
# -------------------------------------------------------------
st.markdown('<div class="main-title">📊 지류 만족도 조사 실시간 집계 대시보드</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">종이로 수합된 설문지를 등록하고 실시간 누적 결과 및 요약 통계를 모니터링합니다.</div>', unsafe_allow_html=True)

if is_gsheets_enabled():
    st.markdown('<div style="margin-bottom: 12px;"><span style="background-color:#DCFCE7; color:#166534; padding:4px 12px; border-radius:12px; font-size:0.85rem; font-weight:600;">🟢 구글 스프레드시트 실시간 클라우드 연동 중</span></div>', unsafe_allow_html=True)
else:
    st.markdown('<div style="margin-bottom: 12px;"><span style="background-color:#F1F5F9; color:#475569; padding:4px 12px; border-radius:12px; font-size:0.85rem; font-weight:600;">💾 로컬 CSV 저장 모드 (구글 시트 설정 시 자동 전환)</span></div>', unsafe_allow_html=True)

# 최신 데이터 불러오기
df_data = load_survey_data()
total_count = len(df_data)

# 상단 KPI 지표 카드
col1, col2, col3, col4 = st.columns(4)

if total_count > 0:
    overall_mean = round(float(df_data["평균"].mean()), 1)
    highest_score = round(float(df_data["평균"].max()), 1)
    latest_date = str(df_data["등록일시"].iloc[-1])[:10]
else:
    overall_mean = 0.0
    highest_score = 0.0
    latest_date = "-"

with col1:
    st.metric(label="📄 총 설문 응답 수", value=f"{total_count} 건")
with col2:
    st.metric(label="⭐ 전체 평균 만족도", value=f"{overall_mean} / 5.0 점")
with col3:
    st.metric(label="🏆 최고 평균 점수", value=f"{highest_score} 점")
with col4:
    st.metric(label="🕒 최근 등록 일자", value=f"{latest_date}")

st.markdown("---")

# 시각화 탭 & 데이터 테이블 구성
tab1, tab2 = st.tabs(["📑 실시간 누적 집계표", "📈 세부 항목별 평균 분석"])

with tab1:
    col_filter1, col_filter2, col_down = st.columns([2.5, 1, 1.5])
    
    with col_filter1:
        search_query = st.text_input("🔍 발주사 / 공사명 / 담당자 검색", placeholder="검색어를 입력하세요...")
    
    with col_down:
        st.write("") # 줄맞춤 여백
        if total_count > 0:
            csv_data = df_data.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 엑셀용 CSV 다운로드 (UTF-8-SIG)",
                data=csv_data,
                file_name=f"survey_summary_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )
        else:
            st.button("📥 엑셀용 CSV 다운로드", disabled=True, use_container_width=True)

    # 검색 필터 적용
    filtered_df = df_data.copy()
    if search_query:
        mask = (
            filtered_df["발주사"].astype(str).str.contains(search_query, case=False, na=False) |
            filtered_df["공사명"].astype(str).str.contains(search_query, case=False, na=False) |
            filtered_df["담당자이름"].astype(str).str.contains(search_query, case=False, na=False)
        )
        filtered_df = filtered_df[mask]

    if len(filtered_df) > 0:
        st.caption("💡 **행(Row) 삭제 방법**: 삭제하고 싶은 줄(행)을 표에서 마우스로 클릭하면 삭제 버튼이 활성화됩니다.")

        selection_event = st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "등록일시": st.column_config.TextColumn("등록일시", width="medium"),
                "발주사": st.column_config.TextColumn("발주사", width="small"),
                "공사명": st.column_config.TextColumn("공사명", width="medium"),
                "계약기간": st.column_config.TextColumn("계약기간", width="medium"),
                "담당자소속": st.column_config.TextColumn("담당자소속", width="small"),
                "담당자이름": st.column_config.TextColumn("담당자이름", width="small"),
                "소통_설명및협의": st.column_config.NumberColumn("소통:설명협의", format="%d"),
                "소통_공사기간준수": st.column_config.NumberColumn("소통:공기준수", format="%d"),
                "품질_계약내용실행": st.column_config.NumberColumn("품질:계약실행", format="%d"),
                "품질_설계개선": st.column_config.NumberColumn("품질:설계개선", format="%d"),
                "안전_안전사고예방": st.column_config.NumberColumn("안전:사고예방", format="%d"),
                "기타_민원관리": st.column_config.NumberColumn("기타:민원관리", format="%d"),
                "종합_전반적만족도": st.column_config.NumberColumn("종합:전반만족", format="%d"),
                "합계": st.column_config.NumberColumn("총점 (35점)", format="%d"),
                "평균": st.column_config.NumberColumn("평균 (5.0점)", format="%.1f 점"),
            }
        )
        st.caption(f"총 {len(filtered_df)}개의 설문 결과가 조회되었습니다.")

        # 표에서 마우스 클릭으로 행을 선택했을 때 나타나는 삭제 패널
        selected_rows = []
        if selection_event and hasattr(selection_event, "selection"):
            sel = selection_event.selection
            if isinstance(sel, dict):
                selected_rows = sel.get("rows", [])
            elif hasattr(sel, "rows"):
                selected_rows = sel.rows or []

        if selected_rows and len(selected_rows) > 0:
            sel_idx = selected_rows[0]
            if sel_idx < len(filtered_df):
                target_item = filtered_df.iloc[sel_idx]
                target_orig_idx = filtered_df.index[sel_idx]

                with st.container():
                    st.warning(
                        f"선택한 설문: **[{target_item['등록일시']}] {target_item['발주사']} - {target_item['공사명']} (담당: {target_item['담당자이름']})**"
                    )
                    col_del_btn, col_del_space = st.columns([2.5, 7.5])
                    with col_del_btn:
                        if st.button("🗑️ 선택한 이 행 삭제하기", type="primary", use_container_width=True, key="btn_table_delete"):
                            if delete_survey_entry(target_orig_idx):
                                st.success("삭제 완료! 화면을 새로고침합니다...")
                                st.rerun()

        # 또는 하단 드롭다운 목록에서 번호로 골라 삭제할 수 있는 보조 기능
        with st.expander("🗑️ 목록에서 직접 골라서 삭제하기"):
            item_options = {
                idx: f"[{idx + 1}번] {row['등록일시']} | {row['발주사']} - {row['공사명']} ({row['담당자이름']})"
                for idx, row in df_data.iterrows()
            }
            chosen_row_idx = st.selectbox(
                "삭제할 설문 항목을 선택하세요:",
                options=list(item_options.keys()),
                format_func=lambda x: item_options[x],
                key="select_delete_row"
            )
            col_drop_del, _ = st.columns([2.5, 7.5])
            with col_drop_del:
                if st.button("🗑️ 선택한 항목 영구 삭제", type="primary", use_container_width=True, key="btn_dropdown_delete"):
                    if delete_survey_entry(chosen_row_idx):
                        st.success("삭제 완료! 화면을 새로고침합니다...")
                        st.rerun()

    else:
        if total_count == 0:
            st.info("💡 아직 등록된 설문 데이터가 없습니다. 좌측 사이드바에서 지류 설문지를 확인하고 첫 데이터를 등록해 보세요!")
        else:
            st.warning("검색 조건과 일치하는 데이터가 없습니다.")

with tab2:
    if total_count > 0:
        st.subheader("📊 7개 평가 항목별 평균 점수 현황")
        # 항목별 평균 점수 계산
        score_means = df_data[SCORE_COLUMNS].mean().round(2).reset_index()
        score_means.columns = ["평가항목", "평균점수"]
        
        # 라벨 가독성 개선
        label_map = {
            "소통_설명및협의": "1. 소통: 설명 및 협의",
            "소통_공사기간준수": "2. 소통: 공사기간 준수",
            "품질_계약내용실행": "3. 품질: 계약내용 실행",
            "품질_설계개선": "4. 품질: 설계 개선",
            "안전_안전사고예방": "5. 안전: 안전사고 예방",
            "기타_민원관리": "6. 기타: 민원 관리",
            "종합_전반적만족도": "7. 종합: 전반적 만족도"
        }
        score_means["문항명"] = score_means["평가항목"].map(label_map)
        
        # 차트 출력
        st.bar_chart(
            score_means.set_index("문항명")["평균점수"],
            height=320,
            use_container_width=True
        )
        
        # 세부 수치 표
        st.table(score_means[["문항명", "평균점수"]].rename(columns={"문항명": "평가 항목", "평균점수": "평균 점수 (5점 만점)"}))
    else:
        st.info("데이터가 등록되면 항목별 평균 점수 차트가 여기에 표시됩니다.")

# -------------------------------------------------------------
# 6. 하단 안내 및 파일 관리 가이드
# -------------------------------------------------------------
with st.expander("ℹ️ 사용 안내 및 데이터 백업 팁"):
    st.markdown("""
    - **데이터 자동 저장**: 설문 등록 시 `d:\\servey-app\\survey_data.csv` 파일에 자동으로 계속 누적 저장됩니다.
    - **엑셀 호환(한글 보존)**: 다운로드 버튼을 누르면 엑셀에서 바로 열어도 한글이 깨지지 않는 `UTF-8-SIG` 포맷으로 다운로드됩니다.
    - **지류 설문지 확인**: 좌측 사이드바의 파일 업로더에 PDF나 스캔 이미지를 올리면 바로 보면서 오타 없이 편리하게 입력할 수 있습니다.
    """)
