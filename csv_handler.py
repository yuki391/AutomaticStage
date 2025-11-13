# csv_handler.py

import csv
import os
import datetime


def save_path_to_csv(filepath, path_data, timestamp_obj):
    """
    x, y座標のリストを指定されたタイムスタンプと共にCSVファイルに保存する
    """
    if not path_data:
        print("データがないため、CSVファイルは作成されませんでした。")
        return False

    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            timestamp_str = timestamp_obj.strftime("%Y-%m-%d %H:%M:%S")
            csvfile.write(f"# Data Generated/Modified: {timestamp_str}\n")

            # フィールド名を x, y のみに変更
            fieldnames = ['x', 'y']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(path_data)

        print(f"✅ 結果を '{filepath}' に保存しました。合計 {len(path_data)} 点")
        return True
    except IOError as e:
        print(f"エラー: ファイル '{filepath}' への書き込みに失敗しました - {e}")
        return False


def load_path_from_csv(filepath):
    """
    x, y のみのシンプルなCSVファイルを読み込む
    """
    if not os.path.exists(filepath):
        print(f"エラー: ファイル '{filepath}' が見つかりません。")
        return []

    points = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # コメント行(#)を読み飛ばす
            for line in f:
                if not line.strip().startswith('#'):
                    break

            # ループを抜けた後、残りの部分を読み込む
            # DictReaderに渡すために、一度読み飛ばした行と残りの行を結合する
            # ただし、ファイルポインタは進んでいるので、ヘッダー行から読み込ませる
            f.seek(0)  # ポインタを最初に戻す
            content_after_comments = [row for row in f if not row.strip().startswith('#')]

            reader = csv.DictReader(content_after_comments)
            for row in reader:
                # 角度(angle)の読み込みを削除
                points.append({
                    'x': float(row['x']),
                    'y': float(row['y']),
                })
        print(f"'{filepath}' から {len(points)} 点のデータを読み込みました。")
        return points
    except Exception as e:
        print(f"エラー: CSVファイルの読み込みに失敗しました - {e}")
        return []