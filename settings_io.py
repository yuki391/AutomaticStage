import json
import os
from typing import Dict, Any

# settings.json をこのモジュールと同じフォルダに置く（実行カレントディレクトリに依存しない）
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(MODULE_DIR, "settings.json")

def load_settings() -> Dict[str, Any]:
    """settings.json を読み込んで辞書を返す。なければ空辞書を返す。"""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        # 呼び出し元でログを出したいので例外を潰さず空を返す
        print(f"[settings_io] load_settings: エラー {e}")
        return {}

def save_settings(d: Dict[str, Any]) -> bool:
    """辞書 d を settings.json に保存する。成功したら True を返す。"""
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[settings_io] save_settings: 書き込みに失敗しました: {e}")
        return False