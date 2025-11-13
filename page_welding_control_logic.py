import threading
import time
from tkinter import messagebox, filedialog
from procedures import run_tilt_calibration, teach_origin_by_jog, run_preview
from csv_handler import load_path_from_csv


class WeldingControlLogic:
    """
    ロジック部分を切り出したクラス。

    - `main` は元の PageWeldingControl インスタンスを想定し、
      .motion, .welder, .sensors, .dio, .active_preset, .controller などの
      属性へアクセスする。
    - UI 呼び出し（ボタンコマンド等）は main がこのクラスのメソッドを呼ぶ。
    """

    def __init__(self, main):
        self.main = main
        self.stop_event = getattr(main, 'stop_event', threading.Event())
        # 状態フラグは main のものを優先して使う
        if not hasattr(self.main, 'is_moving'):
            self.main.is_moving = False

    # --- スレッドユーティリティ ---
    def run_in_thread(self, target, *args):
        t = threading.Thread(target=target, args=args)
        t.daemon = True
        t.start()
        return t

    # --- モーター接続確認 ---
    def check_motor_connection(self):
        self.main.add_log("モーターとの接続を確認しています...")
        if not getattr(self.main, 'motion', None):
            self.main.add_log("!!! エラー: モーションシステムが初期化されていません。")
            return
        if not self.main.motion.check_connection('x'):
            self.main.add_log("!!! 警告: モーターからの応答がありません。")
        else:
            self.main.add_log("モーターとの接続は正常です。")

    # --- 溶着フロー ---
    def start_welding_flow(self):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        points = self.main.controller.shared_data.get('weld_points')
        if not points:
            messagebox.showwarning("データなし", "溶着データがありません。")
            return
        self.stop_event.clear()
        self.run_in_thread(self._welding_flow_thread, points)

    def _welding_flow_thread(self, points):
        try:
            self.main.add_log("--- 溶着プロセス開始 ---")
            self.main.motion.home_all_axes(self.main.sensors)
            if self.stop_event.is_set():
                self.main.add_log("中断されました。")
                return

            work_origin = teach_origin_by_jog(self.main.motion)
            if work_origin is None or self.stop_event.is_set():
                self.main.add_log("中断されました。")
                return

            if not run_preview(self.main.motion, points, work_origin, self.main.active_preset):
                self.main.add_log("プレビューに失敗したため、フローを停止します。")
                return
            if self.stop_event.is_set():
                self.main.add_log("中断されました。")
                return

            while True:
                ans = messagebox.askyesnocancel(
                    "最終確認",
                    "プレビューが完了しました。\nこの位置で溶着を開始しますか？\n\n"
                    "「はい」: 溶着開始\n"
                    "「いいえ」: もう一回プレビューを表示\n"
                    "「キャンセル」: 中止"
                )
                if ans is True:
                    break
                elif ans is False:
                    self.main.add_log("ユーザー操作: もう一回プレビューを表示します。")
                    ok = run_preview(self.main.motion, points, work_origin, self.main.active_preset)
                    if not ok:
                        self.main.add_log("プレビューに失敗したため、フローを停止します。")
                        return
                    if self.stop_event.is_set():
                        self.main.add_log("中断されました。")
                        return
                    continue
                else:
                    self.main.add_log("ユーザーにより操作が中断されました。")
                    return

            self.main.add_log(f"--- 溶着ジョブ開始 ({len(points)}点) ---")
            for i, p in enumerate(points):
                if self.stop_event.is_set():
                    self.main.add_log("中断されました。")
                    return

                target_x = work_origin[0] + p['x']
                target_y = work_origin[1] + p['y']
                self.main.add_log(f"({i + 1}/{len(points)}) 点へ移動: X={target_x:.2f}, Y={target_y:.2f}")

                self.main.motion.move_xy_abs(target_x, target_y, self.main.active_preset)

                if i == 0:
                    self.main.add_log("-> 初回移動のため1秒待機します。")
                    time.sleep(1)
                self.main.motion.execute_welding_press(self.main.welder, self.main.active_preset)

            self.main.add_log("--- 溶着ジョブ完了 ---")
            self.main.motion.return_to_origin()

        except Exception as e:
            self.main.add_log(f"エラーが発生しました: {e}")
            messagebox.showerror("実行時エラー", f"ジョブ実行中にエラーが発生しました:\n{e}")

    # --- キャリブレーション ---
    def run_calibration(self):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        num_points = int(self.main.calib_points_var.get())
        self.main.add_log(f"--- {num_points}点での傾斜キャリブレーションを開始します ---")
        self.run_in_thread(self._calibration_thread, num_points)

    def _calibration_thread(self, num_points):
        plane = run_tilt_calibration(self.main.motion, num_points, self.main.active_preset)
        if plane:
            self.main.motion.set_tilt_plane(plane)
            self.main.add_log("傾斜キャリブレーションが完了し、補正データを適用しました。")
        else:
            self.main.add_log("キャリブレーションが中止または失敗しました。")

    # --- CSV 読込 ---
    def load_from_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        points = load_path_from_csv(path)
        if points:
            self.main.controller.shared_data['weld_points'] = points
            # UI 更新は main に委譲
            if hasattr(self.main, 'update_status'):
                self.main.update_status()
            self.main.add_log(f"CSVから {len(points)} 点を読み込みました。")

    # --- 距離移動（キャリブレーション補助） ---
    def run_calib_move(self):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        if not getattr(self.main.motion, 'is_homed', False):
            messagebox.showerror("エラー", "最初に原点復帰を実行してください。")
            return
        try:
            target_dist = float(self.main.target_dist_entry.get())
            axis = self.main.calib_axis_var.get()
            self.run_in_thread(self._calib_move_thread, axis, target_dist)
        except ValueError:
            messagebox.showerror("入力エラー", "目標距離には数値を入力してください。")

    def _calib_move_thread(self, axis, distance):
        self.main.add_log(f"--- 距離キャリブレーション: {axis.upper()}軸を +{distance}mm 移動します ---")
        if axis == 'x':
            self.main.motion.move_xy_rel(dx_mm=distance, dy_mm=0, preset=self.main.active_preset)
        elif axis == 'y':
            self.main.motion.move_xy_rel(dx_mm=0, dy_mm=distance, preset=self.main.active_preset)
        self.main.add_log("移動完了。実際の移動距離を測定し、入力してください。")

    # --- キャリブレーション適用 ---
    def calculate_and_apply(self):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        try:
            target_dist = float(self.main.target_dist_entry.get())
            actual_dist = float(self.main.actual_dist_entry.get())
        except ValueError:
            messagebox.showerror("入力エラー", "目標距離と実測値には数値を入力してください。")
            return
        if actual_dist == 0:
            messagebox.showerror("計算エラー", "実測値に0は入力できません。")
            return
        axis = self.main.calib_axis_var.get()
        if axis not in ('x', 'y'):
            messagebox.showerror("エラー", f"未対応の軸が選択されています: {axis}")
            return
        current_ppm = self.main.motion.pulses_per_mm_x if axis == 'x' else self.main.motion.pulses_per_mm_y
        correction_factor = target_dist / actual_dist
        new_ppm = current_ppm * correction_factor
        msg = (
            f"{axis.upper()}軸 距離キャリブレーションの適用\n\n"
            f"目標距離: {target_dist:.4f} mm\n"
            f"実測距離: {actual_dist:.4f} mm\n\n"
            f"補正係数: {correction_factor:.6f}\n"
            f"現在の pulses/mm: {current_ppm:.6f}\n"
            f"補正後の pulses/mm: {new_ppm:.6f}\n\n"
            "この変更を適用してよろしいですか？"
        )
        if not messagebox.askokcancel("適用の確認", msg):
            self.main.add_log("ユーザーがキャリブレーションの適用をキャンセルしました。")
            return
        try:
            self.main.motion.update_pulses_per_mm(axis, new_ppm)
            self.main.add_log(f"{axis.upper()}軸の pulses/mm を {current_ppm:.6f} -> {new_ppm:.6f} に更新しました。")
            messagebox.showinfo("適用完了", f"{axis.upper()}軸のキャリブレーションを適用しました。")
        except Exception as e:
            self.main.add_log(f"キャリブレーション適用中にエラーが発生しました: {e}")
            messagebox.showerror("適用エラー", f"キャリブレーションの適用に失敗しました:\n{e}")

    # --- 手動移動 ---
    def move_axis(self, axis, direction):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        if self.main.is_moving:
            self.main.add_log("警告: 現在、別の移動命令を実行中です。")
            return
        if axis in ('x', 'y') and not getattr(self.main.motion, 'is_homed', False):
            self.main.add_log("エラー: XY軸を動かすには、先に「XY原点復帰」を実行してください。")
            messagebox.showerror("エラー", "機械のXY座標が不明です。\n最初に「XY原点復帰」を実行してください。")
            return
        try:
            step = float(self.main.step_entries[axis].get())
            amount = step * direction
            self.run_in_thread(self._move_thread, axis, amount)
        except Exception:
            self.main.add_log("エラー: 移動量には数値を入力してください。")

    def _move_thread(self, axis, amount):
        try:
            self.main.is_moving = True
            self._set_jog_buttons_enabled(False)
            self.main.homing_button.config(state='disabled')
            self.main.z_origin_btn.config(state='disabled')
            self.main.add_log(f"手動操作: {axis.upper()}軸を {amount:+.2f}mm 動かします...")
            if axis == 'x':
                self.main.motion.move_xy_rel(dx_mm=amount, dy_mm=0, preset=self.main.active_preset)
            elif axis == 'y':
                self.main.motion.move_xy_rel(dx_mm=0, dy_mm=amount, preset=self.main.active_preset)
            elif axis == 'z':
                self.main.motion.move_z_rel(amount)
            self.main.add_log(f"完了: {axis.upper()}軸 移動完了。")
        finally:
            self.main.is_moving = False
            self._set_jog_buttons_enabled(True)
            self.main.homing_button.config(state='normal')
            self.main.z_origin_btn.config(state='normal')

    def _set_jog_buttons_enabled(self, enabled):
        state = 'normal' if enabled else 'disabled'
        for b in getattr(self.main, 'jog_buttons', []):
            try:
                b.config(state=state)
            except Exception:
                pass

    # --- 原点復帰 ---
    def run_homing_sequence(self):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        if self.main.is_moving:
            self.main.add_log("警告: 現在、別の移動命令が実行中です。")
            return
        if messagebox.askyesno("確認", "XY原点復帰を開始します。\n機械周りに障害物がないか確認してください。"):
            self.run_in_thread(self._homing_thread)

    def _homing_thread(self):
        try:
            self.main.is_moving = True
            self.main.homing_button.config(state='disabled')
            self.main.z_origin_btn.config(state='disabled')
            self._set_jog_buttons_enabled(False)

            self.main.add_log("--- 原点復帰の前にZ軸を安全な高さへ移動します ---")
            self.main.motion.move_z_abs_pulse(self.main.main_config_SAFE_Z_PULSE if hasattr(self.main, 'main_config_SAFE_Z_PULSE') else 2100)
            self.main.motion.home_all_axes(self.main.sensors)

            if self.main.motion.is_homed:
                self._set_jog_buttons_enabled(True)
                self.main.add_log("原点復帰が完了しました。手動操作が可能です。")
        finally:
            self.main.is_moving = False
            self.main.homing_button.config(state='normal')
            self.main.z_origin_btn.config(state='normal')
            if getattr(self.main, 'motion', None) and self.main.motion.is_homed:
                self._set_jog_buttons_enabled(True)

    # --- Z原点設定 ---
    def run_set_z_origin(self):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        if self.main.is_moving:
            self.main.add_log("警告: 現在、別の移動命令が実行中です。")
            return
        if messagebox.askyesno("確認", "現在のZ軸の位置を、新しい原点(0)として設定しますか？"):
            self.run_in_thread(self._set_z_origin_thread)

    def _set_z_origin_thread(self):
        try:
            self.main.is_moving = True
            self._set_jog_buttons_enabled(False)
            self.main.homing_button.config(state='disabled')
            self.main.z_origin_btn.config(state='disabled')
            self.main.motion.set_z_origin_here()
            self.main.add_log("Z軸の原点設定完了。")
        finally:
            self.main.is_moving = False
            self.main.homing_button.config(state='normal')
            self.main.z_origin_btn.config(state='normal')
            self._set_jog_buttons_enabled(True)

    # --- 電流指定で移動 ---
    def set_current_only_move(self, axis, direction):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        if self.main.is_moving:
            self.main.add_log("警告: 別の移動命令が実行中です。")
            return
        try:
            current = float(self.main.step_entries[f"{axis}_adv_cur"].get())
            self.run_in_thread(self._current_only_thread, axis, current * direction)
        except ValueError:
            self.main.add_log("エラー: 電流値には数値を入力してください。")

    def _current_only_thread(self, axis, current):
        try:
            self.main.is_moving = True
            self._set_jog_buttons_enabled(False)
            self.main.motion.set_axis_current(axis, current)
        finally:
            self.main.is_moving = False
            self._set_jog_buttons_enabled(True)

    # --- 連続移動停止 ---
    def stop_continuous(self, axis):
        if not getattr(self.main, 'motion', None):
            messagebox.showerror("エラー", "モーションシステムが初期化されていません。")
            return
        if self.main.is_moving:
            self.main.add_log("警告: 別の移動命令が実行中です。")
            return
        self.run_in_thread(self._stop_thread, axis)

    def _stop_thread(self, axis):
        try:
            self.main.is_moving = True
            self._set_jog_buttons_enabled(False)
            self.main.motion.stop_continuous_move(axis)
        finally:
            self.main.is_moving = False
            self._set_jog_buttons_enabled(True)

    # --- 緊急停止と復帰 ---
    def on_emergency_stop(self):
        self.stop_event.set()
        if getattr(self.main, 'motion', None):
            try:
                self.main.motion.emergency_stop()
            except Exception:
                pass
        if getattr(self.main, 'welder', None):
            try:
                self.main.welder.turn_off()
                self.main.add_log("!!! 溶着機をOFFにしました。 !!!")
            except Exception:
                pass
        if hasattr(self.main, 'recover_btn'):
            self.main.recover_btn.config(state='normal')
        if hasattr(self.main, 'stop_btn'):
            self.main.stop_btn.config(state='disabled')
        messagebox.showwarning("緊急停止",
                               "全モーターのトルクがOFFになり、溶着機が停止しました。\n機械を手で安全な範囲に移動させた後、「復帰"+
                               ""+"」ボタンを押してください。")

    def on_recovery(self):
        if hasattr(self.main, 'recover_btn'):
            self.main.recover_btn.config(state='disabled')
        self.run_in_thread(self._recovery_thread)

    def _recovery_thread(self):
        if getattr(self.main, 'motion', None):
            try:
                self.main.motion.recover_from_stop()
            except Exception:
                pass
        self.stop_event.clear()
        if hasattr(self.main, 'stop_btn'):
            self.main.stop_btn.config(state='normal')
        self.main.add_log("復帰完了。待機状態に戻りました。")
