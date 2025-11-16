# check_pin_status.py
#
# 指定したデジタル入力ピンの状態を監視（ポーリング）するだけの
# 独立したテスト用スクリプトです。
# io_controller.py や config.py などの他のファイルは一切不要です。
#
# 実行前に、myADconvert.py がこのファイルと同じフォルダにあることを確認してください。

import time
import sys
import platform

# myADconvert.py が同じフォルダにあることを前提とします
try:
    # myADconvert.py (ファイル) から ADfunc クラスをインポート
    from myADconvert import ADfunc
except ImportError:
    print("エラー: myADconvert.py が見つかりません。", file=sys.stderr)
    print("このスクリプトと同じフォルダに配置してください。", file=sys.stderr)
    sys.exit(1)

# --- 設定項目 ---

# 1. CONTEC デバイス名 (通常は "DIO000")
DEVICE_NAME = "DIO000"

# 2. 状態を確認したいデジタル入力(DI)チャンネル番号
# (物理的な緊急停止ボタンを接続したピン番号を指定してください)
PIN_TO_CHECK = 3


# --- 設定項目ここまで ---

def main():
    """
    DIOデバイスを初期化し、指定した入力ピンの状態を読み取り続ける
    """

    # 'DIO' タイプで ADfunc を初期化
    ad_converter = ADfunc('DIO')

    # デバイスの初期化
    if not ad_converter.init(DEVICE_NAME):
        print(f"エラー: デバイス '{DEVICE_NAME}' の初期化に失敗しました。", file=sys.stderr)
        print("1. CONTEC I/OユニットがPCに正しく接続されているか確認してください。")
        print("2. CONTECのドライバがPCにインストールされているか確認してください。")
        print(f"3. デバイス名が '{DEVICE_NAME}' で正しいか確認してください。")
        return

    print(f"デバイス '{DEVICE_NAME}' の初期化に成功しました。")
    print(f"DIピン {PIN_TO_CHECK} の監視を開始します。")
    print("ボタンを押したり離したりして、下の表示が変わるか確認してください。")
    print("プログラムを終了するには Ctrl+C を押してください。\n")

    last_raw_state = -1  # 前回の生の値を保持する変数

    try:
        # 無限ループで状態を監視
        while True:
            # デジタル入力チャンネルからボタンの生の値を読み取る
            # (myADconvert.py v3.0.0 のインターフェース定義に従い、
            #  ADfunc('DIO') の read を呼び出す際も AI_DI 引数を渡します)
            raw_state = ad_converter.read(channel=PIN_TO_CHECK, AI_DI='DI')

            # 状態が変化した時だけ、コンソールに結果を表示
            if raw_state != last_raw_state:

                # io_controller.py の SensorController のロジック（not state）に基づく判定
                # (「押された」ときに 0 [Low] になる回路を想定)
                is_triggered = not bool(raw_state)

                print(f"--- 状態変化検知 --- ({time.strftime('%H:%M:%S')})")
                print(f"  [生データ] read() の戻り値: {raw_state}")
                print(f"  [判定ロジック] is_triggered (not raw_state): {is_triggered}")

                if is_triggered:
                    # raw_state が 0 だった場合
                    print("  [状態] -> 押されている (と判定)")
                else:
                    # raw_state が 1 (または0以外) だった場合
                    print("  [状態] -> 押されていない (と判定)")

                last_raw_state = raw_state  # 現在の状態を保存

            # ポーリング間隔 (0.1秒)
            time.sleep(0.1)

    except KeyboardInterrupt:
        # Ctrl+C が押されたらループを抜ける
        print("\n監視を終了します。")
    except Exception as e:
        print(f"\n実行中にエラーが発生しました: {e}", file=sys.stderr)
    finally:
        # プログラム終了時にデバイスを安全に終了させる
        print("デバイスを終了処理中...")
        ad_converter.exit()
        print("デバイスを正常に終了しました。")


if __name__ == "__main__":
    main()