# main_app.py

# I/O Terminal ピン配置
# CN1
# ピンO-PC:24V
# ピンO-NC:GND
# ピンo-00:溶着機11
#
# CN2
# ピンI-PC:24V
# ピンI-00:フットペダル
# ピンI-01:X軸リミットスイッチ
# ピンI-02:Y軸リミットスイッチ
# ピンI-03:非常停止ボタン
#
# その他
# 溶着機12:24V
# フットペダル:GND
# 非常停止ボタン:GND

# トラブルシューティング
# 加速度がおかしい時はDYNAMIXEL Wizard 2.0 等でモーターの Drive Mode (Address 10) を確認し、Time-based Profileになっていないか確認。
# 通常動作に戻すには，選択解除して０にする。
# Pゲインがおかしい事もある



# main_app.py

import tkinter as tk
from tkinter import messagebox
import sys

# 各ページクラスのインポート
from page_manual_control import PageManualControl
from page_dxf_editor import PageDxfEditor
# 統合されたページをインポート
from page_merged import PageMergedPreviewExecution

# ハードウェア関連
from myADconvert import ADfunc
from motion_system import MotionSystem
from io_controller import WelderController, SensorController
import config
import presets


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自動溶着機コントロールアプリ v2.1 (Merged)")
        self.geometry("1200x850")

        # --- データ共有用 ---
        default_preset = list(presets.WELDING_PRESETS.keys())[0]
        self.shared_data = {
            "weld_points": [],
            "preset_name": default_preset
        }

        # --- ハードウェア初期化 ---
        self.hardware = {
            "dio": None, "motion": None, "welder": None, "sensors": {}, "emergency_sensor": None
        }
        self._init_hardware()

        # --- 画面コンテナ ---
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.pages = {}
        # ページリストを変更（統合ページを使用）
        page_classes = (PageManualControl, PageDxfEditor, PageMergedPreviewExecution)

        for PageClass in page_classes:
            page_name = PageClass.__name__
            frame = PageClass(parent=container, controller=self)
            self.pages[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_page("PageManualControl")

    def _init_hardware(self):
        print("ハードウェアを初期化しています...")
        try:
            dio = ADfunc('DIO')
            if not dio.init("DIO000"):
                messagebox.showerror("エラー", "CONTEC DIOの初期化に失敗しました。")
                return
            self.hardware["dio"] = dio
            self.hardware["motion"] = MotionSystem(log_callback=print)
            self.hardware["welder"] = WelderController(dio)
            self.hardware["sensors"] = {
                'x': SensorController(dio, config.LIMIT_SWITCH_X_PIN),
                'y': SensorController(dio, config.LIMIT_SWITCH_Y_PIN)
            }
            self.hardware["emergency_sensor"] = SensorController(dio, config.EMERGENCY_STOP_PIN)
            print("ハードウェア初期化完了")
        except Exception as e:
            messagebox.showerror("初期化エラー", f"ハードウェア初期化中にエラーが発生しました:\n{e}")

    def show_page(self, page_name):
        if page_name not in self.pages:
            return
        frame = self.pages[page_name]
        frame.tkraise()
        if hasattr(frame, 'on_page_show'):
            frame.on_page_show()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()