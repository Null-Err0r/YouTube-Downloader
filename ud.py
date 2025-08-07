#!/usr/bin/env python3.10
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

class GetFormatsThread(QThread):
    finished = pyqtSignal(str)
    thumbnail = pyqtSignal(str, str)

    def __init__(self, url):
        super().__init__()
        if not re.match(r'^[a-zA-Z0-9_\-/\\]+$', url):
            raise ValueError("Invalid URL format")
        self.url = url

    def run(self):
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        command_info = f'yt-dlp --cookies-from-browser firefox --get-title --get-thumbnail "{self.url}"'
        try:
            output_info = subprocess.check_output(
                command_info,
                shell=True,
                text=True,
                creationflags=creationflags
            ).strip().split('\n')
            title = output_info[0] if output_info else "عنوان نامشخص"
            thumbnail_url = output_info[1] if len(output_info) > 1 else None
            self.thumbnail.emit(title, thumbnail_url)
        except subprocess.CalledProcessError as e:
            self.thumbnail.emit(f"خطا در گرفتن اطلاعات ویدیو: {e}", None)

        command = f'yt-dlp --cookies-from-browser firefox -F "{self.url}"'
        try:
            output = subprocess.check_output(
                command,
                shell=True,
                text=True,
                creationflags=creationflags
            )
            self.finished.emit(output)
        except subprocess.CalledProcessError as e:
            self.finished.emit(f"خطا در دریافت کیفیت‌ها:\n{e}")

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    message = pyqtSignal(str)

    def __init__(self, command):
        super().__init__()
        if not re.match(r'^[a-zA-Z0-9_\-/\\]+$', command):
            raise ValueError("Invalid command format")
        self.command = command

    def run(self):
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            self.command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags
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

class YouTubeDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.downloaded_file = None
        self.format_sizes = {}
        self.custom_path = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle('YouTube Downloader')
        self.setFixedSize(900, 800)

        layout = QVBoxLayout()

        self.url_label = QLabel('وارد کردن لینک ویدیو:')
        self.url_input = QLineEdit()

        self.get_formats_btn = QPushButton('بارگیری اطلاعات ویدیو')
        self.get_formats_btn.clicked.connect(self.start_get_formats)

        thumbnail_title_layout = QHBoxLayout()

        self.thumbnail_label = QLabel('پیش‌نمایش ویدیو:')
        self.thumbnail_label.setStyleSheet("border: 0px solid black;")
        self.thumbnail_label.setFixedWidth(300)
        self.thumbnail_label.setFixedHeight(180)

        self.title_label = QLabel('عنوان ویدیو: -')
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(300)

        thumbnail_title_layout.addWidget(self.thumbnail_label)
        thumbnail_title_layout.addWidget(self.title_label)

        self.formats_list = QTextEdit()
        self.formats_list.setReadOnly(True)

        self.quality_label = QLabel('انتخاب کیفیت:')
        self.quality_select = QComboBox()

        buttons_layout = QHBoxLayout()
        self.download_btn = QPushButton('دانلود ویدیو')
        self.download_btn.clicked.connect(self.download_video)

        self.save_custom_btn = QPushButton('ذخیره در مسیر دلخواه')
        self.save_custom_btn.clicked.connect(self.set_custom_path)

        self.download_audio_btn = QPushButton('استخراج صدا (MP3 320kbps)')
        self.download_audio_btn.clicked.connect(self.download_audio)

        buttons_layout.addWidget(self.download_btn)
        buttons_layout.addWidget(self.save_custom_btn)
        buttons_layout.addWidget(self.download_audio_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        layout.addWidget(self.url_label)
        layout.addWidget(self.url_input)
        layout.addWidget(self.get_formats_btn)
        layout.addLayout(thumbnail_title_layout)
        layout.addWidget(self.formats_list)
        layout.addWidget(self.quality_label)
        layout.addWidget(self.quality_select)
        layout.addLayout(buttons_layout)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

        self.check_install_dependencies()

    def check_install_dependencies(self):
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            subprocess.check_call(['yt-dlp', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
            subprocess.check_call(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
            self.formats_list.setText('پیش‌نیازها نصب و به‌روزرسانی شدند!')
        except subprocess.CalledProcessError:
            self.formats_list.setText('yt-dlp یا ffmpeg نصب نیست. در حال نصب...')
            try:
                if sys.platform == "linux":
                    subprocess.check_call(['sudo', 'apt', 'install', '-y', 'ffmpeg'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                elif sys.platform == "win32":
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
                    self.formats_list.setText('لطفاً ffmpeg را به‌صورت دستی در ویندوز نصب کنید.')
                self.formats_list.setText('پیش‌نیازها نصب شدند!')
            except subprocess.CalledProcessError as e:
                self.formats_list.setText(f'خطا در نصب پیش‌نیازها: {e}')

    def start_get_formats(self):
        url = self.url_input.text().strip()
        if not url:
            self.formats_list.setText('لطفاً لینک را وارد کنید!')
            return

        self.formats_list.setText('در حال بارگیری اطلاعات ویدیو...')
        self.get_formats_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0) 

        if self.downloaded_file and os.path.exists(self.downloaded_file):
            try:
                os.remove(self.downloaded_file)
                self.formats_list.setText(f'فایل قبلی ({self.downloaded_file}) پاک شد.')
                self.downloaded_file = None
            except OSError as e:
                self.formats_list.setText(f'خطا در پاک کردن فایل قبلی: {e}')

        self.get_formats_thread = GetFormatsThread(url)
        self.get_formats_thread.finished.connect(self.on_get_formats_finished)
        self.get_formats_thread.thumbnail.connect(self.on_thumbnail_received)
        self.get_formats_thread.start()

    def on_thumbnail_received(self, title, thumbnail_url):
        self.title_label.setText(f'عنوان ویدیو: {title}')
        if thumbnail_url:
            response = requests.get(thumbnail_url)
            with open('thumbnail.jpg', 'wb') as f:
                f.write(response.content)
            pixmap = QPixmap('thumbnail.jpg').scaled(500, 180, aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio)
            self.thumbnail_label.setPixmap(pixmap)
            os.remove('thumbnail.jpg')
        else:
            self.thumbnail_label.setText('تصویر پیش‌نمایش در دسترس نیست')

    def on_get_formats_finished(self, output):
        self.formats_list.setText(output)
        self.quality_select.clear()
        self.format_sizes.clear()

        if "Only images are available" in output or "Some formats may be missing" in output:
            self.formats_list.setText(output + '\n\nخطا: هیچ فرمت ویدیویی در دسترس نیست. لطفاً لینک دیگری امتحان کنید یا yt-dlp را به‌روزرسانی کنید.')
            QMessageBox.warning(self, "خطا", "هیچ فرمت ویدیویی در دسترس نیست. ممکن است به دلیل محدودیت‌های یوتیوب (SSAP) باشد. لطفاً لینک دیگری امتحان کنید یا yt-dlp را به‌روزرسانی کنید.")
            self.get_formats_btn.setEnabled(True)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            return

        quality_720_index = -1
        for i, line in enumerate(output.split('\n')):
            parts = line.split()
            if parts and (len(parts) > 1 and parts[0].isdigit()):
                resolution = re.search(r'(\d+x\d+)', line)
                if resolution:
                    format_id = parts[0]
                    size = next((part for part in parts if any(unit in part for unit in ['MiB', 'GiB', 'KiB'])), 'حجم نامشخص')
                    self.format_sizes[format_id] = size
                    display_text = f'Video {resolution.group(1)} ({format_id}) - {size}'
                    self.quality_select.addItem(display_text)
                    if '720' in resolution.group(1):
                        quality_720_index = self.quality_select.count() - 1

        if quality_720_index != -1:
            self.quality_select.setCurrentIndex(quality_720_index)
        elif self.quality_select.count() == 0:
            self.formats_list.setText(output + '\n\nخطا: هیچ فرمت ویدیویی معتبری یافت نشد.')
            QMessageBox.warning(self, "خطا", "هیچ فرمت ویدیویی معتبری یافت نشد. لطفاً لینک دیگری امتحان کنید.")

        self.get_formats_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

    def set_custom_path(self):
        self.custom_path = QFileDialog.getExistingDirectory(self, 'پوشه ذخیره را انتخاب کنید')
        if self.custom_path:
            self.formats_list.setText(f'مسیر دلخواه انتخاب شد: {self.custom_path}')
        else:
            self.formats_list.setText('مسیر دلخواهی انتخاب نشد!')

    def download_video(self):
        url = self.url_input.text().strip()
        format_text = self.quality_select.currentText()
        if not url or not format_text:
            self.formats_list.setText('لطفاً لینک و کیفیت را انتخاب کنید!')
            return

        format_id = format_text.split('(')[-1].split(')')[0]
        if self.custom_path:
            save_path = os.path.join(self.custom_path, "%(title)s.%(ext)s")
            self.formats_list.setText(f'در حال دانلود در مسیر: {self.custom_path}')
        else:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            save_path = os.path.join(desktop_path, "%(title)s.%(ext)s")
            self.formats_list.setText(f'در حال دانلود در دسکتاپ: {save_path}')

        command = f'yt-dlp --cookies-from-browser firefox -f {format_id}+bestaudio --merge-output-format mp4 -o "{save_path}" "{url}"'
        
        self.start_download(command)

    def download_audio(self):
        video_file = QFileDialog.getOpenFileName(self, 'فایل ویدیویی را انتخاب کنید', '', 'Video Files (*.mp4 *.mkv *.webm)')[0]
        
        if video_file:
            self.downloaded_file = video_file
            self.formats_list.setText(f'فایل انتخاب‌شده: {video_file}')
            self.extract_audio_from_file(video_file)
        else:
            self.formats_list.setText('فایلی انتخاب نشد! لطفاً یک فایل ویدیویی انتخاب کنید.')

    def start_download(self, command):
        self.progress_bar.setValue(0)
        self.download_thread = DownloadThread(command)
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.message.connect(self.on_download_message)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.start()

    def on_download_message(self, message):
        self.formats_list.append(message)
        if "Destination" in message:
            self.downloaded_file = message.split("Destination: ")[-1].strip()
        if "ERROR" in message or "Some formats may be missing" in message:
            QMessageBox.warning(self, "خطا در دانلود", message + "\nلطفاً yt-dlp را به‌روزرسانی کنید یا لینک دیگری امتحان کنید.")

    def on_download_finished(self):
        self.formats_list.append(f'فایل دانلودشده: {self.downloaded_file}')
        if self.progress_bar.value() == 100:
            QMessageBox.information(self, "دانلود کامل شد", "فایل ویدیویی با موفقیت دانلود و ترکیب شد!")

    def extract_audio_from_file(self, video_file):
        if not re.match(r'^[a-zA-Z0-9_\-/\\]+$', video_file):
            raise ValueError("Invalid video file path")
        audio_file = os.path.splitext(video_file)[0] + '.mp3'
        
        self.formats_list.append(f'در حال استخراج صدا از: {video_file}')
        self.formats_list.append(f'ذخیره به‌عنوان: {audio_file}')
        command = f'ffmpeg -i "{video_file}" -vn -acodec mp3 -ab 320k "{audio_file}" -y'
        
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags
            )
            self.formats_list.append('صدا با موفقیت استخراج شد!')
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "استخراج صدا", "صدا با موفقیت به‌صورت MP3 استخراج شد!")
        except subprocess.CalledProcessError as e:
            self.formats_list.append(f'خطا در استخراج صدا: {e.stderr}')
            if "Audio:" not in e.stderr:
                self.formats_list.append('فایل انتخاب‌شده جریان صوتی ندارد! لطفاً فایلی با صدا انتخاب کنید.')
                QMessageBox.warning(self, "خطا", "فایل انتخاب‌شده جریان صوتی ندارد! لطفاً فایلی با صدا انتخاب کنید.")
            self.progress_bar.setValue(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec())
