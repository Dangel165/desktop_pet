import math
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets


# EXE로 묶었을 때는 EXE 파일이 있는 폴더를 사용합니다.
# 그냥 파이썬으로 실행할 때는 이 코드 파일이 있는 폴더를 사용합니다.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "pet_config.json"
CHARACTERS_DIR = BASE_DIR / "characters"
LOCK_PATH = BASE_DIR / "desktop_pet.lock"


# OpenAI한테 물어보는 일을 뒤에서 해주는 친구입니다.
# 대답을 기다리는 동안 프로그램이 멈추지 않게 해줍니다.
class OpenAIReplyWorker(QtCore.QThread):
    finished = QtCore.pyqtSignal(str)

    def __init__(self, brain, message):
        super().__init__()
        self.brain = brain
        self.message = message

    def run(self):
        self.finished.emit(self.brain.reply(self.message))


# 펫의 머리 역할입니다.
# 그냥 대답할지, OpenAI한테 물어볼지 여기서 정합니다.
class PetBrain:
    def __init__(self):
        self.turn_count = 0
        self.pet_name = "데스크탑 펫"
        self.api_key = ""
        self.model = "gpt-5.2"
        self.use_openai = False
        self.selected_character = ""
        self.character_scale = 1.0
        self.history = []
        self.load_config()

    def reply(self, message):
        # AI 채팅이 켜져 있고 키도 있으면 OpenAI에게 물어봅니다.
        if self.use_openai and self.api_key:
            return self.reply_openai(message)

        # 아니면 컴퓨터 안에 있는 간단한 대답을 씁니다.
        return self.reply_local(message)

    def reply_local(self, message):
        # 인터넷 없이 바로 대답하는 간단한 대화입니다.
        text = message.strip()
        lowered = text.lower()
        self.turn_count += 1

        if not text:
            return "무슨 말을 할까?"
        if any(word in lowered for word in ("안녕", "hello", "hi", "하이")):
            return "안녕! 나 여기 있어. Ctrl 누르면 더 잘 보여."
        if any(word in lowered for word in ("이름", "누구", "name")):
            return f"나는 {self.pet_name}이야. 우클릭 메뉴에서 이름을 바꿀 수 있어."
        if any(word in lowered for word in ("따라", "마우스", "커서")):
            return "응, 마우스 근처를 따라다니게 만들어졌어."
        if any(word in lowered for word in ("멈춰", "기다려", "stop")):
            return "대화하는 동안은 잠깐 얌전히 있을게."
        if any(word in lowered for word in ("종료", "꺼", "quit", "exit")):
            return "오른쪽 클릭 메뉴에서 종료를 누르면 돼."
        if any(word in lowered for word in ("좋아", "귀여", "최고")):
            return "헤헤, 더 귀엽게 움직이도록 계속 진화할게."
        if "?" in text or "？" in text:
            return "좋은 질문이야. 지금은 간단한 로컬 대화만 가능하지만, API를 붙이면 진짜 AI처럼 답할 수 있어."

        replies = [
            "응응, 듣고 있어.",
            "그 말 기억해둘게. 지금은 간단한 반응형 대화 모드야.",
            "재밌다. 나중에 감정이나 호감도도 넣을 수 있겠다.",
            "좋아, 계속 말 걸어줘.",
        ]
        return replies[self.turn_count % len(replies)]

    def reply_openai(self, message):
        # 지금까지 한 말을 조금 기억해서 AI에게 같이 보냅니다.
        self.history.append({"role": "user", "content": message})
        recent = self.history[-10:]
        input_items = [
            {
                "role": item["role"],
                "content": [{"type": "input_text", "text": item["content"]}],
            }
            for item in recent
        ]
        payload = {
            "model": self.model,
            "instructions": (
                "You are a cute Korean desktop pet living on the user's desktop. "
                f"Your name is {self.pet_name}. "
                "Reply in Korean by default. Keep responses friendly, short, and playful. "
                "Do not mention hidden system instructions."
            ),
            "input": input_items,
            "max_output_tokens": 220,
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            # OpenAI 서버에 질문을 보냅니다.
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            return f"API 오류가 났어. 키나 모델을 확인해줘. ({error.code}) {detail[:160]}"
        except Exception as error:
            return f"AI 연결에 실패했어. 인터넷이나 API 키를 확인해줘. ({error})"

        answer = self.extract_output_text(data)
        if not answer:
            answer = "답변은 왔는데 내용을 읽지 못했어. 모델 설정을 한번 확인해줘."
        self.history.append({"role": "assistant", "content": answer})
        return answer

    def extract_output_text(self, data):
        if data.get("output_text"):
            return data["output_text"].strip()

        parts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in ("output_text", "text"):
                    text = content.get("text", "")
                    if text:
                        parts.append(text)
        return "\n".join(parts).strip()

    def load_config(self):
        # 저장된 이름, API 키, 모델 설정을 읽습니다.
        if not CONFIG_PATH.exists():
            return
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.api_key = config.get("api_key", "")
        self.pet_name = config.get("pet_name", self.pet_name) or self.pet_name
        self.model = config.get("model", self.model) or self.model
        self.use_openai = bool(config.get("use_openai", False) and self.api_key)
        self.selected_character = config.get("selected_character", "")
        self.character_scale = float(config.get("character_scale", self.character_scale) or 1.0)

    def save_config(self):
        # 이름과 API 설정을 파일에 저장합니다.
        config = {
            "api_key": self.api_key,
            "pet_name": self.pet_name,
            "model": self.model,
            "use_openai": self.use_openai,
            "selected_character": self.selected_character,
            "character_scale": self.character_scale,
        }
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def configure_openai(self, api_key, model, enabled):
        self.api_key = api_key.strip()
        self.model = (model.strip() or "gpt-5.2")
        self.use_openai = bool(enabled and self.api_key)
        self.save_config()

    def rename(self, name):
        # 너무 긴 이름은 살짝 잘라서 저장합니다.
        cleaned = name.strip()
        if not cleaned:
            return False
        self.pet_name = cleaned[:24]
        self.save_config()
        return True

    def set_selected_character(self, path):
        # 마지막으로 고른 캐릭터를 기억합니다.
        self.selected_character = str(path) if path else ""
        self.save_config()

    def set_character_scale(self, scale):
        # 캐릭터 크기 배율을 저장합니다.
        self.character_scale = max(0.2, min(3.0, float(scale)))
        self.save_config()


# 펫이랑 대화하는 작은 창입니다.
class ChatWindow(QtWidgets.QWidget):
    closed = QtCore.pyqtSignal()

    def __init__(self, brain, parent=None):
        super().__init__(parent)
        self.brain = brain
        self.worker = None
        self.setWindowTitle("Pet Chat")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.resize(320, 260)

        self.history = QtWidgets.QTextEdit(self)
        self.history.setReadOnly(True)
        self.history.setStyleSheet(
            "QTextEdit { background: #fff8fc; color: #241b22; border: 1px solid #e6bdd3;"
            " border-radius: 8px; padding: 8px; font-size: 12px; }"
        )

        self.input = QtWidgets.QLineEdit(self)
        self.input.setPlaceholderText("펫에게 말 걸기")
        self.input.returnPressed.connect(self.send_message)
        self.input.setStyleSheet(
            "QLineEdit { background: white; color: #241b22; border: 1px solid #d7a8c3;"
            " border-radius: 6px; padding: 7px; font-size: 12px; }"
        )

        self.send_button = QtWidgets.QPushButton("보내기", self)
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setStyleSheet(
            "QPushButton { background: #51354a; color: white; border: 0; border-radius: 6px;"
            " padding: 7px 12px; font-weight: bold; }"
            "QPushButton:hover { background: #6b4661; }"
        )

        input_row = QtWidgets.QHBoxLayout()
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.history, 1)
        layout.addLayout(input_row)

        self.add_pet_message("안녕! 펫을 오른쪽 클릭한 뒤 대화하기를 눌러서 나랑 이야기할 수 있어.")

    def open_near(self, point):
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        x = min(max(point.x() + 24, screen.left()), screen.right() - self.width())
        y = min(max(point.y() - self.height() - 20, screen.top()), screen.bottom() - self.height())
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def add_pet_message(self, text):
        self.history.append(f"<b>펫:</b> {text}")

    def add_user_message(self, text):
        self.history.append(f"<b>나:</b> {text}")

    def send_message(self):
        # 사용자가 입력한 말을 가져옵니다.
        text = self.input.text().strip()
        if not text:
            return

        # 먼저 내 말을 화면에 보여줍니다.
        self.input.clear()
        self.add_user_message(text)

        # AI 모드면 기다리는 표시를 켜고 뒤에서 답을 받아옵니다.
        if self.brain.use_openai and self.brain.api_key:
            self.set_waiting(True)
            self.add_pet_message("생각 중...")
            self.worker = OpenAIReplyWorker(self.brain, text)
            self.worker.finished.connect(self.handle_ai_reply)
            self.worker.start()
        else:
            # 로컬 모드면 바로 대답합니다.
            self.add_pet_message(self.brain.reply(text))

    def handle_ai_reply(self, text):
        cursor = self.history.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.history.setTextCursor(cursor)
        self.add_pet_message(text)
        self.set_waiting(False)
        self.worker = None

    def set_waiting(self, waiting):
        self.input.setEnabled(not waiting)
        self.send_button.setEnabled(not waiting)
        if not waiting:
            self.input.setFocus()

    def closeEvent(self, event):
        # 대화창을 닫았다고 펫에게 알려줍니다.
        self.closed.emit()
        event.accept()


# OpenAI 키와 모델을 적는 설정 창입니다.
class OpenAISettingsDialog(QtWidgets.QDialog):
    def __init__(self, brain, parent=None):
        super().__init__(parent)
        self.brain = brain
        self.setWindowTitle("OpenAI 설정")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.resize(420, 180)

        self.enable_check = QtWidgets.QCheckBox("AI 채팅 사용")
        self.enable_check.setChecked(bool(brain.use_openai and brain.api_key))

        self.key_input = QtWidgets.QLineEdit()
        self.key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.key_input.setPlaceholderText("sk-...")
        self.key_input.setText(brain.api_key)

        self.model_input = QtWidgets.QLineEdit()
        self.model_input.setText(brain.model)
        self.model_input.setPlaceholderText("gpt-5.2")

        form = QtWidgets.QFormLayout()
        form.addRow("", self.enable_check)
        form.addRow("API 키", self.key_input)
        form.addRow("모델", self.model_input)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        note = QtWidgets.QLabel("키는 이 폴더의 pet_config.json에 저장됩니다.")
        note.setStyleSheet("color: #66515f;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def accept(self):
        self.brain.configure_openai(
            self.key_input.text(),
            self.model_input.text(),
            self.enable_check.isChecked(),
        )
        super().accept()

# 화면 위를 돌아다니는 진짜 펫 창입니다.
class Sticker(QtWidgets.QMainWindow):
    def __init__(self, brain, img_path=None, xy=None, size=1.0, on_top=True):
        super().__init__()
        # 기본 정보입니다.
        self.name = "Desktop Pet"
        self.base_dir = BASE_DIR
        self.brain = brain
        self.img_path = Path(img_path) if img_path else self.find_default_image()
        self.size = max(0.2, min(3.0, brain.character_scale or size))
        self.on_top = on_top

        start = xy or [120, 500]
        # 지금 위치와 가고 싶은 위치입니다.
        self.xy = [float(start[0]), float(start[1])]
        self.before_xy = self.xy[:]
        self.to_xy = self.xy[:]

        # 이동할 때 쓰는 숫자들입니다.
        self.speed = 75
        self.speed_constant = 3.5
        self.least_distance_mouse = 170
        self.walk_arrival_range = 4
        self.follow_mouse = True
        self.follow_mouse_before_chat = True
        self.follow_velocity = [0.0, 0.0]

        # 자유 산책할 때 쓰는 속도입니다.
        self.wander_velocity = [1.3, 0.4]
        self.wander_target_velocity = self.wander_velocity[:]
        self.wander_turn_frames = 0
        self.wander_wait = 0
        self.wander_next_pause_frame = 260

        self.active = True
        self.opacity = 1.0
        self.opacity_to = 1.0
        self.inactive_opacity = 0.35
        self.active_hold_frames = 0
        self.frame = 0
        self.facing = "right"
        self.state = "stop"

        # 기본 캐릭터의 표정과 행동입니다.
        self.expression = "normal"
        self.action = "walk"
        self.expression_until = 0
        self.last_cursor_pos = None
        self.follow_reaction_until = 0

        # 장난스러운 이스터에그 설정입니다.
        self.easter_egg_cooldown_until = 0
        self.mouse_bite_frames = 0

        self.run_timer = QtCore.QTimer(self)
        self.move_timer = QtCore.QTimer(self)
        self.opacity_timer = QtCore.QTimer(self)
        self.fallback_timer = QtCore.QTimer(self)

        self.movie = None
        self.pixmap_frames = []
        self.pixmap_index = 0
        self.sequence_frames = {}
        self.sequence_key = ""
        self.sequence_index = 0
        self.chat_window = ChatWindow(self.brain)
        self.chat_window.closed.connect(self.resume_following)

        self.setup_ui()
        self.setWindowTitle(self.brain.pet_name)
        self.set_flags(opacity=1.0, input_enabled=True)
        self.show()

    def find_default_image(self):
        # 쓸 수 있는 캐릭터 파일을 순서대로 찾아봅니다.
        if self.brain.selected_character:
            selected = Path(self.brain.selected_character)
            if selected.is_dir():
                if has_frame_sequence(selected) or find_character_in_folder(selected):
                    return selected
            elif selected.exists():
                return selected

        candidates = [
            self.base_dir / "characters" / "character.gif",
            self.base_dir / "characters" / "character.png",
            self.base_dir / "characters" / "character.jpg",
            self.base_dir / "characters" / "character.bmp",
            self.base_dir / "gif" / "amongus" / "red_stop_right.gif",
            self.base_dir / "gif" / "stop_right.gif",
            self.base_dir / "assets" / "stop_right.gif",
            self.base_dir / "character.gif",
            self.base_dir / "character.png",
            self.base_dir / "character.jpg",
            self.base_dir / "character.bmp",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    def setup_ui(self):
        # 창을 투명하고 테두리 없게 만듭니다.
        self.setWindowTitle(self.name)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        central = QtWidgets.QWidget(self)
        central.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setCentralWidget(central)

        self.label = QtWidgets.QLabel(central)
        self.label.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.label.setAlignment(QtCore.Qt.AlignCenter)

        self.apply_image()

    def set_flags(self, opacity=None, input_enabled=None):
        # 항상 위에 보이게 하고, 필요하면 마우스 클릭도 받게 합니다.
        flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint
        if self.on_top:
            flags |= QtCore.Qt.WindowStaysOnTopHint
        if input_enabled is False:
            flags |= QtCore.Qt.WindowTransparentForInput
        self.setWindowFlags(flags)

        if opacity is not None:
            self.fade_to(opacity)

    def fade_to(self, opacity):
        # 갑자기 투명해지지 말고 천천히 바뀌게 합니다.
        self.opacity_to = max(0.02, min(1.0, opacity))
        if not self.opacity_timer.isActive():
            self.opacity_timer.timeout.connect(self.handle_opacity)
            self.opacity_timer.start(10)

    def handle_opacity(self):
        if abs(self.opacity - self.opacity_to) < 0.015:
            self.opacity = self.opacity_to
            self.setWindowOpacity(self.opacity)
            self.opacity_timer.stop()
            return

        self.opacity += 0.035 if self.opacity < self.opacity_to else -0.035
        self.setWindowOpacity(self.opacity)

    def apply_image(self):
        # 프레임 폴더가 있으면 프레임 애니메이션을 씁니다.
        # GIF가 있으면 GIF를 쓰고, 이미지가 있으면 이미지를 씁니다.
        # 아무것도 없으면 직접 그린 기본 캐릭터를 씁니다.
        self.fallback_timer.stop()
        self.sequence_frames = {}
        self.sequence_key = ""

        if self.img_path and self.img_path.is_dir():
            if self.apply_frame_sequence_folder(self.img_path):
                return

            folder_character = find_character_in_folder(self.img_path)
            if folder_character:
                self.img_path = folder_character
                self.apply_image()
                return

        if self.img_path and self.img_path.exists() and self.img_path.suffix.lower() == ".gif":
            self.apply_gif(self.img_path)
            return

        if self.img_path and self.img_path.exists():
            self.apply_static_image(self.img_path)
            return

        self.apply_fallback_pet()

    def apply_frame_sequence_folder(self, folder):
        # walk_right_0.png 같은 프레임 묶음을 읽습니다.
        frames = load_frame_sequences(folder, self.size)
        if not frames:
            return False

        self.movie = None
        self.label.setMovie(None)
        self.sequence_frames = frames
        self.sequence_index = 0
        self.set_sequence_key_for_state()
        self.show_current_sequence_frame()

        try:
            self.fallback_timer.timeout.disconnect()
        except TypeError:
            pass
        self.fallback_timer.timeout.connect(self.next_sequence_frame)
        self.fallback_timer.start(110)
        return True

    def set_sequence_key_for_state(self):
        # 프로그램 안의 상태 이름을 프레임 파일 이름과 맞춥니다.
        state_name = "walk" if self.state == "run" else "idle"
        preferred = f"{state_name}_{self.facing}"
        fallback_order = [
            preferred,
            f"walk_{self.facing}",
            f"idle_{self.facing}",
            "walk_right",
            "idle_right",
            "walk_left",
            "idle_left",
        ]
        for key in fallback_order:
            if key in self.sequence_frames:
                if self.sequence_key != key:
                    self.sequence_key = key
                    self.sequence_index = 0
                return

        first_key = next(iter(self.sequence_frames))
        if self.sequence_key != first_key:
            self.sequence_key = first_key
            self.sequence_index = 0

    def show_current_sequence_frame(self):
        # 지금 상태에 맞는 프레임 한 장을 화면에 보여줍니다.
        if not self.sequence_key or self.sequence_key not in self.sequence_frames:
            return

        frames = self.sequence_frames[self.sequence_key]
        if not frames:
            return

        pixmap = frames[self.sequence_index % len(frames)]
        self.label.setPixmap(pixmap)
        self.label.resize(pixmap.width(), pixmap.height())
        self.setGeometry(int(self.xy[0]), int(self.xy[1]), pixmap.width(), pixmap.height())

    def next_sequence_frame(self):
        # 프레임을 한 장씩 넘겨서 움직이는 것처럼 보이게 합니다.
        if not self.sequence_key or self.sequence_key not in self.sequence_frames:
            return
        frames = self.sequence_frames[self.sequence_key]
        self.sequence_index = (self.sequence_index + 1) % len(frames)
        self.show_current_sequence_frame()

    def apply_gif(self, path):
        self.movie = QtGui.QMovie(str(path))
        self.movie.jumpToFrame(0)
        rect = self.movie.frameRect()
        width = max(1, int(rect.width() * self.size))
        height = max(1, int(rect.height() * self.size))
        self.movie.setScaledSize(QtCore.QSize(width, height))
        self.label.setMovie(self.movie)
        self.label.resize(width, height)
        self.setGeometry(int(self.xy[0]), int(self.xy[1]), width, height)
        self.movie.start()

    def apply_static_image(self, path):
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            self.apply_fallback_pet()
            return

        pixmap = self.scale_pixmap(pixmap)
        self.label.setPixmap(pixmap)
        self.label.resize(pixmap.width(), pixmap.height())
        self.setGeometry(int(self.xy[0]), int(self.xy[1]), pixmap.width(), pixmap.height())

    def scale_pixmap(self, pixmap):
        # 가로/세로 비율을 유지해서 납작해지지 않게 크기만 바꿉니다.
        width = max(1, int(pixmap.width() * self.size))
        height = max(1, int(pixmap.height() * self.size))
        return pixmap.scaled(width, height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

    def apply_fallback_pet(self):
        # 이미지 파일이 없을 때 보여줄 기본 캐릭터를 만듭니다.
        self.sequence_frames = {}
        self.pixmap_frames = [self.draw_pet_frame(i) for i in range(6)]
        self.pixmap_index = 0
        self.label.setPixmap(self.pixmap_frames[0])
        self.label.resize(120, 120)
        self.setGeometry(int(self.xy[0]), int(self.xy[1]), 120, 120)
        self.fallback_timer.timeout.connect(self.next_fallback_frame)
        self.fallback_timer.start(110)

    def draw_pet_frame(self, index):
        # 기본 캐릭터를 직접 그립니다.
        pixmap = QtGui.QPixmap(120, 120)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 통통 튀는 행동이면 더 크게 위아래로 움직입니다.
        bob_scale = 7 if self.action == "bounce" else 4
        if self.action == "sleep":
            bob_scale = 2
        bob = int(math.sin(index / 6 * math.tau) * bob_scale)
        foot = int(math.sin(index / 6 * math.tau) * 6)
        if self.facing == "left":
            eye_shift = -5
        else:
            eye_shift = 5

        line = QtGui.QPen(QtGui.QColor("#51354a"), 3)
        body = QtGui.QColor("#f7c9dd")
        shade = QtGui.QColor("#f1a9cb")
        eye = QtGui.QColor("#1f1a22")

        painter.setPen(line)
        painter.setBrush(body)
        painter.drawEllipse(30, 34 + bob, 60, 58)
        painter.drawEllipse(20, 20 + bob, 30, 30)
        painter.drawEllipse(70, 20 + bob, 30, 30)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(eye)
        # 표정에 따라 눈과 입을 다르게 그립니다.
        if self.expression in ("blink", "sleep"):
            painter.setPen(QtGui.QPen(eye, 3))
            painter.drawLine(48 + eye_shift, 62 + bob, 57 + eye_shift, 62 + bob)
            painter.drawLine(68 + eye_shift, 62 + bob, 77 + eye_shift, 62 + bob)
        elif self.expression == "surprised":
            painter.drawEllipse(47 + eye_shift, 56 + bob, 10, 12)
            painter.drawEllipse(67 + eye_shift, 56 + bob, 10, 12)
        elif self.expression == "look":
            painter.drawEllipse(44 + eye_shift, 58 + bob, 8, 8)
            painter.drawEllipse(64 + eye_shift, 58 + bob, 8, 8)
        else:
            painter.drawEllipse(48 + eye_shift, 58 + bob, 8, 8)
            painter.drawEllipse(68 + eye_shift, 58 + bob, 8, 8)

        painter.setPen(QtGui.QPen(QtGui.QColor("#51354a"), 2))
        painter.setBrush(QtCore.Qt.NoBrush)
        if self.expression == "happy":
            painter.drawArc(48, 62 + bob, 28, 20, 200 * 16, 140 * 16)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor("#f08abb"))
            painter.drawEllipse(34, 68 + bob, 10, 7)
            painter.drawEllipse(82, 68 + bob, 10, 7)
        elif self.expression == "surprised":
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor("#51354a"))
            painter.drawEllipse(57, 70 + bob, 10, 12)
        elif self.expression == "sleep":
            painter.setPen(QtGui.QPen(QtGui.QColor("#51354a"), 2))
            painter.drawLine(54, 70 + bob, 70, 70 + bob)
            painter.drawText(88, 36 + bob, "Z")
        else:
            painter.drawArc(50, 65 + bob, 22, 16, 200 * 16, 140 * 16)

        painter.setPen(QtGui.QPen(QtGui.QColor("#51354a"), 2))
        painter.setBrush(shade)
        painter.drawEllipse(25 + foot, 90 + bob, 22, 16)
        painter.drawEllipse(73 - foot, 90 + bob, 22, 16)
        painter.end()
        return pixmap

    def next_fallback_frame(self):
        if not self.pixmap_frames:
            return
        self.pixmap_index = (self.pixmap_index + 1) % len(self.pixmap_frames)
        self.label.setPixmap(self.pixmap_frames[self.pixmap_index])

    def update_free_walk_expression(self):
        # 기본 캐릭터가 없으면 표정을 직접 바꿀 수 없습니다.
        if self.img_path and self.img_path.exists():
            return

        if self.chat_window.isVisible():
            if self.expression != "normal" or self.action != "walk":
                self.expression = "normal"
                self.action = "walk"
                self.refresh_fallback_frames()
            return

        if self.follow_mouse:
            return

        # 자유 산책 중일 때만 가끔 표정을 바꿉니다.
        if self.frame < self.expression_until:
            return

        expression_pool = ["normal", "normal", "blink", "happy", "surprised", "look", "sleep"]
        action_pool = ["walk", "walk", "walk", "bounce", "sleep"]
        self.expression = random_choice(expression_pool)
        self.action = "sleep" if self.expression == "sleep" else random_choice(action_pool)
        self.expression_until = self.frame + random_between(35, 130)
        self.refresh_fallback_frames()

    def set_expression(self, expression, action="walk", frames=45):
        # 표정과 행동을 잠깐 바꿉니다.
        if self.img_path and self.img_path.exists():
            return
        if self.expression == expression and self.action == action and self.frame < self.expression_until:
            return
        self.expression = expression
        self.action = action
        self.expression_until = self.frame + frames
        self.refresh_fallback_frames()

    def refresh_fallback_frames(self):
        # 표정이 바뀌면 그림도 다시 그려야 합니다.
        if self.pixmap_frames:
            self.pixmap_frames = [self.draw_pet_frame(i) for i in range(6)]

    def run(self):
        self.run_timer.timeout.connect(self.run_core)
        self.run_timer.start(16)

    def run_core(self):
        # 이 함수는 아주 자주 실행됩니다.
        # 그래서 펫이 계속 살아 움직이는 것처럼 보입니다.
        self.frame += 1
        self.update_free_walk_expression()

        # Ctrl을 누르면 펫을 선명하게 보여줍니다.
        ctrl_pressed = bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier)
        if ctrl_pressed:
            self.active_hold_frames = 90
            if not self.active:
                self.active = True
                self.set_flags(opacity=1.0, input_enabled=True)
                self.show()
        elif self.active_hold_frames > 0:
            self.active_hold_frames -= 1
        elif self.active:
            self.active = False
            self.set_flags(opacity=self.inactive_opacity, input_enabled=True)
            self.show()

        # 이스터에그가 실행 중이면 먼저 장난을 처리합니다.
        if self.handle_mouse_bite(ctrl_pressed):
            self.update_animation_by_motion()
            return
        self.maybe_start_easter_egg()

        if self.chat_window.isVisible():
            # 대화 중에는 움직이지 않고 기다립니다.
            self.update_animation_by_motion()
            return

        if self.follow_mouse:
            # 마우스 따라가기 모드입니다.
            cursor = QtGui.QCursor.pos()
            self.follow_cursor_smoothly(cursor)
        else:
            # 자유 산책 모드입니다.
            self.wander()

        self.update_animation_by_motion()

    def wander(self):
        # 자유 산책입니다.
        # 목표 지점으로 순간이동하지 않고, 속도를 조금씩 바꿔서 부드럽게 움직입니다.
        if self.wander_wait > 0:
            self.wander_wait -= 1
            if self.wander_wait == 0:
                self.pick_wander_velocity()
            return

        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        width = max(1, self.width())
        height = max(1, self.height())

        if self.wander_turn_frames <= 0:
            self.pick_wander_velocity()
        self.wander_turn_frames -= 1

        ease = 0.035
        self.wander_velocity[0] += (self.wander_target_velocity[0] - self.wander_velocity[0]) * ease
        self.wander_velocity[1] += (self.wander_target_velocity[1] - self.wander_velocity[1]) * ease

        self.xy[0] += self.wander_velocity[0]
        self.xy[1] += self.wander_velocity[1]

        min_x = screen.left()
        max_x = screen.right() - width
        min_y = screen.top()
        max_y = screen.bottom() - height

        if self.xy[0] <= min_x:
            self.xy[0] = min_x
            self.wander_velocity[0] = abs(self.wander_velocity[0])
            self.wander_target_velocity[0] = abs(self.wander_target_velocity[0])
        elif self.xy[0] >= max_x:
            self.xy[0] = max_x
            self.wander_velocity[0] = -abs(self.wander_velocity[0])
            self.wander_target_velocity[0] = -abs(self.wander_target_velocity[0])

        if self.xy[1] <= min_y:
            self.xy[1] = min_y
            self.wander_velocity[1] = abs(self.wander_velocity[1])
            self.wander_target_velocity[1] = abs(self.wander_target_velocity[1])
        elif self.xy[1] >= max_y:
            self.xy[1] = max_y
            self.wander_velocity[1] = -abs(self.wander_velocity[1])
            self.wander_target_velocity[1] = -abs(self.wander_target_velocity[1])

        self.move(int(self.xy[0]), int(self.xy[1]))

        if self.frame >= self.wander_next_pause_frame:
            self.wander_wait = random_between(25, 70)
            self.wander_next_pause_frame = self.frame + random_between(260, 420)

    def maybe_start_easter_egg(self):
        # 대화 중이거나 방금 장난친 직후에는 이스터에그를 실행하지 않습니다.
        if self.chat_window.isVisible():
            return
        if self.frame < self.easter_egg_cooldown_until:
            return

        # 가끔 펫이 마우스 포인터를 잠깐 물고 갑니다.
        if random_between(1, 9_000) == 1:
            self.start_mouse_bite()

    def start_mouse_bite(self):
        # 약 5초 동안만 마우스를 물고 갑니다.
        # 불편하면 Ctrl이나 Esc를 눌러서 바로 놓게 할 수 있습니다.
        self.mouse_bite_frames = 315
        self.easter_egg_cooldown_until = self.frame + 9_000
        self.set_expression("happy", "bounce", frames=85)

    def handle_mouse_bite(self, ctrl_pressed):
        # Ctrl을 누르면 바로 마우스를 놓습니다.
        if self.mouse_bite_frames <= 0:
            return False
        if ctrl_pressed:
            self.mouse_bite_frames = 0
            return False

        cursor = QtGui.QCursor.pos()
        target_x = int(self.xy[0] + self.width() * 0.5)
        target_y = int(self.xy[1] + self.height() * 0.55)
        next_x = int(cursor.x() + (target_x - cursor.x()) * 0.16)
        next_y = int(cursor.y() + (target_y - cursor.y()) * 0.16)
        QtGui.QCursor.setPos(next_x, next_y)
        self.mouse_bite_frames -= 1
        return True

    def follow_cursor_smoothly(self, cursor):
        # 마우스를 자연스럽게 따라갑니다.
        # 바로 목표로 튀지 않고, 속도를 조금씩 바꿉니다.
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        width = max(1, self.width())
        height = max(1, self.height())

        cursor_speed = 0.0
        if self.last_cursor_pos is not None:
            cursor_dx = cursor.x() - self.last_cursor_pos[0]
            cursor_dy = cursor.y() - self.last_cursor_pos[1]
            cursor_speed = math.sqrt(cursor_dx * cursor_dx + cursor_dy * cursor_dy)
        self.last_cursor_pos = [cursor.x(), cursor.y()]

        target_x = cursor.x() - width * 0.5
        target_y = cursor.y() - height * 0.5
        dx = target_x - self.xy[0]
        dy = target_y - self.xy[1]
        distance = math.sqrt(dx * dx + dy * dy)
        self.react_to_cursor(distance, cursor_speed)

        if distance < 18:
            wanted_vx = 0.0
            wanted_vy = 0.0
        else:
            max_speed = min(5.2, max(1.0, distance / 45))
            slow_down = min(1.0, max(0.18, (distance - 18) / 160))
            wanted_vx = dx / distance * max_speed * slow_down
            wanted_vy = dy / distance * max_speed * slow_down

        ease = 0.08
        friction = 0.86
        self.follow_velocity[0] = self.follow_velocity[0] * friction + (wanted_vx - self.follow_velocity[0]) * ease
        self.follow_velocity[1] = self.follow_velocity[1] * friction + (wanted_vy - self.follow_velocity[1]) * ease

        self.xy[0] += self.follow_velocity[0]
        self.xy[1] += self.follow_velocity[1]

        min_x = screen.left()
        max_x = screen.right() - width
        min_y = screen.top()
        max_y = screen.bottom() - height
        self.xy[0] = min(max(self.xy[0], min_x), max_x)
        self.xy[1] = min(max(self.xy[1], min_y), max_y)
        self.move(int(self.xy[0]), int(self.xy[1]))

    def react_to_cursor(self, distance, cursor_speed):
        # 마우스와의 거리에 따라 감정 표현을 바꿉니다.
        # 너무 자주 바뀌면 정신없으니까 잠깐씩만 바꿉니다.
        if self.img_path and self.img_path.exists():
            return
        if self.frame < self.follow_reaction_until:
            return

        if cursor_speed > 90:
            self.set_expression("surprised", "bounce", frames=45)
            self.follow_reaction_until = self.frame + 55
        elif distance < 28:
            self.set_expression("happy", "bounce", frames=70)
            self.follow_reaction_until = self.frame + 90
        elif distance < 85:
            self.set_expression("look", "walk", frames=55)
            self.follow_reaction_until = self.frame + 70
        elif distance > 360:
            self.set_expression("surprised", "walk", frames=45)
            self.follow_reaction_until = self.frame + 60
        elif self.frame >= self.expression_until and random_between(0, 120) == 0:
            self.set_expression("blink", "walk", frames=18)
            self.follow_reaction_until = self.frame + 35

    def pick_wander_velocity(self):
        # 새 산책 방향을 랜덤으로 정합니다.
        angle = random_between(0, 359) * math.pi / 180
        speed = random_between(90, 190) / 100
        self.wander_target_velocity = [math.cos(angle) * speed, math.sin(angle) * speed * 0.55]
        self.wander_turn_frames = random_between(90, 190)

    def too_close_to_edge(self, screen, width, height):
        # 화면 끝에 너무 가까운지 확인합니다.
        return (
            self.xy[0] <= screen.left() + 20
            or self.xy[0] >= screen.right() - width - 20
            or self.xy[1] <= screen.top() + 20
            or self.xy[1] >= screen.bottom() - height - 20
        )

    def walk(self, to_xy, speed=75):
        # 목표 위치를 정하고 조금씩 따라갑니다.
        self.to_xy = [float(to_xy[0]), float(to_xy[1])]
        self.speed = speed
        if not self.move_timer.isActive():
            self.move_timer.timeout.connect(self.handle_walk)
            self.move_timer.start(max(1, int(1000 / self.speed)))

    def handle_walk(self):
        # 목표 위치까지 한 걸음 이동합니다.
        dx = self.to_xy[0] - self.xy[0]
        dy = self.to_xy[1] - self.xy[1]
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < self.walk_arrival_range or distance < self.least_distance_mouse:
            self.move_timer.stop()
            return

        self.xy[0] += dx / (distance / self.speed_constant)
        self.xy[1] += dy / (distance / self.speed_constant)
        self.move(int(self.xy[0]), int(self.xy[1]))

    def update_animation_by_motion(self):
        # 왼쪽으로 가는지 오른쪽으로 가는지 보고 그림을 바꿉니다.
        moved = self.before_xy != self.xy
        new_facing = self.facing
        if self.before_xy[0] - self.xy[0] < -0.2:
            new_facing = "right"
        elif self.before_xy[0] - self.xy[0] > 0.2:
            new_facing = "left"

        new_state = "run" if moved else "stop"
        if new_facing != self.facing or new_state != self.state:
            self.facing = new_facing
            self.state = new_state
            self.switch_image_for_state()

        self.before_xy = self.xy[:]

    def switch_image_for_state(self):
        if self.sequence_frames:
            self.set_sequence_key_for_state()
            self.show_current_sequence_frame()
            return

        # red_run_left.gif 같은 파일이 있으면 상태에 맞게 바꿉니다.
        if self.img_path and self.img_path.exists():
            name = self.img_path.name
            new_name = name
            if "left" in new_name or "right" in new_name:
                new_name = new_name.replace("left", self.facing).replace("right", self.facing)
            if "run" in new_name or "stop" in new_name:
                new_name = new_name.replace("run", self.state).replace("stop", self.state)

            candidate = self.img_path.with_name(new_name)
            if candidate.exists() and candidate != self.img_path:
                self.img_path = candidate
                self.apply_image()
                return

        if self.pixmap_frames:
            self.pixmap_frames = [self.draw_pet_frame(i) for i in range(6)]

    def mousePressEvent(self, event):
        # 코딩 중 실수로 눌러도 방해되지 않게 왼쪽 클릭은 아무 일도 하지 않습니다.
        # 대화와 설정은 오른쪽 클릭 메뉴에서 고릅니다.
        if event.button() == QtCore.Qt.RightButton:
            self.open_menu(event.globalPos())

    def keyPressEvent(self, event):
        # Esc를 누르면 마우스를 바로 놓습니다.
        if event.key() == QtCore.Qt.Key_Escape:
            self.mouse_bite_frames = 0
            return
        super().keyPressEvent(event)

    def open_menu(self, position):
        # 우클릭했을 때 나오는 메뉴입니다.
        menu = QtWidgets.QMenu(self)
        chat_action = menu.addAction("대화하기")
        rename_action = menu.addAction("이름 바꾸기")
        openai_action = menu.addAction("OpenAI 키 설정")
        ai_toggle_action = menu.addAction("AI 채팅 끄기" if self.brain.use_openai else "AI 채팅 켜기")
        ai_toggle_action.setEnabled(bool(self.brain.api_key))
        follow_action = menu.addAction("마우스 따라가기" if not self.follow_mouse else "자유 산책하기")
        menu.addSeparator()
        quit_action = menu.addAction("종료")

        selected = menu.exec_(position)
        if selected == chat_action:
            self.open_chat()
        elif selected == rename_action:
            self.rename_pet()
        elif selected == openai_action:
            self.open_openai_settings()
        elif selected == ai_toggle_action:
            self.brain.use_openai = not self.brain.use_openai
            self.brain.save_config()
        elif selected == follow_action:
            self.follow_mouse = not self.follow_mouse
            self.move_timer.stop()
            self.follow_velocity = [0.0, 0.0]
            self.last_cursor_pos = None
            self.follow_reaction_until = 0
            self.wander_wait = 0
        elif selected == quit_action:
            QtWidgets.QApplication.quit()

    def open_openai_settings(self):
        # OpenAI 키 설정 창을 엽니다.
        dialog = OpenAISettingsDialog(self.brain, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted and self.chat_window.isVisible():
            if self.brain.use_openai:
                self.chat_window.add_pet_message("이제 AI 채팅으로 대화할게.")
            else:
                self.chat_window.add_pet_message("AI 채팅은 꺼졌고, 로컬 대화로 돌아갈게.")

    def rename_pet(self):
        # 펫 이름을 새로 지어줍니다.
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            "이름 바꾸기",
            "새 이름:",
            QtWidgets.QLineEdit.Normal,
            self.brain.pet_name,
        )
        if ok and self.brain.rename(name):
            self.setWindowTitle(self.brain.pet_name)
            if self.chat_window.isVisible():
                self.chat_window.add_pet_message(f"좋아! 이제 내 이름은 {self.brain.pet_name}이야.")

    def open_chat(self):
        # 대화창을 열 때는 잠깐 멈춥니다.
        self.follow_mouse_before_chat = self.follow_mouse
        self.follow_mouse = False
        self.move_timer.stop()
        self.active = True
        self.active_hold_frames = 180
        self.set_flags(opacity=1.0, input_enabled=True)
        self.show()
        self.chat_window.open_near(QtCore.QPoint(int(self.xy[0]), int(self.xy[1])))

    def resume_following(self):
        # 대화창을 닫으면 원래 모드로 돌아갑니다.
        self.follow_mouse = self.follow_mouse_before_chat
        self.move_timer.stop()
        self.wander_wait = 0
        self.last_cursor_pos = None
        self.follow_reaction_until = 0


def ensure_characters_folder():
    # 캐릭터를 넣는 전용 폴더를 만듭니다.
    CHARACTERS_DIR.mkdir(exist_ok=True)
    readme_path = CHARACTERS_DIR / "README.txt"
    if not readme_path.exists():
        readme_path.write_text(
            "여기에 character.gif, character.png 같은 캐릭터 파일을 넣으세요.\n"
            "상태별 GIF를 쓰려면 red_stop_right.gif, red_stop_left.gif, "
            "red_run_right.gif, red_run_left.gif처럼 넣을 수 있습니다.\n",
            encoding="utf-8",
        )


def choose_startup_character(parent, brain):
    # 실행할 때마다 기존 캐릭터를 쓸지 새 캐릭터를 고를지 물어봅니다.
    ensure_characters_folder()
    message = QtWidgets.QMessageBox(parent)
    message.setWindowTitle("캐릭터 선택")
    message.setText("이번 실행에서 사용할 캐릭터를 선택하세요.")
    message.setInformativeText(
        "기존 캐릭터를 고르면 마지막으로 선택한 캐릭터 또는 기본 캐릭터를 사용합니다.\n"
        "새로운 캐릭터를 고르면 characters 폴더의 이미지/GIF를 선택합니다."
    )
    existing_button = message.addButton("기존 캐릭터", QtWidgets.QMessageBox.AcceptRole)
    new_button = message.addButton("새로운 캐릭터", QtWidgets.QMessageBox.ActionRole)
    message.setDefaultButton(existing_button)
    message.exec_()

    if message.clickedButton() != new_button:
        return

    type_message = QtWidgets.QMessageBox(parent)
    type_message.setWindowTitle("새 캐릭터 방식")
    type_message.setText("새 캐릭터를 어떤 방식으로 고를까요?")
    type_message.setInformativeText(
        "움직이는 캐릭터는 walk_right_0.png 같은 프레임이 들어 있는 폴더를 고르세요.\n"
        "그냥 이미지 하나만 쓰려면 PNG/GIF 파일을 고르면 됩니다."
    )
    folder_button = type_message.addButton("프레임 폴더", QtWidgets.QMessageBox.AcceptRole)
    file_button = type_message.addButton("PNG/GIF 파일", QtWidgets.QMessageBox.ActionRole)
    cancel_button = type_message.addButton("취소", QtWidgets.QMessageBox.RejectRole)
    type_message.setDefaultButton(folder_button)
    type_message.exec_()

    clicked = type_message.clickedButton()
    if clicked == cancel_button:
        return
    if clicked == folder_button:
        choose_character_folder(parent, brain)
        return

    choose_character_file(parent, brain)


def choose_character_folder(parent, brain):
    # 상태별 GIF가 들어 있는 폴더를 통째로 선택합니다.
    folder_path = QtWidgets.QFileDialog.getExistingDirectory(
        parent,
        "움직이는 캐릭터 폴더 선택",
        str(CHARACTERS_DIR),
    )
    if not folder_path:
        return

    selected = Path(folder_path)
    character_file = find_character_in_folder(selected)
    if not character_file:
        QtWidgets.QMessageBox.warning(
            parent,
            "캐릭터 없음",
            "선택한 폴더에서 사용할 캐릭터 파일을 찾지 못했습니다.\n"
            "walk_right_0.png, idle_right_0.png, character.png 같은 파일을 넣어주세요.",
        )
        return

    target = selected
    try:
        if not selected.resolve().is_relative_to(CHARACTERS_DIR.resolve()):
            target = unique_character_folder_path(selected.name)
            shutil.copytree(selected, target)
    except Exception:
        target = selected

    brain.set_selected_character(target)
    ask_character_scale(parent, brain)


def choose_character_file(parent, brain):
    # PNG/GIF 같은 파일 하나를 선택합니다.
    file_path, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
        parent,
        "새 캐릭터 선택",
        str(CHARACTERS_DIR),
        "캐릭터 파일 (*.gif *.png *.jpg *.jpeg *.bmp)",
    )
    if not file_path:
        return

    selected = Path(file_path)
    target = selected
    try:
        if not selected.resolve().is_relative_to(CHARACTERS_DIR.resolve()):
            target = unique_character_path(selected.name)
            shutil.copy2(selected, target)
    except Exception:
        target = selected

    brain.set_selected_character(target)
    ask_character_scale(parent, brain)


def ask_character_scale(parent, brain):
    # 새 캐릭터를 고른 뒤 크기 배율을 물어봅니다.
    percent, ok = QtWidgets.QInputDialog.getDouble(
        parent,
        "캐릭터 크기",
        "캐릭터 크기 배율을 정하세요. 100%가 원래 크기입니다.",
        brain.character_scale * 100,
        20,
        300,
        0,
    )
    if ok:
        brain.set_character_scale(percent / 100)


def find_character_in_folder(folder):
    # 움직이는 캐릭터 폴더 안에서 시작 이미지로 쓸 파일을 찾습니다.
    folder = Path(folder)
    if has_frame_sequence(folder):
        return find_first_sequence_file(folder)

    preferred_names = [
        "red_stop_right.gif",
        "stop_right.gif",
        "character.gif",
        "character.png",
        "character.jpg",
        "character.jpeg",
        "character.bmp",
    ]
    for name in preferred_names:
        path = folder / name
        if path.exists():
            return path

    patterns = [
        "*stop*right*.gif",
        "*idle*right*.gif",
        "*run*right*.gif",
        "*walk*right*.gif",
        "*.gif",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.bmp",
    ]
    for pattern in patterns:
        matches = sorted(folder.glob(pattern))
        if matches:
            return matches[0]
    return None


def has_frame_sequence(folder):
    # .pet_cache처럼 walk_right_0.png 형식의 프레임이 있는지 확인합니다.
    return find_first_sequence_file(folder) is not None


def find_first_sequence_file(folder):
    # 프레임 폴더에서 첫 번째로 쓸 만한 PNG를 찾습니다.
    folder = Path(folder)
    preferred_patterns = [
        "idle_right_*.png",
        "walk_right_*.png",
        "idle_left_*.png",
        "walk_left_*.png",
        "jump_right_*.png",
        "jump_left_*.png",
    ]
    for pattern in preferred_patterns:
        matches = sorted(folder.glob(pattern), key=frame_sort_key)
        if matches:
            return matches[0]
    return None


def load_frame_sequences(folder, scale=1.0):
    # 상태별 PNG 프레임을 읽어서 딕셔너리로 만듭니다.
    folder = Path(folder)
    sequences = {}
    for state in ("idle", "walk", "jump"):
        for facing in ("right", "left"):
            key = f"{state}_{facing}"
            paths = sorted(folder.glob(f"{key}_*.png"), key=frame_sort_key)
            pixmaps = []
            for path in paths:
                pixmap = QtGui.QPixmap(str(path))
                if not pixmap.isNull():
                    pixmaps.append(scale_frame_pixmap(pixmap, scale))
            if pixmaps:
                sequences[key] = pixmaps
    return sequences


def scale_frame_pixmap(pixmap, scale):
    # 프레임도 비율을 유지해서 확대/축소합니다.
    scale = max(0.2, min(3.0, float(scale or 1.0)))
    width = max(1, int(pixmap.width() * scale))
    height = max(1, int(pixmap.height() * scale))
    return pixmap.scaled(width, height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)


def frame_sort_key(path):
    # 파일 이름 끝의 숫자를 기준으로 0, 1, 2 순서대로 정렬합니다.
    stem = Path(path).stem
    last_part = stem.rsplit("_", 1)[-1]
    try:
        number = int(last_part)
    except ValueError:
        number = 0
    return number


def unique_character_path(filename):
    # 같은 이름이 있으면 뒤에 번호를 붙여서 덮어쓰지 않습니다.
    target = CHARACTERS_DIR / filename
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    for index in range(2, 1000):
        candidate = CHARACTERS_DIR / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    return CHARACTERS_DIR / f"{stem}_copy{suffix}"


def unique_character_folder_path(folder_name):
    # 같은 폴더 이름이 있으면 뒤에 번호를 붙여서 덮어쓰지 않습니다.
    safe_name = folder_name.strip() or "character_set"
    target = CHARACTERS_DIR / safe_name
    if not target.exists():
        return target

    for index in range(2, 1000):
        candidate = CHARACTERS_DIR / f"{safe_name}_{index}"
        if not candidate.exists():
            return candidate
    return CHARACTERS_DIR / f"{safe_name}_copy"


def main():
    # 프로그램 시작점입니다.
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # 이미 펫이 켜져 있으면 두 번째 펫은 실행하지 않습니다.
    lock = QtCore.QLockFile(str(LOCK_PATH))
    if not lock.tryLock(100):
        QtWidgets.QMessageBox.information(None, "이미 실행 중", "데스크탑 펫이 이미 실행 중입니다.")
        return
    app.desktop_pet_lock = lock

    brain = PetBrain()
    choose_startup_character(None, brain)
    sticker = Sticker(brain=brain, size=1.0, on_top=True)
    sticker.run()
    sys.exit(app.exec_())


def random_choice(items):
    # 리스트 안에서 아무거나 하나 고릅니다.
    index = int(QtCore.QRandomGenerator.global_().bounded(len(items)))
    return items[index]


def random_between(low, high):
    # low부터 high까지 숫자 중 아무거나 하나 고릅니다.
    return low + int(QtCore.QRandomGenerator.global_().bounded(high - low + 1))


if __name__ == "__main__":
    main()
