

from __future__ import annotations

import sys
import traceback
import webbrowser
import subprocess
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QLineEdit, QTextEdit, QPlainTextEdit, QFileDialog,
    QComboBox, QCheckBox, QGroupBox, QFormLayout, QMessageBox, QSplitter,
    QProgressBar, QStatusBar, QApplication as _QApp,
)

try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    HAS_MULTIMEDIA = True
except Exception:
    HAS_MULTIMEDIA = False

from pipeline import TranscriptEduPipeline


CONFIG_API_KEY = "your own Ollama code"


APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "output"


# --------------------------------------------------------------------------- #
# Background worker (keeps the GUI thread responsive)
# --------------------------------------------------------------------------- #

class PipelineWorker(QThread):
    progress = pyqtSignal(str)
    stage_done = pyqtSignal(str, str)     # stage name, result text/path
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, pipeline: TranscriptEduPipeline, transcript_path: str,
                 output_dir: str, render_video: bool, quality: str):
        super().__init__()
        self.pipeline = pipeline
        self.transcript_path = transcript_path
        self.output_dir = output_dir
        self.render_video = render_video
        self.quality = quality

    def run(self):
        try:
            self.progress.emit("Reading transcript...")
            transcript = self.pipeline.read_transcript(self.transcript_path)

            self.progress.emit("Summarizing transcript with Ollama...")
            summary = self.pipeline.summarize_transcript(transcript)
            self.stage_done.emit("summary", summary)

            self.progress.emit("Generating Manim scene code...")
            manim_code = self.pipeline.generate_manim_code(summary)
            self.stage_done.emit("manim_code", manim_code)

            video_path = ""
            if self.render_video:
                self.progress.emit("Rendering Manim video (this can take a while)...")
                try:
                    video_path = self.pipeline.render_manim_video(
                        manim_code, self.output_dir, quality=self.quality
                    )
                    self.stage_done.emit("video_path", video_path)
                except Exception as exc:
                    self.progress.emit(f"Video render failed: {exc}")

            self.progress.emit("Generating Streamlit app code...")
            streamlit_code = self.pipeline.generate_streamlit_code(summary)
            self.stage_done.emit("streamlit_code", streamlit_code)

            self.progress.emit("Done.")
            self.finished_ok.emit({
                "summary": summary,
                "manim_code": manim_code,
                "video_path": video_path,
                "streamlit_code": streamlit_code,
            })
        except Exception:
            self.failed.emit(traceback.format_exc())


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Transcript \u2192 Manim + Streamlit Generator")
        self.resize(1200, 780)

        self.transcript_path: Optional[str] = None
        self.worker: Optional[PipelineWorker] = None
        self.current_video_path: str = ""

        self._build_ui()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")

    # ---------------------------------------------------------------- UI ---
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        root.addWidget(self._build_settings_panel(), stretch=0)
        root.addWidget(self._build_output_panel(), stretch=1)

    def _build_settings_panel(self) -> QWidget:
        panel = QGroupBox("Settings")
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)

        form = QFormLayout()
        self.model_edit = QLineEdit("gpt-oss:120b-cloud")
        self.host_edit = QLineEdit("http://localhost:11434")
        self.api_key_edit = QLineEdit(CONFIG_API_KEY or "")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("optional \u2014 only if your endpoint needs one")
        form.addRow("Model:", self.model_edit)
        form.addRow("Ollama host:", self.host_edit)
        form.addRow("API key:", self.api_key_edit)
        layout.addLayout(form)

        self.quality_combo = QComboBox()
        self.quality_combo.addItem("Low (fast)", "l")
        self.quality_combo.addItem("Medium", "m")
        self.quality_combo.addItem("High (slow)", "h")
        self.quality_combo.setCurrentIndex(1)
        quality_row = QFormLayout()
        quality_row.addRow("Video quality:", self.quality_combo)
        layout.addLayout(quality_row)

        self.render_video_checkbox = QCheckBox("Render Manim video (needs ffmpeg)")
        self.render_video_checkbox.setChecked(True)
        layout.addWidget(self.render_video_checkbox)

        layout.addSpacing(10)

        self.pick_file_btn = QPushButton("\U0001F4C2 Choose Transcript (.txt)")
        self.pick_file_btn.clicked.connect(self.choose_transcript)
        layout.addWidget(self.pick_file_btn)

        self.file_label = QLabel("No file selected.")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("color: #666;")
        layout.addWidget(self.file_label)

        self.generate_btn = QPushButton("\U0001F680 Generate")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 8px; } "
            "QPushButton:disabled { color: #999; }"
        )
        self.generate_btn.clicked.connect(self.run_pipeline)
        layout.addWidget(self.generate_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addStretch(1)

        self.run_streamlit_btn = QPushButton("\u25B6 Run Generated Streamlit App")
        self.run_streamlit_btn.setEnabled(False)
        self.run_streamlit_btn.clicked.connect(self.launch_streamlit_app)
        layout.addWidget(self.run_streamlit_btn)

        return panel

    def _build_output_panel(self) -> QWidget:
        self.tabs = QTabWidget()

        mono = QFont("Courier New")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(10)

        # Summary tab
        self.summary_view = QTextEdit()
        self.summary_view.setReadOnly(True)
        self.tabs.addTab(self.summary_view, "Summary")

        # Manim code tab
        manim_tab = QWidget()
        manim_layout = QVBoxLayout(manim_tab)
        self.manim_code_view = QPlainTextEdit()
        self.manim_code_view.setReadOnly(True)
        self.manim_code_view.setFont(mono)
        manim_layout.addWidget(self.manim_code_view)
        manim_btns = QHBoxLayout()
        self.save_manim_btn = QPushButton("Save generated_scene.py...")
        self.save_manim_btn.clicked.connect(lambda: self._save_text(self.manim_code_view, "generated_scene.py"))
        manim_btns.addWidget(self.save_manim_btn)
        manim_btns.addStretch(1)
        manim_layout.addLayout(manim_btns)
        self.tabs.addTab(manim_tab, "Manim Code")

        # Video tab
        self.video_tab = QWidget()
        video_layout = QVBoxLayout(self.video_tab)
        self.video_widget = None
        self.media_player = None
        if HAS_MULTIMEDIA:
            try:
                self.video_widget = QVideoWidget()
                self.media_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
                self.media_player.setVideoOutput(self.video_widget)
                video_layout.addWidget(self.video_widget, stretch=1)
                controls = QHBoxLayout()
                play_btn = QPushButton("Play")
                play_btn.clicked.connect(lambda: self.media_player.play())
                pause_btn = QPushButton("Pause")
                pause_btn.clicked.connect(lambda: self.media_player.pause())
                controls.addWidget(play_btn)
                controls.addWidget(pause_btn)
                controls.addStretch(1)
                video_layout.addLayout(controls)
            except Exception:
                self.video_widget = None
                self.media_player = None

        if self.video_widget is None:
            video_layout.addWidget(QLabel(
                "In-app video preview isn't available on this system "
                "(missing Qt multimedia backend). Use the button below instead."
            ))

        open_btn_row = QHBoxLayout()
        self.open_video_btn = QPushButton("Open Video in System Player")
        self.open_video_btn.setEnabled(False)
        self.open_video_btn.clicked.connect(self.open_video_externally)
        open_btn_row.addWidget(self.open_video_btn)
        open_btn_row.addStretch(1)
        video_layout.addLayout(open_btn_row)

        self.tabs.addTab(self.video_tab, "Video")

        # Streamlit code tab
        st_tab = QWidget()
        st_layout = QVBoxLayout(st_tab)
        self.streamlit_code_view = QPlainTextEdit()
        self.streamlit_code_view.setReadOnly(True)
        self.streamlit_code_view.setFont(mono)
        st_layout.addWidget(self.streamlit_code_view)
        st_btns = QHBoxLayout()
        self.save_streamlit_btn = QPushButton("Save generated_app.py...")
        self.save_streamlit_btn.clicked.connect(lambda: self._save_text(self.streamlit_code_view, "generated_app.py"))
        st_btns.addWidget(self.save_streamlit_btn)
        st_btns.addStretch(1)
        st_layout.addLayout(st_btns)
        self.tabs.addTab(st_tab, "Streamlit Code")

        # Log tab
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(mono)
        self.tabs.addTab(self.log_view, "Log")

        return self.tabs

    # ------------------------------------------------------------ actions ---
    def choose_transcript(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose transcript", "", "Text files (*.txt)")
        if path:
            self.transcript_path = path
            self.file_label.setText(path)
            self.generate_btn.setEnabled(True)

    def run_pipeline(self):
        if not self.transcript_path:
            return

        self.generate_btn.setEnabled(False)
        self.run_streamlit_btn.setEnabled(False)
        self.open_video_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log_view.clear()
        self.summary_view.clear()
        self.manim_code_view.clear()
        self.streamlit_code_view.clear()
        self.current_video_path = ""

        pipeline = TranscriptEduPipeline(
            model=self.model_edit.text().strip() or "llama3.1:70b",
            ollama_host=self.host_edit.text().strip() or "http://localhost:11434",
            api_key=self.api_key_edit.text().strip() or None,
        )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        self.worker = PipelineWorker(
            pipeline=pipeline,
            transcript_path=self.transcript_path,
            output_dir=str(OUTPUT_DIR),
            render_video=self.render_video_checkbox.isChecked(),
            quality=self.quality_combo.currentData(),
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.stage_done.connect(self._on_stage_done)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, message: str):
        self.log_view.appendPlainText(message)
        self.statusBar().showMessage(message)

    def _on_stage_done(self, stage: str, payload: str):
        if stage == "summary":
            self.summary_view.setPlainText(payload)
        elif stage == "manim_code":
            self.manim_code_view.setPlainText(payload)
        elif stage == "video_path":
            self.current_video_path = payload
            self.open_video_btn.setEnabled(True)
            if self.media_player is not None:
                self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(payload)))
        elif stage == "streamlit_code":
            self.streamlit_code_view.setPlainText(payload)

    def _on_finished(self, result: dict):
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        self.run_streamlit_btn.setEnabled(bool(result.get("streamlit_code")))
        self.statusBar().showMessage("Generation complete.")
        QMessageBox.information(self, "Done", "Generation complete. Check the tabs on the right.")

    def _on_failed(self, error_text: str):
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        self.log_view.appendPlainText("ERROR:\n" + error_text)
        self.statusBar().showMessage("Failed \u2014 see Log tab.")
        QMessageBox.critical(self, "Generation failed", error_text.strip().splitlines()[-1] if error_text.strip() else "Unknown error")

    def open_video_externally(self):
        if self.current_video_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_video_path))

    def launch_streamlit_app(self):
        app_path = OUTPUT_DIR / "generated_app.py"
        if not app_path.exists():
            QMessageBox.warning(self, "Not found", f"{app_path} does not exist yet.")
            return
        try:
            subprocess.Popen(["streamlit", "run", str(app_path)])
            webbrowser.open("http://localhost:8501")
        except FileNotFoundError:
            QMessageBox.critical(
                self, "Streamlit not found",
                "Could not find the `streamlit` command. Install it with:\n\npip install streamlit"
            )

    def _save_text(self, widget: QPlainTextEdit, default_name: str):
        text = widget.toPlainText()
        if not text:
            QMessageBox.information(self, "Nothing to save", "Generate content first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save file", default_name, "Python files (*.py)")
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.statusBar().showMessage(f"Saved {path}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
