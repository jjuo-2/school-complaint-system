import streamlit as st
import hashlib
import heapq
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import uuid
import os

# Firebase 관련 import
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    st.error("Firebase 패키지가 설치되지 않았습니다. requirements.txt에 firebase-admin을 추가해주세요.")

# 사용자 역할별 권한 정의
USER_ROLES = {
    'parent': {
        'permissions': ['민원등록', '내민원조회', '상태확인'],
        'display_name': '학부모'
    },
    'teacher': {
        'permissions': ['내민원조회', '상태확인', '전체민원조회', '민원할당', '상태변경'],
        'display_name': '교직원'
    },
    'admin': {
        'permissions': ['모든권한', '사용자관리', '교사관리', '시스템설정'],
        'display_name': '관리자'
    }
}

# 민원 카테고리 정의
COMPLAINT_CATEGORIES = {
    'academic': '학사 관련',
    'facility': '시설 관리',
    'meal': '급식 관련', 
    'health': '보건 관련',
    'counseling': '상담 관련',
    'safety': '안전 관리',
    'general': '일반 문의'
}

# 자주 하는 질문 데이터
FAQ_DATA = {
    '급식 관련': [
        {
            'question': '급식 메뉴는 어디서 확인할 수 있나요?',
            'answer': '하이클래스 → 급식안내 메뉴에서 주간 급식표를 확인하실 수 있습니다.'
        },
        {
            'question': '알레르기가 있는 경우 어떻게 해야 하나요?',
            'answer': '보건실(031-123-4567)로 연락주시거나 담임선생님께 사전에 알려주세요.'
        },
    ],
    '학사 일정': [
        {
            'question': '2025학년도 방학 기간은 언제인가요?',
            'answer': '여름방학: 7월 28일 ~ 8월 20일\n\n겨울방학: 26년 1월 6일 ~ 2월 28일\n'
        },
        {
            'question': '학부모 상담 주간은 언제인가요?',
            'answer': '4월 2주가 학부모 상담주간이며, \n개별 상담은 담임선생님과 사전 약속 후 가능합니다.'
        },
        {
            'question': '체험학습 신청은 어떻게 하나요?',
            'answer': '체험학습 신청서를 담임선생님께 최대 3일전에 제출해주세요. \n\n 연간 16일 이내로 가능합니다.'
        }
    ],
    '시설 이용': [
        {
            'question': '도서관 이용 시간은 언제인가요?',
            'answer': '평일: 오전 9시 ~ 오후 4시\n\n토, 일요일/공휴일: 휴관'
        },
        {
            'question': '운동장 개방 시간은?',
            'answer': '평일 오후 6시 ~ 8시, 주말 오전 9시 ~ 오후 6시\n\n학교 행사가 있는 날은 이용이 제한될 수 있습니다.'
        },
    ],
    '보건/안전': [
        {
            'question': '아이가 학교에서 아플 때는?',
            'answer': '보건실에서 1차 처치 후 학부모님께 연락드립니다. 응급상황 시 119신고 후 즉시 연락드립니다.'
        },
        {
            'question': '학교 출입 시 준수사항이 있나요?',
            'answer': '방문증 착용 필수, 신분증 지참, 출입대장 작성 후 출입 가능합니다. 보안상 무단 출입은 금지됩니다.'
        },
        {
            'question': '감염병 발생 시 어떻게 해야 하나요?',
            'answer': '즉시 담임선생님과 보건실에 연락하고, 완치 시까지 등교중지합니다. 진단서 제출 후 출석 인정됩니다.'
        }
    ]
}

class FirebaseManager:
    """Firebase 연결 및 데이터베이스 관리"""
    
    def __init__(self):
        self.db = None
        self.initialize_firebase()
    
    @st.cache_resource
    def initialize_firebase(_self):
        """Firebase 초기화 (중복 방지)"""
        if not FIREBASE_AVAILABLE:
            st.error("❌ Firebase 패키지가 설치되지 않았습니다!")
            return None
        
        if not firebase_admin._apps:
            try:
                # Streamlit Cloud에서 실행 중인지 확인
                if hasattr(st, 'secrets') and 'firebase' in st.secrets:
                    # Secrets에서 인증 정보 가져오기
                    cred = credentials.Certificate({
                        "type": st.secrets["firebase"]["type"],
                        "project_id": st.secrets["firebase"]["project_id"],
                        "private_key_id": st.secrets["firebase"]["private_key_id"],
                        "private_key": st.secrets["firebase"]["private_key"],
                        "client_email": st.secrets["firebase"]["client_email"],
                        "client_id": st.secrets["firebase"]["client_id"],
                        "auth_uri": st.secrets["firebase"]["auth_uri"],
                        "token_uri": st.secrets["firebase"]["token_uri"],
                        "auth_provider_x509_cert_url": st.secrets["firebase"]["auth_provider_x509_cert_url"],
                        "client_x509_cert_url": st.secrets["firebase"]["client_x509_cert_url"]
                    })
                    st.success("☁️ Streamlit Cloud에서 Firebase 연결!")
                else:
                    # 로컬에서 JSON 파일 사용
                    if os.path.exists("firebase-key.json"):
                        cred = credentials.Certificate("firebase-key.json")
                        st.success("💻 로컬 환경에서 Firebase 연결!")
                    else:
                        st.error("❌ firebase-key.json 파일을 찾을 수 없습니다!")
                        return None
                
                firebase_admin.initialize_app(cred)
                return firestore.client()
                
            except Exception as e:
                st.error(f"❌ Firebase 연결 실패: {e}")
                return None
        else:
            return firestore.client()
    
    def get_db(self):
        """데이터베이스 인스턴스 반환"""
        if self.db is None:
            self.db = self.initialize_firebase()
        return self.db
    
    def save_user(self, user_id: str, user_data: dict):
        """사용자 정보 저장"""
        try:
            db = self.get_db()
            if db:
                db.collection('users').document(user_id).set(user_data)
                return True
        except Exception as e:
            st.error(f"사용자 저장 실패: {e}")
            return False
    
    def get_user(self, user_id: str):
        """사용자 정보 조회"""
        try:
            db = self.get_db()
            if db:
                doc = db.collection('users').document(user_id).get()
                if doc.exists:
                    return doc.to_dict()
            return None
        except Exception as e:
            st.error(f"사용자 조회 실패: {e}")
            return None
    
    def get_all_users(self):
        """모든 사용자 조회"""
        try:
            db = self.get_db()
            if db:
                docs = db.collection('users').stream()
                users = {}
                for doc in docs:
                    users[doc.id] = doc.to_dict()
                return users
            return {}
        except Exception as e:
            st.error(f"사용자 목록 조회 실패: {e}")
            return {}
    
    def save_complaint(self, complaint_id: str, complaint_data: dict):
        """민원 저장"""
        try:
            db = self.get_db()
            if db:
                db.collection('complaints').document(complaint_id).set(complaint_data)
                return True
        except Exception as e:
            st.error(f"민원 저장 실패: {e}")
            return False
    
    def update_complaint(self, complaint_id: str, update_data: dict):
        """민원 업데이트"""
        try:
            db = self.get_db()
            if db:
                db.collection('complaints').document(complaint_id).update(update_data)
                return True
        except Exception as e:
            st.error(f"민원 업데이트 실패: {e}")
            return False
    
    def get_all_complaints(self):
        """모든 민원 조회"""
        try:
            db = self.get_db()
            if db:
                docs = db.collection('complaints').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
                complaints = {}
                for doc in docs:
                    complaints[doc.id] = doc.to_dict()
                return complaints
            return {}
        except Exception as e:
            st.error(f"민원 목록 조회 실패: {e}")
            return {}
    
    def save_student_registry(self, registry_data: dict):
        """학생 명단 저장"""
        try:
            db = self.get_db()
            if db:
                db.collection('system').document('student_registry').set({'data': registry_data})
                return True
        except Exception as e:
            st.error(f"학생 명단 저장 실패: {e}")
            return False
    
    def get_student_registry(self):
        """학생 명단 조회"""
        try:
            db = self.get_db()
            if db:
                doc = db.collection('system').document('student_registry').get()
                if doc.exists:
                    return doc.to_dict().get('data', {})
            return {}
        except Exception as e:
            st.error(f"학생 명단 조회 실패: {e}")
            return {}
    
    def save_teacher_codes(self, codes: set):
        """교사 코드 저장"""
        try:
            db = self.get_db()
            if db:
                db.collection('system').document('teacher_codes').set({'codes': list(codes)})
                return True
        except Exception as e:
            st.error(f"교사 코드 저장 실패: {e}")
            return False
    
    def get_teacher_codes(self):
        """교사 코드 조회"""
        try:
            db = self.get_db()
            if db:
                doc = db.collection('system').document('teacher_codes').get()
                if doc.exists:
                    return set(doc.to_dict().get('codes', []))
            return set()
        except Exception as e:
            st.error(f"교사 코드 조회 실패: {e}")
            return set()

class ComplaintSystem:
    def __init__(self, firebase_manager):
        self.firebase = firebase_manager
        self.load_from_firebase()
    
    def load_from_firebase(self):
        """Firebase에서 데이터 로드"""
        if self.firebase.get_db():
            complaints = self.firebase.get_all_complaints()
            if complaints:
                st.session_state.complaints_db = complaints
            else:
                if 'complaints_db' not in st.session_state:
                    st.session_state.complaints_db = {}
        
        if 'complaint_queue' not in st.session_state:
            st.session_state.complaint_queue = []
        if 'processing_stack' not in st.session_state:
            st.session_state.processing_stack = []
        if 'complaint_counter' not in st.session_state:
            st.session_state.complaint_counter = 1
    
    def create_complaint(self, title: str, content: str, category: str, urgency: str, user_id: str) -> str:
        """민원 등록 (Firebase에 저장)"""
        complaint_id = str(st.session_state.complaint_counter)
        st.session_state.complaint_counter += 1
        
        urgency_value = 1 if urgency == '긴급' else 2
        
        complaint = {
            'id': complaint_id,
            'title': title,
            'content': content,
            'category': category,
            'urgency': urgency,
            'urgency_value': urgency_value,
            'status': '대기중',
            'created_by': user_id,
            'created_at': datetime.now().isoformat(),
            'assigned_to': None,
            'history': [{
                'status': '대기중',
                'timestamp': datetime.now().isoformat(),
                'note': '민원 등록됨'
            }]
        }
        
        heapq.heappush(st.session_state.complaint_queue, (urgency_value, int(complaint_id)))
        st.session_state.complaints_db[complaint_id] = complaint
        self.firebase.save_complaint(complaint_id, complaint)
        
        return complaint_id
    
    def update_complaint_status(self, complaint_id: str, new_status: str, note: str = ""):
        """민원 상태 업데이트 (Firebase 동기화)"""
        complaint_id_str = str(complaint_id)
        
        if complaint_id_str not in st.session_state.complaints_db:
            return False
        
        complaint = st.session_state.complaints_db[complaint_id_str]
        complaint['status'] = new_status
        complaint['history'].append({
            'status': new_status,
            'timestamp': datetime.now().isoformat(),
            'note': note or f'상태 변경: {new_status}'
        })
        
        if new_status == '완료' and int(complaint_id) in st.session_state.processing_stack:
            st.session_state.processing_stack.remove(int(complaint_id))
        
        self.firebase.update_complaint(complaint_id_str, {
            'status': new_status,
            'history': complaint['history']
        })
        
        return True

class AuthSystem:
    def __init__(self, firebase_manager):
        self.firebase = firebase_manager
        self.load_from_firebase()
    
    def load_from_firebase(self):
        """Firebase에서 데이터 로드"""
        if self.firebase.get_db():
            users = self.firebase.get_all_users()
            if users:
                st.session_state.user_db = users
            
            student_registry = self.firebase.get_student_registry()
            if student_registry:
                st.session_state.student_registry = student_registry
            
            teacher_codes = self.firebase.get_teacher_codes()
            if teacher_codes:
                st.session_state.teacher_codes = teacher_codes
        
        if 'user_db' not in st.session_state:
            st.session_state.user_db = {
                'admin': {
                    'password_hash': self.hash_password('admin123'),
                    'role': 'admin',
                    'name': '시스템 관리자',
                    'created_at': datetime.now().isoformat()
                }
            }
        
        if 'student_registry' not in st.session_state:
            st.session_state.student_registry = {
                '김철수': {'grade': 1, 'class': '1', 'student_id': '47', 'year': 2025},
                '이영희': {'grade': 2, 'class': '2', 'student_id': '23', 'year': 2025},
                '박민수': {'grade': 3, 'class': '3', 'student_id': '58', 'year': 2025},
                '최지영': {'grade': 1, 'class': '4', 'student_id': '14', 'year': 2025},
                '정우진': {'grade': 2, 'class': '5', 'student_id': '36', 'year': 2025}
            }
        
        if 'teacher_db' not in st.session_state:
            st.session_state.teacher_db = {}
        
        if 'teacher_codes' not in st.session_state:
            st.session_state.teacher_codes = set()
        
        if 'current_user' not in st.session_state:
            st.session_state.current_user = None
        
        if 'is_logged_in' not in st.session_state:
            st.session_state.is_logged_in = False
    
    def hash_password(self, password: str) -> str:
        """비밀번호 해싱"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def generate_teacher_code(self) -> str:
        """교사 가입 코드 생성 (Firebase 동기화)"""
        code = str(uuid.uuid4())[:8].upper()
        st.session_state.teacher_codes.add(code)
        self.firebase.save_teacher_codes(st.session_state.teacher_codes)
        return code
    
    def signup_teacher_with_code(self, teacher_id: str, password: str, name: str, code: str) -> Tuple[bool, str]:
        """교사 회원가입 (Firebase 동기화)"""
        if code not in st.session_state.teacher_codes:
            return False, "유효하지 않은 교사 가입 코드입니다."
        
        if teacher_id in st.session_state.user_db:
            return False, "이미 존재하는 사용자 ID입니다."
        
        user_data = {
            'password_hash': self.hash_password(password),
            'role': 'teacher',
            'name': name,
            'created_at': datetime.now().isoformat()
        }
        
        st.session_state.user_db[teacher_id] = user_data
        st.session_state.teacher_db[teacher_id] = {
            'categories': [],
            'is_master': False
        }
        
        st.session_state.teacher_codes.remove(code)
        
        self.firebase.save_user(teacher_id, user_data)
        self.firebase.save_teacher_codes(st.session_state.teacher_codes)
        
        return True, f"교사 계정이 성공적으로 생성되었습니다!"
    
    def add_student_to_registry(self, student_name: str, grade: int, class_name: str, student_id: str, year: int = 2025) -> Tuple[bool, str]:
        """학생 명단에 추가 (Firebase 동기화)"""
        if student_name in st.session_state.student_registry:
            return False, "이미 등록된 학생입니다."
        
        st.session_state.student_registry[student_name] = {
            'grade': grade,
            'class': class_name,
            'student_id': student_id,
            'year': year
        }
        
        self.firebase.save_student_registry(st.session_state.student_registry)
        return True, f"{student_name} 학생이 명단에 추가되었습니다."
    
    def signup_parent(self, student_name: str, password: str) -> Tuple[bool, str]:
        """학부모 회원가입 (Firebase 동기화)"""
        if student_name not in st.session_state.student_registry:
            return False, "등록되지 않은 학생입니다. 학교에 문의해주세요."
        
        parent_id = student_name
        
        if parent_id in st.session_state.user_db:
            return False, "이미 등록된 계정입니다."
        
        user_data = {
            'password_hash': self.hash_password(password),
            'role': 'parent',
            'name': f"{student_name} 학부모",
            'student_name': student_name,
            'created_at': datetime.now().isoformat()
        }
        
        st.session_state.user_db[parent_id] = user_data
        self.firebase.save_user(parent_id, user_data)
        
        return True, f"{student_name} 학부모 계정이 생성되었습니다! (로그인 ID: {student_name})"
    
    def login(self, user_id: str, password: str) -> Tuple[bool, str]:
        """로그인"""
        if user_id not in st.session_state.user_db:
            return False, "존재하지 않는 사용자입니다."
        
        user = st.session_state.user_db[user_id]
        if user['password_hash'] != self.hash_password(password):
            return False, "비밀번호가 올바르지 않습니다."
        
        st.session_state.current_user = {
            'id': user_id,
            'name': user['name'],
            'role': user['role'],
            'permissions': USER_ROLES[user['role']]['permissions']
        }
        st.session_state.is_logged_in = True
        
        return True, f"환영합니다, {user['name']}님!"
    
    def logout(self):
        """로그아웃"""
        st.session_state.current_user = None
        st.session_state.is_logged_in = False
        st.rerun()
    
    def is_master_teacher(self, user_id: str) -> bool:
        """마스터 교사 권한 확인"""
        if user_id == 'admin':
            return True
        return st.session_state.teacher_db.get(user_id, {}).get('is_master', False)
    
    def list_complaints(self, current_user: Dict) -> List[Dict]:
        """민원 목록 조회 (권한별)"""
        user_role = current_user['role']
        user_id = current_user['id']
        
        all_complaints = list(st.session_state.complaints_db.values())
        
        if user_role == 'admin':
            return all_complaints
        elif user_role == 'parent':
            return [c for c in all_complaints if c['created_by'] == user_id]
        elif user_role == 'teacher':
            if self.is_master_teacher(user_id):
                return all_complaints
            else:
                teacher_categories = st.session_state.teacher_db.get(user_id, {}).get('categories', [])
                return [c for c in all_complaints if c['category'] in teacher_categories]
        
        return []

def render_faq_section():
    """자주 하는 질문 섹션"""
    st.subheader("❓ 자주 하는 질문")
    st.info("민원 등록 전에 아래 내용을 먼저 확인해보세요!")
    
    for category, faqs in FAQ_DATA.items():
        with st.expander(f"📂 {category}"):
            for i, faq in enumerate(faqs, 1):
                st.markdown(f"**Q{i}. {faq['question']}**")
                st.markdown(f"**A{i}.** {faq['answer']}")
                if i < len(faqs):
                    st.markdown("---")
    
    st.markdown("---")
    st.markdown("💡 **위 내용으로 해결되지 않는 문제가 있으시면 민원을 등록해주세요!**")

def render_admin_management():
    """관리자 전용 관리 페이지"""
    st.subheader("🔧 시스템 관리")
    auth = st.session_state.auth_system
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["교사 코드 생성", "교사 권한 관리", "학생 명단 관리", "시스템 현황", "Firebase 상태"])
    
    with tab1:
        st.write("**교사 가입 코드 생성**")
        if st.button("새 교사 코드 생성"):
            code = auth.generate_teacher_code()
            st.success(f"교사 가입 코드: **{code}**")
            st.info("이 코드를 교사에게 전달하여 회원가입시 사용하게 하세요.")
        
        if st.session_state.teacher_codes:
            st.write("**활성 코드 목록:**")
            for code in st.session_state.teacher_codes:
                st.code(code)
    
    with tab2:
        st.write("**교사 카테고리 관리**")
        
        teachers = [uid for uid, user in st.session_state.user_db.items() if user['role'] == 'teacher']
        
        if teachers:
            selected_teacher = st.selectbox("교사 선택", teachers)
            
            current_categories = st.session_state.teacher_db.get(selected_teacher, {}).get('categories', [])
            st.write(f"현재 담당 카테고리: {', '.join(current_categories) if current_categories else '없음'}")
            
            new_categories = st.multiselect(
                "담당 카테고리 설정",
                list(COMPLAINT_CATEGORIES.keys()),
                default=current_categories,
                format_func=lambda x: COMPLAINT_CATEGORIES[x]
            )
            
            is_master = st.checkbox(
                "마스터 교사 권한 (모든 카테고리 접근 가능)",
                value=st.session_state.teacher_db.get(selected_teacher, {}).get('is_master', False)
            )
            
            if st.button("설정 저장"):
                if selected_teacher not in st.session_state.teacher_db:
                    st.session_state.teacher_db[selected_teacher] = {}
                
                st.session_state.teacher_db[selected_teacher]['categories'] = new_categories
                st.session_state.teacher_db[selected_teacher]['is_master'] = is_master
                st.success("교사 권한이 업데이트되었습니다!")
                st.rerun()
        else:
            st.info("등록된 교사가 없습니다.")
    
    with tab3:
        st.write("**🔒 학생 명단 관리 (보안 기능)**")
        st.info("등록된 학생만 회원가입이 가능합니다.")
        
        st.write("**👤 개별 학생 추가**")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            new_student_name = st.text_input("학생 이름")
        with col2:
            new_grade = st.selectbox("학년", [1, 2, 3, 4, 5, 6])
        with col3:
            new_class = st.text_input("반", placeholder="1")
        with col4:
            new_student_id = st.text_input("학번", placeholder="47")
        with col5:
            new_year = st.number_input("연도", value=2025, min_value=2020, max_value=2030)
        
        if st.button("학생 추가") and new_student_name:
            success, message = auth.add_student_to_registry(new_student_name, new_grade, new_class, new_student_id, new_year)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
        
        st.markdown("---")
        
        st.write("**등록된 학생 목록**")
        if st.session_state.student_registry:
            student_data = []
            for name, info in st.session_state.student_registry.items():
                student_data.append({
                    '이름': name,
                    '학년': f"{info['grade']}학년",
                    '반': f"{info['class']}반",
                    '학번': info['student_id'],
                    '연도': info.get('year', 2025)
                })
            
            try:
                import pandas as pd
                df = pd.DataFrame(student_data)
                st.dataframe(df, use_container_width=True)
            except ImportError:
                for data in student_data:
                    st.write(f"- {data['이름']} ({data['학년']} {data['반']}, 학번: {data['학번']})")
        else:
            st.info("등록된 학생이 없습니다.")
    
    with tab4:
        st.write("**시스템 현황**")
        
        user_stats = {}
        for user in st.session_state.user_db.values():
            role = user['role']
            user_stats[role] = user_stats.get(role, 0) + 1
        
        st.write("**사용자 현황:**")
        for role, count in user_stats.items():
            st.write(f"- {USER_ROLES[role]['display_name']}: {count}명")
        
        complaint_stats = {}
        for complaint in st.session_state.complaints_db.values():
            status = complaint['status']
            complaint_stats[status] = complaint_stats.get(status, 0) + 1
        
        st.write("**민원 현황:**")
        for status, count in complaint_stats.items():
            st.write(f"- {status}: {count}건")
        
        st.write(f"**학생 명단:** {len(st.session_state.student_registry)}명 등록됨")
    
    with tab5:
        st.write("**Firebase 연결 상태**")
        firebase_manager = st.session_state.firebase_manager
        
        if firebase_manager.get_db():
            st.success("✅ Firebase 연결됨")
            
            # 컬렉션 상태 확인
            try:
                db = firebase_manager.get_db()
                collections = ['users', 'complaints', 'system']
                
                for collection_name in collections:
                    docs = list(db.collection(collection_name).limit(1).stream())
                    if docs:
                        st.write(f"📊 {collection_name}: 데이터 있음")
                    else:
                        st.write(f"📋 {collection_name}: 비어있음")
                        
            except Exception as e:
                st.error(f"컬렉션 확인 중 오류: {e}")
        else:
            st.error("❌ Firebase 연결 실패")

def render_auth_page():
    """인증 페이지"""
    auth = st.session_state.auth_system
    
    st.title("🏫 학교 민원처리시스템")
    st.markdown("---")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🔑 로그인", "❓ 자주 하는 질문", "👨‍👩‍👧‍👦 학부모 가입", "👨‍🏫 교사 가입"])
    
    with tab1:
        st.subheader("로그인")
        st.info("🔹 학부모: 학생 이름으로 로그인\n🔹 교사: 교사 ID로 로그인\n🔹 관리자: admin")
        
        with st.form("login_form"):
            login_id = st.text_input("사용자 ID", placeholder="학생 이름 또는 교사 ID")
            login_password = st.text_input("비밀번호", type="password")
            login_submit = st.form_submit_button("로그인", use_container_width=True)
            
            if login_submit and login_id and login_password:
                success, message = auth.login(login_id, login_password)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
    
    with tab2:
        render_faq_section()
    
    with tab3:
        st.subheader("학부모 회원가입")
        st.info("🔒 등록된 학생의 학부모만 가입 가능합니다.")
        st.warning("⚠️ 보안상 학생 이름을 정확히 입력해주세요. (오타,띄어쓰기 주의)")
        
        with st.form("parent_signup"):
            child_name = st.text_input("자녀 이름", placeholder="정확한 학생 이름 입력")
            parent_password = st.text_input("비밀번호", type="password")
            parent_submit = st.form_submit_button("가입하기")
            
            if parent_submit and child_name and parent_password:
                success, message = auth.signup_parent(child_name, parent_password)
                if success:
                    st.success(message)
                else:
                    st.error(message)
    
    with tab4:
        st.subheader("교사 회원가입")
        with st.form("teacher_signup"):
            teacher_id = st.text_input("교사 ID")
            teacher_name = st.text_input("교사 이름")
            teacher_password = st.text_input("비밀번호", type="password")
            teacher_code = st.text_input("교사 가입 코드 (관리자에게 문의)")
            teacher_submit = st.form_submit_button("가입하기")
            
            if teacher_submit and all([teacher_id, teacher_name, teacher_password, teacher_code]):
                success, message = auth.signup_teacher_with_code(teacher_id, teacher_password, teacher_name, teacher_code)
                if success:
                    st.success(message)
                else:
                    st.error(message)

def render_complaint_details(complaint, user, complaint_sys):
    """민원 상세 정보 렌더링"""
    st.write(f"**카테고리:** {COMPLAINT_CATEGORIES.get(complaint['category'], complaint['category'])}")
    st.write(f"**긴급도:** {complaint['urgency']}")
    st.write(f"**등록자:** {complaint['created_by']}")
    st.write(f"**등록일:** {complaint['created_at'][:19]}")
    if complaint['assigned_to']:
        st.write(f"**담당자:** {complaint['assigned_to']}")
    st.write(f"**내용:** {complaint['content']}")
    
    if user['role'] in ['teacher', 'admin'] and complaint['status'] != '완료':
        new_status = st.selectbox(
            "상태 변경",
            ['대기중', '처리중', '완료'],
            index=['대기중', '처리중', '완료'].index(complaint['status']),
            key=f"status_{complaint['id']}"
        )
        note = st.text_input("처리 메모", key=f"note_{complaint['id']}")
        
        if st.button(f"상태 업데이트", key=f"update_{complaint['id']}"):
            complaint_sys.update_complaint_status(complaint['id'], new_status, note)
            st.success("상태가 업데이트되었습니다!")
            st.rerun()

def render_complaint_system():
    """민원 시스템 메인 페이지"""
    auth = st.session_state.auth_system
    complaint_sys = st.session_state.complaint_system
    
    user = st.session_state.current_user
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**👤 {user['name']}** ({USER_ROLES[user['role']]['display_name']})")
    with col2:
        if st.button("로그아웃"):
            auth.logout()
    
    st.markdown("---")
    
    if user['role'] == 'admin':
        render_admin_management()
        st.markdown("---")
    
    if user['role'] == 'parent':
        st.subheader("📝 민원 등록")
        
        with st.form("complaint_form"):
            title = st.text_input("제목")
            content = st.text_area("내용")
            category = st.selectbox("카테고리", 
                                  list(COMPLAINT_CATEGORIES.keys()),
                                  format_func=lambda x: COMPLAINT_CATEGORIES[x])
            urgency = st.radio("긴급도", ['보통', '긴급'], horizontal=True)
            
            submit = st.form_submit_button("민원 등록")
            
            if submit and title and content:
                complaint_id = complaint_sys.create_complaint(title, content, category, urgency, user['id'])
                st.success(f"민원이 등록되었습니다! (번호: {complaint_id})")
                st.rerun()
    
    st.subheader("📋 민원 목록")
    complaints = auth.list_complaints(user)
    
    if complaints:
        active_complaints = [c for c in complaints if c['status'] != '완료']
        completed_complaints = [c for c in complaints if c['status'] == '완료']
        
        if completed_complaints:
            tab1, tab2 = st.tabs([f"📥 진행 중 ({len(active_complaints)})", f"✅ 처리 완료 ({len(completed_complaints)})"])
        else:
            tab1 = st.tabs([f"📥 진행 중 ({len(active_complaints)})"])[0]
            tab2 = None
        
        with tab1:
            if active_complaints:
                urgent_complaints = [c for c in active_complaints if c['urgency'] == '긴급']
                normal_complaints = [c for c in active_complaints if c['urgency'] == '보통']
                
                urgent_complaints.sort(key=lambda x: x['created_at'])
                normal_complaints.sort(key=lambda x: x['created_at'])
                
                if urgent_complaints:
                    st.markdown("#### 🚨 긴급 민원")
                    for complaint in urgent_complaints:
                        with st.expander(f"[{complaint['id']}] {complaint['title']} - {complaint['status']} 🚨"):
                            render_complaint_details(complaint, user, complaint_sys)
                    
                    if normal_complaints:
                        st.markdown("---")
                
                if normal_complaints:
                    st.markdown("#### 📝 보통 민원")
                    for complaint in normal_complaints:
                        with st.expander(f"[{complaint['id']}] {complaint['title']} - {complaint['status']}"):
                            render_complaint_details(complaint, user, complaint_sys)
                
                if not urgent_complaints and not normal_complaints:
                    st.info("진행 중인 민원이 없습니다.")
            else:
                st.info("진행 중인 민원이 없습니다.")
        
        if tab2:
            with tab2:
                if completed_complaints:
                    completed_complaints.sort(key=lambda x: x['history'][-1]['timestamp'], reverse=True)
                    
                    for complaint in completed_complaints:
                        with st.expander(f"[{complaint['id']}] {complaint['title']} - ✅ 완료"):
                            st.write(f"**카테고리:** {COMPLAINT_CATEGORIES.get(complaint['category'], complaint['category'])}")
                            st.write(f"**긴급도:** {complaint['urgency']}")
                            st.write(f"**등록자:** {complaint['created_by']}")
                            st.write(f"**등록일:** {complaint['created_at'][:19]}")
                            if complaint['assigned_to']:
                                st.write(f"**담당자:** {complaint['assigned_to']}")
                            
                            completed_history = [h for h in complaint['history'] if h['status'] == '완료']
                            if completed_history:
                                st.write(f"**완료일:** {completed_history[-1]['timestamp'][:19]}")
                                if completed_history[-1]['note']:
                                    st.write(f"**완료 메모:** {completed_history[-1]['note']}")
                            
                            st.write(f"**내용:** {complaint['content']}")
                            
                            st.markdown("**📜 처리 이력:**")
                            for i, history in enumerate(complaint['history']):
                                st.write(f"&nbsp;&nbsp;{i+1}. **{history['status']}** - {history['timestamp'][:19]}")
                                if history['note']:
                                    st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;📝 {history['note']}")
                else:
                    st.info("완료된 민원이 없습니다.")
    else:
        st.info("등록된 민원이 없습니다.")

def main():
    st.set_page_config(
        page_title="학교 민원처리시스템",
        page_icon="🏫",
        layout="wide"
    )
    
    # Firebase 및 시스템 초기화
    if 'firebase_manager' not in st.session_state:
        st.session_state.firebase_manager = FirebaseManager()
    
    if 'auth_system' not in st.session_state:
        st.session_state.auth_system = AuthSystem(st.session_state.firebase_manager)
    
    if 'complaint_system' not in st.session_state:
        st.session_state.complaint_system = ComplaintSystem(st.session_state.firebase_manager)
    
    if not st.session_state.get('is_logged_in', False):
        render_auth_page()
    else:
        render_complaint_system()

if __name__ == "__main__":
    main()
