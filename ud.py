#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import sys
import subprocess
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QProgressBar, QFileDialog, QMessageBox
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QPixmap
import re
import os
import requests
import tempfile 
import shutil 

class GetFormatsThread(QThread):
    finished = pyqtSignal(str)
    thumbnail = pyqtSignal(str, str)

    def __init__(self, url, browser):
        super().__init__()
        self.url = url
        self.browser = browser

    def run(self):
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        
        cookie_cmd = f"--cookies-from-browser {self.browser}" if self.browser != "None" else ""

        command_info = f'yt-dlp {cookie_cmd} --get-title --get-thumbnail "{self.url}"'
        try:
            output_info = subprocess.check_output(
                command_info, shell=True, text=True, creationflags=creationflags
            ).strip().split('\n')
            title = output_info[0] if output_info else "عنوان نامشخص"
            thumbnail_url = output_info[1] if len(output_info) > 1 else None
            self.thumbnail.emit(title, thumbnail_url)
        except subprocess.CalledProcessError as e:
            self.thumbnail.emit(f"خطا در گرفتن اطلاعات ویدیو: {e}", None)

        command_formats = f'yt-dlp {cookie_cmd} -F "{self.url}"'
        try:
            output = subprocess.check_output(
                command_formats, shell=True, text=True, stderr=subprocess.STDOUT, creationflags=creationflags
            )
            self.finished.emit(output)
        except subprocess.CalledProcessError as e:
            error_output = e.output
            if "not available on this app" in error_output:
                try:
                    version_cmd = 'yt-dlp --version'
                    current_version = subprocess.check_output(version_cmd, shell=True, text=True, creationflags=creationflags).strip()
                    custom_message = (
                        f"خطا: نسخه yt-dlp شما قدیمی است!\n\n"
                        f"نسخه فعلی شما: {current_version}\n"
                        f"یوتیوب درخواست‌های این نسخه را مسدود کرده است.\n\n"
                        f"لطفاً با دستور 'yt-dlp -U' آن را به‌روزرسانی کنید."
                    )
                    self.finished.emit(custom_message)
                except Exception:
                    self.finished.emit("خطا: نسخه yt-dlp شما قدیمی است. لطفاً با دستور 'yt-dlp -U' آن را آپدیت کنید.")
            else:
                self.finished.emit(f"خطا در دریافت کیفیت‌ها:\n{error_output}")

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    message = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            self.command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags
        )
        for line in process.stdout:
            percent = re.search(r'(\d+\.\d+)%|(\d+)%', line)
            if percent:
                value = percent.group(1) or percent.group(2)
                self.progress.emit(int(float(value)))
            self.message.emit(line.strip())
        process.wait()
        if process.returncode == 0:
            self.message.emit("دانلود با موفقیت انجام شد!")
            self.progress.emit(100)
        else:
            error = process.stderr.read()
            self.message.emit(f"خطا در دانلود: {error}")
            self.progress.emit(0)
        self.finished_signal.emit()

class ExtractAudioThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            result = subprocess.run(
                self.command, shell=True, check=True, capture_output=True, text=True, creationflags=creationflags
            )
            self.finished.emit("صدا با موفقیت استخراج شد!")
        except subprocess.CalledProcessError as e:
            error_message = f'خطا در استخراج صدا: {e.stderr}'
            if "Audio:" not in e.stderr:
                error_message += '\n\nفایل انتخاب‌شده جریان صوتی (Audio Stream) ندارد!'
            self.error.emit(error_message)

class YouTubeDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.downloaded_file = None
        self.format_sizes = {}
        self.custom_path = None
        self.initUI()
        self.check_dependencies()

    def initUI(self):
        self.setWindowTitle('YouTube Downloader')
        self.setFixedSize(900, 800)
        layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.url_label = QLabel('وارد کردن لینک ویدیو:')
        self.url_input = QLineEdit()
        top_layout.addWidget(self.url_label)
        top_layout.addWidget(self.url_input)

        self.browser_label = QLabel('انتخاب مرورگر (برای کوکی):')
        self.browser_select = QComboBox()
        self.browser_select.addItems(["Firefox", "Chrome", "Edge", "Brave", "None"])
        top_layout.addWidget(self.browser_label)
        top_layout.addWidget(self.browser_select)

        thumbnail_title_layout = QHBoxLayout()
        self.thumbnail_label = QLabel('پیش‌نمایش ویدیو:')
        self.thumbnail_label.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setFixedSize(320, 180)

        self.title_label = QLabel('عنوان ویدیو: -')
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.title_label.setWordWrap(True)
        thumbnail_title_layout.addWidget(self.thumbnail_label)
        thumbnail_title_layout.addWidget(self.title_label)

        self.get_formats_btn = QPushButton('بارگیری اطلاعات ویدیو')
        self.formats_list = QTextEdit()
        self.formats_list.setReadOnly(True)
        self.quality_label = QLabel('انتخاب کیفیت:')
        self.quality_select = QComboBox()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        buttons_layout = QHBoxLayout()
        self.download_btn = QPushButton('دانلود ویدیو')
        self.save_custom_btn = QPushButton('ذخیره در مسیر دلخواه')
        self.download_audio_btn = QPushButton('استخراج صدا از فایل (MP3)')
        buttons_layout.addWidget(self.download_btn)
        buttons_layout.addWidget(self.save_custom_btn)
        buttons_layout.addWidget(self.download_audio_btn)

        layout.addLayout(top_layout)
        layout.addWidget(self.get_formats_btn)
        layout.addLayout(thumbnail_title_layout)
        layout.addWidget(self.formats_list)
        layout.addWidget(self.quality_label)
        layout.addWidget(self.quality_select)
        layout.addLayout(buttons_layout)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

        # --- Connections ---
        self.get_formats_btn.clicked.connect(self.start_get_formats)
        self.download_btn.clicked.connect(self.download_video)
        self.save_custom_btn.clicked.connect(self.set_custom_path)
        self.download_audio_btn.clicked.connect(self.select_file_for_audio_extraction)

    def check_dependencies(self):
        self.formats_list.setText("در حال بررسی پیش‌نیازها...")
        if not shutil.which("yt-dlp"):
            QMessageBox.critical(self, "خطا", "yt-dlp یافت نشد! لطفاً آن را نصب کرده و در PATH سیستم قرار دهید.")
            self.formats_list.setText("خطا: yt-dlp نصب نیست.")
            return
        
        if not shutil.which("ffmpeg"):
            QMessageBox.warning(self, "هشدار", "ffmpeg یافت نشد! برای ترکیب ویدیو و صدا و استخراج صدا، نصب آن ضروری است.")
            self.formats_list.setText("هشدار: ffmpeg نصب نیست. عملکرد برنامه محدود خواهد بود.")
        
        self.formats_list.append("تمام پیش‌نیازهای اصلی یافت شدند.")
        
    def start_get_formats(self):
        url = self.url_input.text().strip()
        if not url:
            self.formats_list.setText('لطفاً لینک را وارد کنید!')
            return

        self.formats_list.setText('در حال بارگیری اطلاعات ویدیو...')
        self.get_formats_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        
        browser = self.browser_select.currentText().lower()
        self.get_formats_thread = GetFormatsThread(url, browser)
        self.get_formats_thread.finished.connect(self.on_get_formats_finished)
        self.get_formats_thread.thumbnail.connect(self.on_thumbnail_received)
        self.get_formats_thread.start()

    def on_thumbnail_received(self, title, thumbnail_url):
        self.title_label.setText(f'عنوان ویدیو: {title}')
        if thumbnail_url:
            try:
                response = requests.get(thumbnail_url, timeout=10)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                    tmp_file.write(response.content)
                    thumbnail_path = tmp_file.name
                
                pixmap = QPixmap(thumbnail_path)
                self.thumbnail_label.setPixmap(pixmap.scaled(
                    self.thumbnail_label.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                ))
                os.remove(thumbnail_path)
            except requests.exceptions.RequestException as e:
                self.thumbnail_label.setText(f'خطا در بارگیری تصویر:\n{e}')
        else:
            self.thumbnail_label.setText('تصویر پیش‌نمایش در دسترس نیست')

    def on_get_formats_finished(self, output):
        self.formats_list.setText(output)
        self.quality_select.clear()
        self.format_sizes.clear()

        if "ERROR" in output.upper():
             QMessageBox.warning(self, "خطا", f"خطایی در دریافت اطلاعات رخ داد:\n{output}")

        quality_720_index = -1
        for line in output.split('\n'):
            if line.strip().startswith("ID"): continue
            parts = re.split(r'\s+', line.strip())
            if len(parts) > 2 and parts[0].isdigit():
                format_id = parts[0]
                resolution = next((p for p in parts if 'x' in p and p[0].isdigit()), None)
                if resolution: 
                    size_match = re.search(r'(\d+\.?\d+[GMK]iB)', line)
                    size = size_match.group(1) if size_match else 'حجم نامشخص'
                    self.format_sizes[format_id] = size
                    display_text = f'{resolution} ({format_id}) - {size}'
                    self.quality_select.addItem(display_text)
                    if '720' in resolution:
                        quality_720_index = self.quality_select.count() - 1

        if quality_720_index != -1:
            self.quality_select.setCurrentIndex(quality_720_index)
        elif self.quality_select.count() == 0 and "ERROR" not in output.upper():
            QMessageBox.warning(self, "خطا", "هیچ فرمت ویدیویی معتبری یافت نشد. ممکن است لینک مشکل داشته باشد یا ویدیو خصوصی باشد.")

        self.get_formats_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

    def set_custom_path(self):
        path = QFileDialog.getExistingDirectory(self, 'پوشه ذخیره را انتخاب کنید')
        if path:
            self.custom_path = path
            self.formats_list.setText(f'مسیر دلخواه انتخاب شد: {self.custom_path}')

    def download_video(self):
        url = self.url_input.text().strip()
        format_text = self.quality_select.currentText()
        if not url or not format_text:
            QMessageBox.warning(self, "خطا", "لطفاً لینک و کیفیت را انتخاب کنید!")
            return

        format_id = re.search(r'\((\d+)\)', format_text).group(1)
        
        if self.custom_path:
            save_path = os.path.join(self.custom_path, "%(title)s.%(ext)s")
        else:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            save_path = os.path.join(desktop_path, "%(title)s.%(ext)s")
        
        self.formats_list.setText(f'در حال آماده‌سازی برای دانلود در: {os.path.dirname(save_path)}')
        
        browser = self.browser_select.currentText().lower()
        cookie_cmd = f"--cookies-from-browser {browser}" if browser != "None" else ""
        command = f'yt-dlp {cookie_cmd} -f {format_id}+bestaudio --merge-output-format mp4 -o "{save_path}" "{url}"'
        
        self.start_download(command)

    def select_file_for_audio_extraction(self):
        video_file, _ = QFileDialog.getOpenFileName(self, 'فایل ویدیویی را برای استخراج صدا انتخاب کنید', '', 'Video Files (*.mp4 *.mkv *.webm *.avi *.mov)')
        if video_file:
            self.extract_audio_from_file(video_file)

    def extract_audio_from_file(self, video_file):
        audio_file = os.path.splitext(video_file)[0] + '.mp3'
        self.formats_list.setText(f'در حال استخراج صدا از:\n{video_file}\nبه:\n{audio_file}')
        
        command = f'ffmpeg -i "{video_file}" -vn -c:a libmp3lame -b:a 320k "{audio_file}" -y'
        
        self.progress_bar.setRange(0, 0) # Indeterminate progress
        self.extract_thread = ExtractAudioThread(command)
        self.extract_thread.finished.connect(self.on_extract_audio_finished)
        self.extract_thread.error.connect(self.on_extract_audio_error)
        self.extract_thread.start()

    def on_extract_audio_finished(self, message):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.formats_list.append(f"\nموفقیت: {message}")
        QMessageBox.information(self, "عملیات موفق", message)

    def on_extract_audio_error(self, error_message):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.formats_list.append(f"\nخطا: {error_message}")
        QMessageBox.critical(self, "خطا در استخراج", error_message)

    def start_download(self, command):
        self.progress_bar.setValue(0)
        self.download_btn.setEnabled(False)
        self.download_thread = DownloadThread(command)
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.message.connect(self.on_download_message)
        self.download_thread.finished_signal.connect(self.on_download_finished)
        self.download_thread.start()

    def on_download_message(self, message):
        self.formats_list.append(message)
        if "Destination" in message:
            self.downloaded_file = message.split("Destination: ")[-1].strip()
        elif "ERROR" in message:
            QMessageBox.warning(self, "خطا در دانلود", message)

    def on_download_finished(self):
        self.download_btn.setEnabled(True)
        if self.progress_bar.value() == 100:
            QMessageBox.information(self, "دانلود کامل شد", f"فایل با موفقیت دانلود شد!\n\nمسیر: {self.downloaded_file}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec())
