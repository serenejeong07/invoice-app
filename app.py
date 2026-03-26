import streamlit as st
import google.generativeai as genai
from PIL import Image
import os
from dotenv import load_dotenv
import datetime
import json
import pandas as pd
import io

# 클립보드 붙여넣기를 위한 외부 무료 라이브러리 임포트
from streamlit_paste_button import paste_image_button

# Load environment variables from .env file
load_dotenv()

# Configure Google Gemini API from environment variable
api_key = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=api_key)

st.set_page_config(page_title="인보이스 데이터 추출 및 생성기", layout="wide")

OPTIONS_FILE = "dropdown_options.json"

def load_options():
    try:
        if os.path.exists(OPTIONS_FILE):
            with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    
    return {
        "opt_manager": ["세림", "Serene"],
        "opt_shipping": ["DHL", "Fedex"],
        "opt_category": ["SKIN CARE LOTION SERUM", "Line Body", "Advanced Porcelain Radiance Package"],
        "opt_qty": ["10", "15", "20", "25", "50"],
        "opt_amount": ["$50", "$100", "$200"]
    }

def save_options(options_dict):
    try:
        with open(OPTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(options_dict, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

# 세션 상태에 드롭다운 파일 로드 및 초기값 세팅 (새로고침 시에도 유지되도록)
if "options_loaded" not in st.session_state:
    loaded = load_options()
    st.session_state.opt_manager = loaded.get("opt_manager", ["세림", "Serene"])
    st.session_state.opt_shipping = loaded.get("opt_shipping", ["DHL", "Fedex"])
    st.session_state.opt_category = loaded.get("opt_category", ["SKIN CARE LOTION SERUM", "Line Body"])
    st.session_state.opt_qty = loaded.get("opt_qty", ["10", "15", "20"])
    st.session_state.opt_amount = loaded.get("opt_amount", ["$50", "$100", "$200"])
    st.session_state.options_loaded = True

st.title("인보이스 데이터 추출 및 카카오톡 메시지 생성기")
st.markdown("클립보드에 복사된 인보이스 이미지를 붙여넣어 데이터를 추출하고, 사용자가 편집하여 최종 카카오톡 메시지를 생성합니다.")

if not api_key:
    st.warning("경고: .env 파일에 GEMINI_API_KEY가 설정되지 않았습니다.")

def extract_invoice_data(image_file_bytes):
    """
    Gemini API를 사용하여 이미지에서 데이터를 JSON 형태로 파싱하여 추출합니다.
    """
    image = Image.open(io.BytesIO(image_file_bytes))
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = """
    Please extract the following information from the provided invoice image.
    Return ONLY a valid JSON object without any markdown formatting or extra text.
    The JSON should have exactly the following structure:
    {
      "consignee_name": "extracted consignee name",
      "consignee_phone": "extracted phone number",
      "consignee_address": "detailed street address only (do not include country or zip code)",
      "consignee_country": "extracted country (e.g., UK)",
      "consignee_zipcode": "extracted zip code or postal code",
      "total_qty": "extracted total quantity as naturally found",
      "total_amount": "extracted total amount including currency symbol (e.g., £461.0)",
      "items": [
        {"name": "item name", "quantity": "item quantity"}
      ]
    }
    
    Notes:
    - If an item's name contains "Delivery", "delivery", or relates to shipping, DO NOT include it in the items list.
    - If a field is missing, leave the value as an empty string.
    - Make sure it's 100% valid JSON.
    """
    try:
        response = model.generate_content([prompt, image])
        text = response.text.strip()
        
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        return json.loads(text.strip())
    except Exception as e:
        return {"error": str(e)}

# =========================================================
# 1. 이미지 복사/붙여넣기 섹션
# =========================================================
st.subheader("1. 인보이스 이미지 붙여넣기")
st.markdown("이미지를 클립보드에 복사한 뒤, **아래 버튼을 한 번 클릭하고 Ctrl+V (Mac은 Cmd+V)** 를 눌러주세요.")

paste_result = paste_image_button(
    label="클릭하고 Ctrl+V 눌러서 붙여넣기",
    background_color="#f0f2f6",
    hover_background_color="#e0e2e6",
    text_color="#1f1f1f"
)

if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = None

if paste_result.image_data is not None:
    st.image(paste_result.image_data, caption="붙여넣은 인보이스 이미지", width=400)
    
    if st.button("🚀 데이터 추출 시작", type="primary"):
        with st.spinner("최신 Gemini API가 이미지를 분석 중입니다... (약 5~10초 소요)"):
            
            img_byte_arr = io.BytesIO()
            paste_result.image_data.save(img_byte_arr, format='PNG')
            image_bytes = img_byte_arr.getvalue()
            
            extracted = extract_invoice_data(image_bytes)
            st.session_state.extracted_data = extracted  
            
            # 추출된 데이터를 UI 편집용 session_state로 각각 저장합니다 (이후 텍스트 박스와 양방향 바인딩됨)
            st.session_state.edit_consignee_name = extracted.get("consignee_name", "")
            st.session_state.edit_consignee_phone = extracted.get("consignee_phone", "")
            st.session_state.edit_consignee_address = extracted.get("consignee_address", "")
            st.session_state.edit_consignee_country = extracted.get("consignee_country", "")
            st.session_state.edit_consignee_zipcode = extracted.get("consignee_zipcode", "")
            
            raw_items = [
                item for item in extracted.get("items", [])
                if "delivery" not in str(item.get("name", "")).lower()
            ]
            if not raw_items:
                raw_items = [{"name": "", "quantity": ""}]
            st.session_state.edit_items = pd.DataFrame(raw_items)
            
            # 새로운 데이터를 추출할 때마다 모든 선택값을 초기화하여 항상 첫번째 항목(index 0)으로 돌아가게 설정
            for k in ["sel_manager", "sel_shipping", "sel_category", "sel_qty", "sel_amount"]:
                if k in st.session_state:
                    del st.session_state[k]

# =========================================================
# 2. 데이터 추출 결과 및 데이터 편집 패널
# =========================================================
if st.session_state.extracted_data is not None:
    extracted_data = st.session_state.extracted_data
    
    st.markdown("---")
    st.subheader("2. 데이터 추출 및 편집")
    
    if "error" in extracted_data:
        st.error(f"데이터 추출 중 오류가 발생했습니다: {extracted_data['error']}")
    else:
        today_yymmdd = datetime.datetime.now().strftime("%y%m%d")

        # [NEW] 텍스트 에어리어를 이용해 직관적으로 순서를 바꾸고 편집할 수 있는 패널
        with st.expander("⚙️ 드롭다운 항목 편집 (순서 변경/수정/삭제 가능) - 자동 저장"):
            st.markdown("아래 박스에서 각 항목을 줄바꿈(엔터)으로 구분해 입력하세요. 자연스럽게 텍스트를 위아래로 잘라내기/붙여넣기하여 순서를 이동시킬 수 있습니다! 맨 윗줄에 쓴 항목이 항상 기본 선택됩니다.")
            ec1, ec2, ec3, ec4, ec5 = st.columns(5)
            
            def edit_text_area(header, option_list, col_key):
                text_content = "\n".join(option_list)
                edited_text = st.text_area(header, value=text_content, height=150, key=f"editor_{col_key}")
                return [x.strip() for x in edited_text.split("\n") if x.strip()]
                
            with ec1:
                cur_manager = edit_text_area("담당자 이름", st.session_state.opt_manager, "manager")
            with ec2:
                cur_shipping = edit_text_area("물류", st.session_state.opt_shipping, "shipping")
            with ec3:
                cur_category = edit_text_area("인보이스 품명", st.session_state.opt_category, "category")
            with ec4:
                cur_qty = edit_text_area("인보이스 수량", st.session_state.opt_qty, "qty")
            with ec5:
                cur_amount = edit_text_area("인보이스 금액", st.session_state.opt_amount, "amount")
                
            # 만약 사용자가 에디터에서 뭔가 추가/삭제/수정/순서변경 했다면 상태 업데이트 후 json 파일에 영구 저장
            if (cur_manager != st.session_state.opt_manager or 
                cur_shipping != st.session_state.opt_shipping or 
                cur_category != st.session_state.opt_category or 
                cur_qty != st.session_state.opt_qty or 
                cur_amount != st.session_state.opt_amount):
                
                st.session_state.opt_manager = cur_manager
                st.session_state.opt_shipping = cur_shipping
                st.session_state.opt_category = cur_category
                st.session_state.opt_qty = cur_qty
                st.session_state.opt_amount = cur_amount
                
                save_options({
                    "opt_manager": cur_manager,
                    "opt_shipping": cur_shipping,
                    "opt_category": cur_category,
                    "opt_qty": cur_qty,
                    "opt_amount": cur_amount
                })
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 이미지 추출 정보 (좌측)")
            # 세션 스테이트 초기화 (이전 버전 구조에서 진입시를 대비한 방어코드)
            if "edit_consignee_name" not in st.session_state:
                st.session_state.edit_consignee_name = extracted_data.get("consignee_name", "")
                st.session_state.edit_consignee_phone = extracted_data.get("consignee_phone", "")
                st.session_state.edit_consignee_address = extracted_data.get("consignee_address", "")
                st.session_state.edit_consignee_country = extracted_data.get("consignee_country", "")
                st.session_state.edit_consignee_zipcode = extracted_data.get("consignee_zipcode", "")
                
                raw_items = [
                    item for item in extracted_data.get("items", [])
                    if "delivery" not in str(item.get("name", "")).lower()
                ]
                st.session_state.edit_items = pd.DataFrame(raw_items) if raw_items else pd.DataFrame([{"name": "", "quantity": ""}])

            # 값 입력시 session_state.edit_* 가 업데이트되며 재실행시 보존됨
            e_consignee_name = st.text_input("수취인 이름", key="edit_consignee_name")
            e_consignee_phone = st.text_input("수취인 전화번호", key="edit_consignee_phone")
            e_consignee_address = st.text_input("수취인 상세주소", key="edit_consignee_address")
            e_consignee_country = st.text_input("수취인 나라", key="edit_consignee_country")
            e_consignee_zipcode = st.text_input("수취인 우편번호", key="edit_consignee_zipcode")
            
        with col2:
            st.markdown("#### 사용자 고정 및 수동 선택 정보 (우측)")
            e_date = st.text_input("날짜", value=today_yymmdd)
            manual_batch = st.text_input("주문 번호", value="11")
            
            # 여기서 AI 추출 로직과 무관하게 오로지 윗부분 텍스트에서 저장된 순서(cur_*)대로만 나타나도록 연결됨.
            manual_manager = st.selectbox("담당자 이름", options=cur_manager, key="sel_manager")
            manual_shipping = st.selectbox("물류", options=cur_shipping, key="sel_shipping")
            manual_category = st.selectbox("인보이스 품명", options=cur_category, key="sel_category")
            e_total_qty = st.selectbox("인보이스 수량", options=cur_qty, key="sel_qty")
            e_total_amount = st.selectbox("인보이스 금액", options=cur_amount, key="sel_amount")
            
        st.markdown("#### 품목 리스트 편집 (DataFrame)")
        st.caption("항목을 직접 더블 클릭하여 내용을 수정하거나, 우측 상단의 x로 행을 삭제/추가할 수 있습니다.")
        
        # session_state에 보관된 품목 리스트를 바인딩하여 편집 상태 완전 유지
        edited_df = st.data_editor(
            st.session_state.edit_items,
            num_rows="dynamic",
            use_container_width=True,
            key="edited_items_table",
            column_config={
                "name": st.column_config.TextColumn("품명"),
                "quantity": st.column_config.TextColumn("수량 (ex: 5)")
            }
        )
        
        st.markdown("---")
        st.subheader("3. 최종 출력 및 카카오톡 복사 패널")
        
        if st.button("최종 텍스트 생성하기", type="primary"):
            items_lines = []
            for idx, row in edited_df.iterrows():
                name = str(row.get("name", "")).strip()
                qty = str(row.get("quantity", "")).strip()
                if name:  
                    items_lines.append(f"{name} - {qty}개")
            
            items_text = "\n".join(items_lines)
            
            v_manager = manual_manager if manual_manager else ""
            v_shipping = manual_shipping if manual_shipping else ""
            v_category = manual_category if manual_category else ""
            v_qty = e_total_qty if e_total_qty else ""
            v_amount = e_total_amount if e_total_amount else ""
            
            final_text = f"""{e_date} {manual_batch} {v_shipping} - {e_consignee_name}
{v_manager}

{items_text}

물류：{v_shipping}
인보이스 품명 : {v_category}
인보이스 수량：{v_qty}
인보이스 총금액 : {v_amount}

수취인이름 : {e_consignee_name}
번호 : {e_consignee_phone}
상세주소 :{e_consignee_address}
나라 : {e_consignee_country}
우편번호 : {e_consignee_zipcode}"""

            st.success("텍스트가 생성되었습니다! 아래 코드 블록 우측 상단의 [복사 아이콘]을 눌러 카카오톡에 바로 붙여넣으세요.")
            st.code(final_text, language="nohighlight")
