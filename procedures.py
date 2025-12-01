# procedures.py

import config
import numpy as np
import time
from tkinter import messagebox
import presets


def run_homing_sequence(motion_system, sensors):
    motion_system.log("--- 原点復帰シーケンス開始 (高レベルプレースホルダ) ---")
    motion_system.home_all_axes(sensors)
    motion_system.log("--- 原点復帰シーケンス完了 (高レベルプレースホルダ) ---")


def run_tilt_calibration(motion_system, num_points, preset):
    motion_system.log(f"--- {num_points}点での傾斜キャリブレーション実行 ---")

    if motion_system.homing_offsets['z'] == 0:
        motion_system.log("エラー: 傾斜キャリブレーションの前にZ軸の原点設定を行ってください。")
        messagebox.showerror("エラー",
                             "最初に手動操作でZ軸をワーク表面に接触させ、「Z軸の現在地を原点に」ボタンを押してください。")
        return None

    max_x = config.MACHINE_MAX_X_MM
    max_y = config.MACHINE_MAX_Y_MM

    points_to_measure = []
    if num_points == 3:
        points_to_measure = [(0.1 * max_x, 0.1 * max_y), (0.9 * max_x, 0.5 * max_y), (0.5 * max_x, 0.9 * max_y)]
    elif num_points == 16:
        for i in range(4):
            for j in range(4):
                x = (max_x * 0.8 / 3) * i + (max_x * 0.1)
                y = (max_y * 0.8 / 3) * j + (max_y * 0.1)
                points_to_measure.append((x, y))
    else:
        motion_system.log(f"エラー: 未対応の点数({num_points})です。")
        return None

    measured_data = []
    motion_system.move_z_abs_pulse(config.SAFE_Z_PULSE)

    for i, (x, y) in enumerate(points_to_measure):
        motion_system.log(f"({i + 1}/{num_points}) 点 ({x:.1f}, {y:.1f}) の高さを測定します...")
        motion_system.move_xy_abs(x, y, preset)

        contact_pulse = motion_system.descend_until_contact(preset)

        if contact_pulse is None:
            motion_system.log("!!! Z軸の位置取得に失敗したため、キャリブレーションを中止します。")
            messagebox.showerror("エラー", "Z軸の位置取得に失敗しました。")
            return None

        z_mm = motion_system._pulses_to_mm(contact_pulse, 'z')
        measured_data.append([x, y, z_mm])

        motion_system.move_z_abs_pulse(config.SAFE_Z_PULSE)

    motion_system.return_to_origin()

    if len(measured_data) < 3:
        motion_system.log("エラー: 平面計算に必要なデータが不足しています。")
        return None

    A = np.array([[d[0], d[1], 1] for d in measured_data])
    B = np.array([d[2] for d in measured_data])

    coeffs, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
    a, b, c = coeffs

    plane_coeffs = {'a': a, 'b': b, 'c': c}
    motion_system.log("--- 傾斜キャリブレーション完了 ---")
    motion_system.log(f"計算された傾斜平面: z = {a:.4f}x + {b:.4f}y + {c:.4f}")
    return plane_coeffs


def teach_origin_by_jog(motion_system):
    motion_system.log("--- 加工原点ティーチング開始 ---")
    motion_system.log("UI上でジョグ操作を行い、原点を決定後、ダイアログで 'OK' を押してください。")

    messagebox.showinfo("加工原点設定",
                        "手動操作でワークの原点に移動し、位置が決まったらこのダイアログの 'OK' を押してください。")

    work_origin = (motion_system.current_pos['x'], motion_system.current_pos['y'])

    motion_system.log(f"加工原点が ({work_origin[0]:.2f}, {work_origin[1]:.2f}) に設定されました。")
    return work_origin


def run_preview(motion, points, work_origin, preset):
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    # ★★★ ここからが修正箇所 ★★★
    # ★★★ 'motion_system' を正しい引数名 'motion' に修正 ★★★
    # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
    motion.log("--- 加工範囲のプレビューを開始します ---")

    if not points:
        motion.log("エラー: プレビューする点がありません。")
        return False

    path_x = [p['x'] for p in points]
    path_y = [p['y'] for p in points]

    min_x_abs = work_origin[0] + min(path_x)
    max_x_abs = work_origin[0] + max(path_x)
    min_y_abs = work_origin[1] + min(path_y)
    max_y_abs = work_origin[1] + max(path_y)

    motion.log(f"計算上の加工範囲: X=[{min_x_abs:.2f} ~ {max_x_abs:.2f}], Y=[{min_y_abs:.2f} ~ {max_y_abs:.2f}]")

    tolerance = 1e-6
    if (min_x_abs < -tolerance or max_x_abs > config.MACHINE_MAX_X_MM + tolerance or
            min_y_abs < -tolerance or max_y_abs > config.MACHINE_MAX_Y_MM + tolerance):
        error_msg = (
            f"加工範囲がマシンの可動範囲を超えています！\n\n"
            f"計算上の加工範囲:\n"
            f"  X: {min_x_abs:.2f} ～ {max_x_abs:.2f} mm\n"
            f"  Y: {min_y_abs:.2f} ～ {max_y_abs:.2f} mm\n\n"
            f"マシンの最大可動範囲:\n"
            f"  X: 0 ～ {config.MACHINE_MAX_X_MM} mm\n"
            f"  Y: 0 ～ {config.MACHINE_MAX_Y_MM} mm\n\n"
            f"加工原点の位置、またはDXFデータが正しいか確認してください。"
        )
        motion.log(f"!!! エラー: {error_msg}")
        messagebox.showerror("範囲チェックエラー", error_msg)
        return False

    corners = [
        (min_x_abs, min_y_abs),
        (max_x_abs, min_y_abs),
        (max_x_abs, max_y_abs),
        (min_x_abs, max_y_abs),
        (min_x_abs, min_y_abs)
    ]

    motion.move_z_abs_pulse(config.SAFE_Z_PULSE)

    for i, (x, y) in enumerate(corners):
        motion.log(f"プレビュー移動 ({i + 1}/{len(corners)}): X={x:.2f}, Y={y:.2f}")
        motion.move_xy_abs(x, y, preset, precise_mode=True)
        time.sleep(0.5)

    motion.log("--- プレビュー完了 ---")
    return True

