import csv
import sys
import os
import argparse
import tempfile
from pathlib import Path
from shutil import which

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import (
    QTimer,
    Qt,
    pyqtSlot,
    pyqtSignal,
    QThread,
    QSize,
    QObject,
    # , QIcon#, QAction
)  
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QScreen
from PyQt5.QtWidgets import (
    QStatusBar,
    QAction,
    QMainWindow,
    QApplication,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QShortcut,
    QPushButton,
    QTextEdit,
    QFormLayout,
    QHBoxLayout,
    QCheckBox,
    QDoubleSpinBox,
    QLabel,
    QToolBar,
    QLineEdit,
    QSpinBox,
    QTabWidget,
)
from pynput.mouse import Controller
from PIL import ImageGrab, Image
import numpy as np
from screeninfo import get_monitors
from datetime import datetime
from rich import print as rprint

from pix2tex.datastore import SnipEntry
from pix2tex.resources import resources
from pix2tex import cli
from pix2tex.utils import in_model_path

QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)




class App(QMainWindow):
    isProcessing = False

    def __init__(self, args=None,
                 ):
        super().__init__()
        # QMainWindow.__init__(self, parent)
        self.args = args
        self.model = cli.LatexOCR(self.args)

        self.screenshot_dir = Path("/home/hanz/GitHub/toolkit/LaTeX-OCR/pix2tex/model/screenshots")
        self.history_dir = Path("/home/hanz/GitHub/toolkit/LaTeX-OCR/pix2tex/model/screenshots")
        self.history = []
        self.current_day = datetime.now().strftime("%Y-%m-%d")



        self.initUI()
        self.snipWidget = SnipWidget(self)
        # parent.aboutToQuit.connect(self.closeEvent)
        # self.show()

    def initUI(self):
        self.setWindowTitle("LaTeX OCR")
        # self.setStyleSheet("background-color: #404552")
        QApplication.setWindowIcon(QtGui.QIcon(":/icons/icon.svg"))
        self.left = 300
        self.top = 300
        self.width = 500
        self.height = 600
        self.setGeometry(self.left, self.top, self.width, self.height)

        # ==============================================================
        # Create toolbar
        toolbar = QToolBar("My main toolbar")
        toolbar.setIconSize(QSize(16, 16))
        # self.addToolBar(toolbar)

        button_action = QAction(QIcon("bug.png"), "&Your button", self)
        button_action.setStatusTip("This is your button")
        button_action.triggered.connect(self.onMyToolBarButtonClick)
        button_action.setCheckable(True)
        toolbar.addAction(button_action)

        toolbar.addSeparator()

        button_action2 = QAction(QIcon("bug.png"), "Your &button2", self)
        button_action2.setStatusTip("This is your button2")
        button_action2.triggered.connect(self.onMyToolBarButtonClick)
        button_action2.setCheckable(True)
        toolbar.addAction(button_action2)

        toolbar.addWidget(QLabel("Hello"))
        toolbar.addWidget(QCheckBox())

        self.setStatusBar(QStatusBar(self))

        menu = self.menuBar()

        file_menu = menu.addMenu("&File")
        file_menu.addAction(button_action)
        file_menu.addSeparator()
        file_menu.addAction(button_action2)

        # ==============================================================
        # Create LaTeX display
        self.webView = QWebEngineView()
        self.webView.setHtml("")
        self.webView.setMinimumHeight(80)

        # Create textbox
        self.textbox = QTextEdit(self)
        self.textbox.textChanged.connect(self.displayPrediction)
        self.textbox.setMinimumHeight(40)
        # self.textbox.setStyleSheet(
        #    "color: #c6c6bd; background-color: #4b5162; border: 1px solid #383c4a;"
        # )

        # Create temperature text input
        self.tempField = QDoubleSpinBox(self)
        self.tempField.setValue(self.args.temperature)
        self.tempField.setRange(0, 1)
        self.tempField.setSingleStep(0.1)
        # self.tempField.setStyleSheet("color: #c6c6bd")

        # Create snip button
        self.snipButton = QPushButton("Snip [Alt+S]", self)
        self.snipButton.clicked.connect(self.onClick)
        # self.snipButton.setStyleSheet("color: #c6c6bd")

        self.shortcut = QShortcut(QKeySequence("Alt+S"), self)
        self.shortcut.activated.connect(self.onClick)

        # Create retry button
        self.retryButton = QPushButton("Retry", self)
        self.retryButton.setEnabled(False)
        self.retryButton.clicked.connect(self.returnSnip)
        # self.retryButton.setStyleSheet("color: #c6c6bd")

        # Create tabs
        # tabs = QTabWidget()
        # tabs.addTab(QLabel("Snip"), '"Snip! Snip...?!"')
        # tabs.addTab(QLabel("History"), "History")

        # Create layout
        centralWidget = QWidget()
        centralWidget.setMinimumWidth(200)
        self.setCentralWidget(centralWidget)

        lay = QVBoxLayout(centralWidget)
        lay.addWidget(self.webView, stretch=4)
        # lay.addWidget(tabs) # add history
        lay.addWidget(self.textbox, stretch=2)
        buttons = QHBoxLayout()
        buttons.addWidget(self.snipButton)
        buttons.addWidget(self.retryButton)
        lay.addLayout(buttons)
        settings = QFormLayout()
        settings.addRow("Temperature:", self.tempField)
        # self.tempField.setStyleSheet("color: #c6c6bd")
        lay.addLayout(settings)

    def onMyToolBarButtonClick(self, s):
        print("click", s)

    def toggleProcessing(self, value=None):
        if value is None:
            self.isProcessing = not self.isProcessing
        else:
            self.isProcessing = value
        if self.isProcessing:
            text = "Interrupt"
            func = self.interrupt
        else:
            text = "Snip [Alt+S]"
            func = self.onClick
            self.retryButton.setEnabled(True)
        self.shortcut.setEnabled(not self.isProcessing)
        self.snipButton.setText(text)
        self.snipButton.clicked.disconnect()
        self.snipButton.clicked.connect(func)
        self.displayPrediction()

    @pyqtSlot()
    def onClick(self):
        self.close()
        # if self.args.gnome:
        if which("gnome-screenshot"):
            self.snip_using_gnome_screenshot()
        else:
            self.snipWidget.snip()

    @pyqtSlot()
    def interrupt(self):
        if hasattr(self, "thread"):
            self.thread.terminate()
            self.thread.wait()
            self.toggleProcessing(False)

    def snip_using_gnome_screenshot(self):
        try:
            with tempfile.NamedTemporaryFile() as tmp:
                cmd_str = f"gnome-screenshot --area --file {tmp.name}"
                # subprocess.Popen(*cmd_str.split(" "))
                os.system(f"gnome-screenshot --area --file={tmp.name}")
                # print(tmp.name)
                im = Image.open(tmp.name)
                outdir = self.screenshot_dir / datetime.now().strftime("%Y-%m-%d") / "img"
                if not outdir.exists():
                    rprint("[orange] Created:", outdir)
                    os.makedirs(outdir)

                fpout = self.screenshot_dir / datetime.now().strftime("%Y-%m-%d") / "img" / os.path.basename(
                    f"{tmp.name}.png")
                rprint("[yellow]Saving:", fpout)  # DEBUG

                im.save(str(fpout))
                im.filename = str(fpout)
                # TODO: save inference

                # Use `tmp.name` instead of `tmp.file` due to compatability issues between Pillow and tempfile
                self.returnSnip(im)
        except:
            print(f"Failed to load saved screenshot! Did you cancel the screenshot?")
            print("If you don't have `gnome-screenshot` installed, please install it:\n"
                  "`sudo apt-get install -y gnome-screenshot`")
            self.returnSnip()

    def returnSnip(self, img=None):
        self.toggleProcessing(True)
        self.retryButton.setEnabled(False)

        self.show()
        try:
            self.model.args.temperature = self.tempField.value()
            if self.model.args.temperature == 0:
                self.model.args.temperature = 1e-8
        except:
            pass
        # Run the model in a separate thread
        self.thread = ModelThread(img=img, model=self.model)
        self.thread.finished.connect(self.returnPrediction)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def returnPrediction(self, result):
        self.toggleProcessing(False)
        success, prediction = result["success"], result["prediction"]
        rprint(result)
        if success and result["img"] is not None:
            self.displayPrediction(prediction)
            self.retryButton.setEnabled(True)

            # rprint(img.__dict__.keys())
            # self._tmp_entry = SnipEntry(
            #     img=result["img"], path=result["img"].filename, label=prediction)
            entry = SnipEntry(
                # img=None,#np.array(result["img"]),
                path=result["img"].filename, label=prediction, hparams=dict(
                    temperature=self.model.args.temperature
                ))

            # rprint("[yellow]", "PRE UPDATE")    # DEBUG
            # rprint(entry)                       # DEBUG
            # self.history.append(entry)self._tmp_entry)

            self.update_history(self.history, self.history_dir, self.current_day, entry=entry)

            # rprint("[yellow]", "POST UPDATE")    # DEBUG
            # self._tmp_entry = None
            # rprint(self._tmp_entry)
            rprint(self.history)        # DEBUG
            # self.tmp_prediction = None
        else:
            self.webView.setHtml("")
            msg = QMessageBox()
            msg.setWindowTitle(" ")
            msg.setText("Prediction failed.")
            msg.exec_()

    def displayPrediction(self, prediction=None):
        if self.isProcessing:
            pageSource = """<center>
            <img src="qrc:/icons/processing-icon-anim.svg" width="50", height="50">
            </center>"""
        else:
            if prediction is not None:
                self.textbox.setText("${equation}$".format(equation=prediction))
            else:
                prediction = self.textbox.toPlainText().strip("$")
            pageSource = """
            <html>
            <head><script id="MathJax-script" src="qrc:MathJax.js"></script>
            <script>
            MathJax.Hub.Config({messageStyle: 'none',tex2jax: {preview: 'none'}});
            MathJax.Hub.Queue(
                function () {
                    document.getElementById("equation").style.visibility = "";
                }
                );
            </script>
            </head> """ + """
            <body>
            <div id="equation" style="font-size:1em; visibility:hidden">$${equation}$$</div>
            </body>
            </html>
                """.format(
                equation=prediction
            )
        self.webView.setHtml(pageSource)

    def update_history(self, history, history_dir, current_day, entry) -> None:
        history.append(entry)
        self.save_history(history_dir, current_day, history)

    def save_history(self, history_dir, current_day, history) -> None:
        """
        <date>
            |- imgs
            |   |- <uid>.png
            |   |- <uid>.png
            |   |- <uid>.png
            |
            |- history.csv


        """
        fieldnames = ["uid", "date", "path", "prediction", "hparams", "label"
                      # "user.reaction"
                      ]
        filepath = history_dir / current_day / "history.csv"
        # rprint(filepath)  # DEBUG

        entry: dict = history[-1].to_dict()
        fieldnames = list(entry.keys())
        if not filepath.exists():
            with open(filepath, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=",")
                # writer.writeheader()
                writer.writerow(dict(zip(entry.keys(), fieldnames)))
                writer.writerow(entry)
        else:
            with open(filepath, "a", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=",")
                # writer.writeheader()
                writer.writerow(entry)

    # def closeEvent(self, event):
    #     print('Calling')
    #     print('event: {0}'.format(event))
        # event.accept()

class ModelThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, img, model):
        super().__init__()
        self.img = img
        self.model = model

    def run(self):
        try:
            prediction = self.model(self.img)
            # replace <, > with \lt, \gt so it won't be interpreted as html code
            prediction = prediction.replace("<", "\\lt ").replace(">", "\\gt ")
            self.finished.emit({"success": True, "prediction": prediction, "img": self.img})
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit({"success": False, "prediction": None, "img": None})


class SnipWidget(QMainWindow):
    isSnipping = False

    def __init__(self, parent):
        super().__init__()
        self.parent = parent

        monitos = get_monitors()
        bboxes = np.array([[m.x, m.y, m.width, m.height] for m in monitos])
        x, y, _, _ = bboxes.min(0)
        w, h = bboxes[:, [0, 2]].sum(1).max(), bboxes[:, [1, 3]].sum(1).max()
        self.setGeometry(x, y, w - x, h - y)

        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()

        self.mouse = Controller()

    def snip(self):
        self.isSnipping = True
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))

        self.show()

    def paintEvent(self, event):
        if self.isSnipping:
            brushColor = (0, 180, 255, 100)
            opacity = 0.3
        else:
            brushColor = (255, 255, 255, 0)
            opacity = 0

        self.setWindowOpacity(opacity)
        qp = QtGui.QPainter(self)
        qp.setPen(QtGui.QPen(QtGui.QColor("black"), 2))
        qp.setBrush(QtGui.QColor(*brushColor))
        qp.drawRect(QtCore.QRect(self.begin, self.end))

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            QApplication.restoreOverrideCursor()
            self.close()
            self.parent.show()
        event.accept()

    def mousePressEvent(self, event):
        self.startPos = self.mouse.position

        self.begin = event.pos()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.isSnipping = False
        QApplication.restoreOverrideCursor()

        startPos = self.startPos
        endPos = self.mouse.position
        # account for retina display. #TODO how to check if device is actually using retina display
        factor = 2 if sys.platform == "darwin" else 1

        x1 = int(min(startPos[0], endPos[0]) * factor)
        y1 = int(min(startPos[1], endPos[1]) * factor)
        x2 = int(max(startPos[0], endPos[0]) * factor)
        y2 = int(max(startPos[1], endPos[1]) * factor)

        self.repaint()
        QApplication.processEvents()
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
        except Exception as e:
            if sys.platform == "darwin":
                img = ImageGrab.grab(
                    bbox=(x1 // factor, y1 // factor, x2 // factor, y2 // factor),
                    all_screens=True,
                )
            else:
                raise e
        QApplication.processEvents()

        self.close()
        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()
        self.parent.returnSnip(img)

def parse_args():
    parser = argparse.ArgumentParser(description="GUI arguments")
    parser.add_argument(
        "-t",
        "--temperature",
        type=float,
        default=0.2,
        help="Softmax sampling frequency",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="settings/config.yaml",
        help="path to config file",
    )
    parser.add_argument(
        "-m",
        "--checkpoint",
        type=str,
        default="checkpoints/weights.pth",
        help="path to weights file",
    )
    parser.add_argument("--no-cuda", action="store_true", help="Compute on CPU")
    parser.add_argument(
        "--no-resize", action="store_true", help="Resize the image beforehand"
    )
    parser.add_argument(
        "--gnome",
        action="store_true",
        help="Use gnome-screenshot to capture screenshot",
    )
    arguments = parser.parse_args()
    return arguments    
    
def main():
    arguments = parse_args()
    
    with in_model_path():
        app = QApplication(sys.argv)
        ex = App(arguments, parent=app)

        # TODO: migrate to be used as setup_dir
        user_dir = Path("/home/hanz/GitHub/toolkit/LaTeX-OCR/pix2tex/model/screenshots")
        today_dir = user_dir / datetime.now().strftime("%Y-%m-%d")
        if not os.path.exists(today_dir):
            os.makedirs(today_dir)
        ex.show()

        # rprint("[red]PRE")
        # import pandas as pd
        # df = pd.read_csv(today_dir / "history.csv")
        # print(df.shape)
        # print(df.iloc[0, :])
        
        # perform processes before closing

        # test df

        status = app.exec_()
        # close application
        sys.exit(status)



if __name__ == "__main__":
    main()
