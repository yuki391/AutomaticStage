# ui_components.py

"""
page_welding_control .py のUI部品（ウィジェット）を作成するための関数をまとめたモジュールです。
UIのレイアウトと、ボタンが押されたときの動作を分離し、コードの可読性と管理性を向上させます。
"""

import tkinter as tk
from tkinter import ttk


def create_main_operation_widgets(parent_frame, page):
    """メイン操作（溶着開始、CSV読込など）のUIを作成する"""
    frame = tk.Frame(parent_frame)
    frame.pack(fill='x', pady=5)

    page.start_btn = tk.Button(frame, text="① 溶着開始フロー", command=page.start_welding_flow)
    page.start_btn.pack(side='left', padx=5, pady=5)

    page.load_btn = tk.Button(frame, text="CSVから経路読込", command=page.load_from_csv)
    page.load_btn.pack(side='left', padx=5, pady=5)

    back_btn = tk.Button(frame, text="<< DXF編集ページに戻る",
                         command=lambda: page.controller.show_page("PageDxfEditor"))
    back_btn.pack(side='right', padx=5, pady=5)


def create_calibration_widgets(parent_frame, page):
    """傾斜・距離キャリブレーションのUIを作成する"""
    container = tk.Frame(parent_frame)
    container.pack(fill='x', pady=5)

    # 傾斜キャリブレーション
    calib_frame = ttk.LabelFrame(container, text="傾斜キャリブレーション")
    calib_frame.pack(side='left', fill='x', expand=True, padx=5)
    page.calib_points_var = tk.StringVar(value="3")
    rb3 = ttk.Radiobutton(calib_frame, text="3点測定", variable=page.calib_points_var, value="3")
    rb3.pack(side='left', padx=5)
    rb16 = ttk.Radiobutton(calib_frame, text="16点測定", variable=page.calib_points_var, value="16")
    rb16.pack(side='left', padx=5)
    page.calib_start_btn = tk.Button(calib_frame, text="開始", command=page.run_calibration)
    page.calib_start_btn.pack(side='left', padx=10)

    # 距離キャリブレーション
    dist_calib_frame = ttk.LabelFrame(container, text="距離キャリブレーション")
    dist_calib_frame.pack(side='left', fill='x', expand=True, padx=5)
    page.calib_axis_var = tk.StringVar(value="x")
    axis_menu = ttk.OptionMenu(dist_calib_frame, page.calib_axis_var, "x", "x", "y")
    axis_menu.pack(side='left', padx=5)
    tk.Label(dist_calib_frame, text="目標:").pack(side='left')
    page.target_dist_entry = tk.Entry(dist_calib_frame, width=8)
    page.target_dist_entry.insert(0, "500.0")
    page.target_dist_entry.pack(side='left')
    move_btn = tk.Button(dist_calib_frame, text="移動", command=page.run_calib_move)
    move_btn.pack(side='left', padx=5)
    tk.Label(dist_calib_frame, text="実測:").pack(side='left')
    page.actual_dist_entry = tk.Entry(dist_calib_frame, width=8)
    page.actual_dist_entry.pack(side='left')
    calc_btn = tk.Button(dist_calib_frame, text="適用", command=page.calculate_and_apply)
    calc_btn.pack(side='left', padx=5)


def create_manual_control_widgets(parent_frame, page):
    """手動操作のUIを作成する"""
    frame = ttk.LabelFrame(parent_frame, text="手動操作")
    frame.pack(fill='x', pady=10, padx=5)

    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=5)
    page.homing_button = tk.Button(btn_frame, text="XY原点復帰", command=page.run_homing_sequence)
    page.homing_button.pack(side='left', padx=10)
    page.z_origin_btn = tk.Button(btn_frame, text="Z軸の現在地を原点に", command=page.run_set_z_rot_origin)
    page.z_origin_btn.pack(side='left', padx=10)

    page.create_position_control(frame, "X軸", "mm", "x")
    page.create_position_control(frame, "Y軸", "mm", "y")
    page.create_advanced_control(frame, "Z軸", "mm", "z")



def create_emergency_stop_widgets(parent_frame, page):
    """緊急停止とログのUIを作成する"""
    container = tk.Frame(parent_frame)
    container.pack(fill='both', expand=True)

    stop_frame = tk.Frame(container)
    stop_frame.pack(fill='x', pady=10)
    page.stop_btn = tk.Button(stop_frame, text="緊急停止", bg="red", fg="white", font=("メイリオ", 10, "bold"),
                              command=page.on_emergency_stop)
    page.stop_btn.pack(side='left', padx=5)
    page.recover_btn = tk.Button(stop_frame, text="復帰", command=page.on_recovery, state='disabled')
    page.recover_btn.pack(side='left', padx=5)

    page.status_label = tk.Label(container, text="待機中", anchor='w')
    page.status_label.pack(fill='x')

    log_frame = ttk.LabelFrame(container, text="ログ")
    log_frame.pack(fill='both', expand=True, pady=5)
    page.log_text = tk.Text(log_frame, height=10, state='disabled', bg='black', fg='lightgray', font=("Courier", 9))
    page.log_text.pack(fill='both', expand=True, padx=5, pady=5)