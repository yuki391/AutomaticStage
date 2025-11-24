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


import tkinter as tk
from page_dxf_editor import PageDxfEditor
from page_welding_control import PageWeldingControl
from presets import WELDING_PRESETS

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("自動溶着機コントロールアプリ")
        self.geometry("1200x800")

        # プリセットリストの最初の項目をデフォルトのプリセット名として取得
        default_preset = list(WELDING_PRESETS.keys())[0]

        # ページ間で共有するデータを保持する辞書
        self.shared_data = {
            "weld_points": [],
            "preset_name": default_preset  # 取得した名前をデフォルト値として設定
        }

        # すべてのページを配置するコンテナフレーム
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # ページを辞書に格納
        self.pages = {}
        for Page in (PageDxfEditor, PageWeldingControl):
            page_name = Page.__name__
            frame = Page(parent=container, controller=self)
            self.pages[page_name] = frame
            # 各ページを同じグリッド位置に配置
            frame.grid(row=0, column=0, sticky="nsew")

        # 最初に表示するページを指定
        self.show_page("PageDxfEditor")

    def show_page(self, page_name):
        """指定された名前のページを最前面に表示する"""
        frame = self.pages[page_name]
        frame.tkraise()
        # ページが表示されるときに実行したい処理がある場合、
        # そのページの on_page_show メソッドを呼び出す
        if hasattr(frame, 'on_page_show'):
            frame.on_page_show()


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
