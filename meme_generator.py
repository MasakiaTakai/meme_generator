import sys
import os
import random
import csv
import logging
from io import BytesIO
from PyQt5 import uic, QtWidgets as Qw
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QTimer
from PIL import Image, ImageDraw, ImageFont
try:
    import tweepy
except ImportError:
    tweepy = None

# ファイルログ設定
logging.basicConfig(filename="meme_generator.log", level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

ui_file = resource_path("meme_generator.ui")
Ui_MainWindow, QtBaseClass = uic.loadUiType(ui_file)

class MyForm(Qw.QMainWindow):
    MESSAGE_BOX_STYLE = """
        QMessageBox {
            background-color: black;
        }
        QMessageBox QLabel {
            font-size: 20px;
            font-weight: bold;
            color: white;
        }
        QMessageBox QPushButton {
            background-color: black;
            color: white;
            border: 1px solid white;
            padding: 10px 20px;
            font-size: 16px;
            font-weight: bold;
            min-width: 60px;
            min-height: 20px;
        }
        QMessageBox QPushButton:hover {
            background-color: #55acee;
        }
    """
    BUTTON_STYLE = """
        QPushButton {
            background-color: black;
            color: white;
            border: 1px solid white;
            padding: 10px 20px;
            font-size: 16px;
            font-weight: bold;
            min-width: 60px;
            min-height: 20px;
        }
        QPushButton:hover {
            background-color: #55acee;
            color: white;
        }
    """

    def __init__(self):
        super().__init__()
        logging.debug("Initializing MyForm")
        logging.debug(f"UI file path: {ui_file}")

        if not os.path.exists(ui_file):
            logging.error(f"UI file not found: {ui_file}")
            msg = Qw.QMessageBox(None)
            msg.setWindowTitle("Error")
            msg.setText(f"UI file not found: {ui_file}")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            sys.exit(1)

        self.ui = Ui_MainWindow()
        logging.debug("Setting up UI")
        self.ui.setupUi(self)
        logging.debug("UI setup complete")
        self.setMinimumSize(800, 709)

        QTimer.singleShot(100, self.show_splash_message)
        self.ui.imageCanvas.setScaledContents(True)
        self.ui.imageCanvas.setMinimumSize(600, 450)

        self.image_folder = resource_path("images")
        self.image = None
        self.original_image = None
        self.current_font_size = 75
        self.current_padding = 20
        self.current_top_left_margin = 10
        self.current_bottom_padding = 20

        self.font_path = resource_path("impact.ttf")
        if not os.path.exists(self.font_path):
            logging.warning(f"Font file not found: {self.font_path}. Using default font.")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText(f"Font file not found: {self.font_path}. Using default font.")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            self.font_path = None

        self.captions = self.load_captions()
        self.ui.fontSizeSlider.setValue(75)
        self.ui.paddingSlider.setValue(20)
        self.ui.topLeftMarginSlider.setValue(10)
        self.ui.bottomPaddingSlider.setValue(20)

        self.api_key = os.getenv("X_API_KEY")
        self.api_secret = os.getenv("X_API_SECRET")
        self.access_token = os.getenv("X_ACCESS_TOKEN")
        self.access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")
        logging.debug(f"tweepy available: {tweepy is not None}")
        logging.debug(f"API keys: {self.api_key}, {self.api_secret}, {self.access_token}, {self.access_token_secret}")
        self.twitter_client = None
        self.twitter_api = None
        if tweepy and all([self.api_key, self.api_secret, self.access_token, self.access_token_secret]):
            try:
                self.twitter_client = tweepy.Client(
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_token_secret
                )
                auth = tweepy.OAuth1UserHandler(
                    self.api_key, self.api_secret,
                    self.access_token, self.access_token_secret
                )
                self.twitter_api = tweepy.API(auth)
                self.ui.shareButton.setEnabled(True)
                logging.debug("X API initialized successfully")
            except Exception as e:
                logging.error(f"X API initialization failed: {str(e)}")
                msg = Qw.QMessageBox(self)
                msg.setWindowTitle("Warning")
                msg.setText(f"Failed to initialize X API: {str(e)}")
                msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
                msg.exec_()
                self.ui.shareButton.setEnabled(False)
        else:
            logging.warning("X API keys not set or tweepy missing")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText("X API keys not set or tweepy library not found. X posting disabled.")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            self.ui.shareButton.setEnabled(False)

        logging.debug(f"shareButton exists: {hasattr(self.ui, 'shareButton')}")
        try:
            self.ui.shareButton.clicked.disconnect()
        except:
            logging.debug("No existing connections to disconnect")
        self.ui.shareButton.clicked.connect(self.share_to_x)
        self.ui.shareButton.clicked.connect(lambda: logging.debug("shareButton clicked"))
        self.ui.loadButton.clicked.connect(self.load_image)
        self.ui.templateButton.clicked.connect(self.random_gacha)
        self.ui.saveButton.clicked.connect(self.save_image)
        self.ui.clearButton.clicked.connect(self.clear_canvas)
        self.ui.fontSizeSlider.valueChanged.connect(self.update_font_size)
        self.ui.paddingSlider.valueChanged.connect(self.update_padding)
        self.ui.topLeftMarginSlider.valueChanged.connect(self.update_top_left_margin)
        self.ui.bottomPaddingSlider.valueChanged.connect(self.update_bottom_padding)
        self.ui.topTextEdit.textChanged.connect(self.update_canvas)
        self.ui.bottomTextEdit.textChanged.connect(self.update_canvas)
        logging.debug("Initialization complete")

    def show_splash_message(self):
        logging.debug("Showing splash message")
        msg = Qw.QMessageBox(self)
        msg.setWindowTitle("Welcome!")
        msg.setText("Grok's Meme Generator!\nCreate and share epic memes on X!")
        msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
        msg.exec_()

    def load_captions(self):
        captions_path = resource_path("captions.csv")
        logging.debug(f"Loading captions from: {captions_path}")
        if not os.path.exists(captions_path):
            logging.warning(f"Captions file not found: {captions_path}. Using default captions.")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText(f"Captions file not found: {captions_path}. Using default captions.")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            return [
                "LOL SO TRUE!", "EPIC FAIL!", "TOO FUNNY!", "MEME LORD!",
                "VIRAL VIBES!", "SAVAGE MODE!", "YOLO SWAG!", "BIG MOOD!",
                "NO CHILL!", "LMAO FOREVER!", "SPICY MEME!", "BESTIE ENERGY!",
                "ROASTED!", "ICONIC AF!", "SLAY QUEEN!"
            ]
        try:
            with open(captions_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                captions = [row[0] for row in reader if row]
                if not captions:
                    raise ValueError("captions.csv is empty")
                logging.debug(f"Loaded {len(captions)} captions")
                return captions
        except (FileNotFoundError, ValueError) as e:
            logging.warning(f"Failed to load captions: {str(e)}. Using default captions.")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText(f"Failed to load captions: {str(e)}. Using default captions.")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            return [
                "LOL SO TRUE!", "EPIC FAIL!", "TOO FUNNY!", "MEME LORD!",
                "VIRAL VIBES!", "SAVAGE MODE!", "YOLO SWAG!", "BIG MOOD!",
                "NO CHILL!", "LMAO FOREVER!", "SPICY MEME!", "BESTIE ENERGY!",
                "ROASTED!", "ICONIC AF!", "SLAY QUEEN!"
            ]

    def load_image(self):
        logging.debug("Loading image")
        file_name, _ = Qw.QFileDialog.getOpenFileName(self, "Select Image", self.image_folder, "Image Files (*.png *.jpg *.jpeg)")
        if file_name:
            try:
                self.image = Image.open(file_name).convert("RGBA")
                self.original_image = self.image.copy()
                self.update_canvas()
            except Exception as e:
                logging.error(f"Failed to load image: {str(e)}")
                msg = Qw.QMessageBox(self)
                msg.setWindowTitle("Error")
                msg.setText(f"Failed to load image: {str(e)}")
                msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
                msg.exec_()
                self.image = None
                self.original_image = None

    def random_gacha(self):
        logging.debug("Running random_gacha")
        if not os.path.exists(self.image_folder):
            logging.warning(f"Images folder not found: {self.image_folder}")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText(f"Images folder not found: {self.image_folder}")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            return
        self.image_files = [f for f in os.listdir(self.image_folder) if f.endswith((".jpg", ".png"))]
        if self.image_files:
            selected_image = os.path.join(self.image_folder, random.choice(self.image_files))
            try:
                self.image = Image.open(selected_image).convert("RGBA")
                self.original_image = self.image.copy()
                self.ui.topTextEdit.setText(random.choice(self.captions))
                self.ui.bottomTextEdit.setText("")
                self.update_canvas()
            except Exception as e:
                logging.error(f"Failed to load image: {str(e)}")
                msg = Qw.QMessageBox(self)
                msg.setWindowTitle("Error")
                msg.setText(f"Failed to load image: {str(e)}")
                msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
                msg.exec_()
                self.image = None
                self.original_image = None
        else:
            logging.warning("No images found in images folder")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText("No images found in images folder!")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()

    def save_image(self):
        logging.debug("Saving image")
        if self.image:
            output_folder = "output"
            os.makedirs(output_folder, exist_ok=True)
            output_path = os.path.join(output_folder, f"meme_{random.randint(1, 1000)}.png")
            self.image.save(output_path)
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Saved")
            msg.setText(f"Image saved as {output_path}")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
        else:
            logging.warning("No image to save")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText("No image to save!")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()

    def clear_canvas(self):
        logging.debug("Clearing canvas")
        self.ui.topTextEdit.clear()
        self.ui.bottomTextEdit.clear()
        self.image = None
        self.original_image = None
        self.ui.imageCanvas.clear()

    def share_to_x(self):
        logging.debug("Entering share_to_x")
        if not self.image:
            logging.warning("No image to post")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText("No image to post!")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            return
        if not self.twitter_client or not self.twitter_api:
            logging.warning("X API not initialized")
            msg = Qw.QMessageBox(self)
            msg.setWindowTitle("Warning")
            msg.setText("X API not initialized.")
            msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
            msg.exec_()
            return

        logging.debug("Showing dialog")
        dialog = Qw.QDialog(self)
        dialog.setWindowTitle("Confirm")
        dialog.setStyleSheet("background-color: black;")
        dialog.setWindowFlags(Qt.WindowCloseButtonHint)
        dialog.setFixedSize(300, 150)
        dialog.raise_()
        dialog.activateWindow()
        layout = Qw.QVBoxLayout()
        
        label = Qw.QLabel("Post this meme to X?")
        label.setStyleSheet("font-size: 20px; color: white;")
        layout.addWidget(label)
        
        button_layout = Qw.QHBoxLayout()
        yes_button = Qw.QPushButton("Yes")
        no_button = Qw.QPushButton("No")
        yes_button.setStyleSheet(self.BUTTON_STYLE)
        no_button.setStyleSheet(self.BUTTON_STYLE)
        button_layout.addWidget(yes_button)
        button_layout.addWidget(no_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        logging.debug(f"Buttons added: {[yes_button.text(), no_button.text()]}")
        logging.debug(f"Button style: {yes_button.styleSheet()}")
        
        result = False
        def on_yes():
            nonlocal result
            result = True
            dialog.accept()
        def on_no():
            dialog.reject()
        
        yes_button.clicked.connect(on_yes)
        no_button.clicked.connect(on_no)
        
        dialog.exec_()
        logging.debug(f"Dialog result: {result}")
        
        if result:
            try:
                temp_image = self.image.copy()
                if temp_image.size[0] > 1280 or temp_image.size[1] > 1280:
                    temp_image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                temp_path = "temp_meme.png"
                temp_image.save(temp_path, format="PNG")
                text = self.ui.topTextEdit.text()
                if not text.strip():
                    text = "Check out my meme! #MemeGenerator #MadeByGrok"
                with open(temp_path, 'rb') as image_file:
                    media = self.twitter_api.media_upload(filename=temp_path, file=image_file)
                self.twitter_client.create_tweet(text=text, media_ids=[media.media_id_string])
                msg = Qw.QMessageBox(self)
                msg.setWindowTitle("Success")
                msg.setText("Meme posted to X!")
                msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
                msg.exec_()
                os.remove(temp_path)
            except Exception as e:
                logging.error(f"Failed to post to X: {str(e)}")
                msg = Qw.QMessageBox(self)
                msg.setWindowTitle("Error")
                msg.setText(f"Failed to post to X: {str(e)}")
                msg.setStyleSheet(self.MESSAGE_BOX_STYLE)
                msg.exec_()

    def update_font_size(self, value):
        logging.debug(f"Updating font size: {value}")
        self.current_font_size = value
        if self.image:
            self.update_canvas()

    def update_padding(self, value):
        logging.debug(f"Updating padding: {value}")
        self.current_padding = value
        if self.image:
            self.update_canvas()

    def update_top_left_margin(self, value):
        logging.debug(f"Updating top left margin: {value}")
        self.current_top_left_margin = value
        if self.image:
            self.update_canvas()

    def update_bottom_padding(self, value):
        logging.debug(f"Updating bottom padding: {value}")
        self.current_bottom_padding = value
        if self.image:
            self.update_canvas()

    def update_canvas(self):
        logging.debug("Updating canvas")
        if not self.image:
            self.ui.imageCanvas.clear()
            return
        temp_image = self.original_image.copy()
        draw = ImageDraw.Draw(temp_image)
        font = ImageFont.truetype(self.font_path, self.current_font_size) if self.font_path else ImageFont.load_default()
        top_text = self.ui.topTextEdit.text()
        bottom_text = self.ui.bottomTextEdit.text()
        if top_text:
            draw.text((self.current_top_left_margin, self.current_padding), top_text, fill="white", font=font, stroke_width=2, stroke_fill="black")
        if bottom_text:
            bbox = draw.textbbox((0, 0), bottom_text, font=font)
            text_height = bbox[3] - bbox[1]
            y_position = temp_image.height - text_height - self.current_bottom_padding
            if y_position < 0:
                y_position = max(10, temp_image.height - text_height)
            draw.text((self.current_top_left_margin, y_position), bottom_text, fill="white", font=font, stroke_width=2, stroke_fill="black")
        canvas_size = self.ui.imageCanvas.size()
        resized_image = temp_image.resize((canvas_size.width(), canvas_size.height()), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        resized_image.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        self.ui.imageCanvas.setPixmap(pixmap.scaled(canvas_size.width(), canvas_size.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.image = temp_image

if __name__ == '__main__':
    logging.debug("Starting application")
    app = Qw.QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MyForm()
    window.show()
    logging.debug("Window shown")
    sys.exit(app.exec_())