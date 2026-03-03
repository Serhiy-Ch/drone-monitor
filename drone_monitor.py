from collections import deque


class DroneMonitor:
    def __init__(self,
                 drone_name="Тест-Дрон",
                 safe_battery_level=25,
                 window_size=10,
                 warn_thr=30,
                 severe_thr=15,
                 critical_thr=5,
                 degraded_enter=6,
                 degraded_exit=3,
                 failsafe_enter_severe=8,
                 failsafe_exit_severe=4,
                 failsafe_enter_critical=3):

        self.drone_name = drone_name
        self.safe_battery_level = safe_battery_level

        # звʼязок
        self.current_connection = "SIM1"
        self.backup_connection = "SIM2"

        # база
        self.home_coords = (50.4501, 30.5234)

        # thresholds
        self.warn_thr = warn_thr
        self.severe_thr = severe_thr
        self.critical_thr = critical_thr

        # history window: 0 OK, 1 WARNING, 2 SEVERE, 3 CRITICAL
        self.level_history = deque(maxlen=window_size)

        # hysteresis
        self.degraded_enter = degraded_enter
        self.degraded_exit = degraded_exit
        self.failsafe_enter_severe = failsafe_enter_severe
        self.failsafe_exit_severe = failsafe_exit_severe
        self.failsafe_enter_critical = failsafe_enter_critical

        self.link_state = "NORMAL"  # NORMAL | DEGRADED_LINK | FAILSAFE

    # ---------- 3 levels ----------
    def _signal_level(self, signal_strength: int) -> int:
        if signal_strength < self.critical_thr:
            return 3
        if signal_strength < self.severe_thr:
            return 2
        if signal_strength < self.warn_thr:
            return 1
        return 0

    # ---------- window + hysteresis ----------
    def _update_link_state(self, signal_strength: int):
        lvl = self._signal_level(signal_strength)
        self.level_history.append(lvl)

        warning_count = sum(1 for x in self.level_history if x >= 1)
        severe_count = sum(1 for x in self.level_history if x >= 2)
        critical_count = sum(1 for x in self.level_history if x >= 3)

        # FAILSAFE enter/exit
        if self.link_state != "FAILSAFE":
            if severe_count >= self.failsafe_enter_severe or critical_count >= self.failsafe_enter_critical:
                self.link_state = "FAILSAFE"
        else:
            if severe_count <= self.failsafe_exit_severe and critical_count == 0:
                # повертаємось мʼякше
                self.link_state = "DEGRADED_LINK" if warning_count >= self.degraded_exit else "NORMAL"

        # DEGRADED enter/exit (only if not FAILSAFE)
        if self.link_state != "FAILSAFE":
            if self.link_state == "NORMAL" and warning_count >= self.degraded_enter:
                self.link_state = "DEGRADED_LINK"
            elif self.link_state == "DEGRADED_LINK" and warning_count <= self.degraded_exit:
                self.link_state = "NORMAL"

        return self.link_state, warning_count, severe_count, critical_count, lvl

    # ---------- RISK layer (твій "мозок") ----------
    def compute_risk_score(self, battery, link_state, severe_count, critical_count):
        risk = 0

        # батарея
        if battery < self.safe_battery_level:
            risk += 4
        elif battery < self.safe_battery_level + 10:
            risk += 2

        # стан лінку
        if link_state == "DEGRADED_LINK":
            risk += 2
        elif link_state == "FAILSAFE":
            risk += 4

        # severe / critical накопичення у вікні
        risk += severe_count * 0.5
        risk += critical_count * 1.0

        return risk

    def decide_action(self, risk):
        if risk < 2:
            return "NORMAL"
        elif risk < 4:
            return "DEGRADED"
        elif risk < 6:
            return "FAILSAFE"
        else:
            return "RTL"

    # ---------- actions ----------
    def switch_connection_mode(self, signal_strength, current_gps, force_autonomous=False):
        print(f"[Перемикання] Сигнал: {signal_strength}% | Поточний звʼязок: {self.current_connection}")

        if force_autonomous:
            msg = f"FAILSAFE: Автономний режим -> база {self.home_coords} | GPS={current_gps}"
            print(msg)
            return 4, msg

        if self.current_connection == "SIM1":
            self.current_connection = self.backup_connection
            msg = f"Переключено на резервний звʼязок: {self.current_connection}"
            print(msg)
            return 3, msg

        msg = f"Сигнал слабкий навіть на {self.current_connection}. Автономний режим -> база {self.home_coords}, GPS {current_gps}"
        print(msg)
        return 4, msg

    # ---------- main telemetry check ----------
    def check_telemetry(self, battery, altitude, signal_strength, current_gps):
        print(f"\n[Перевірка] Дрон: {self.drone_name}")
        print(f"[Перевірка] Дані: battery={battery}%, altitude={altitude}м, signal={signal_strength}%, gps={current_gps}")
        print(f"[Перевірка] Мін. батарея: {self.safe_battery_level}%")

        # 1) критична батарея
        if battery < self.safe_battery_level:
            msg = f"Увага! Рівень батареї {battery}% нижче мінімуму {self.safe_battery_level}%. Наказ: RTL."
            print(msg)
            return 2, msg

        # 2) оновлюємо стан лінку (вікно + 3 рівні + гістерезис)
        state, w, s, c, lvl = self._update_link_state(signal_strength)
        lvl_name = {0: "OK", 1: "WARNING", 2: "SEVERE", 3: "CRITICAL"}[lvl]
        print(f"[Лінк] level={lvl_name} | warning={w}/{self.level_history.maxlen}, severe={s}, critical={c} | state={state}")

        # ✅✅✅ ОСЬ САМЕ ТУТ ВСТАВЛЯЄТЬСЯ ТВОЄ risk/decision ✅✅✅
        risk = self.compute_risk_score(battery, state, s, c)
        decision = self.decide_action(risk)
        print(f"[RISK] score={risk:.2f} | decision={decision}")
        # ✅✅✅ КІНЕЦЬ ВСТАВКИ ✅✅✅

        # 3) дії від "мозку"
        if decision == "RTL":
            msg = f"RTL: високий ризик {risk:.2f}"
            print(msg)
            return 2, msg

        if decision == "FAILSAFE":
            return self.switch_connection_mode(signal_strength, current_gps, force_autonomous=True)

        if decision == "DEGRADED":
            code, msg = self.switch_connection_mode(signal_strength, current_gps, force_autonomous=False)
            # якщо просто деградація без перемикань (теоретично) — повернемо 1
            return (1 if code == 0 else code), f"[DEGRADED] {msg}"

        # 4) NORMAL
        msg = "Все в нормі"
        print(msg)
        return 0, msg


if __name__ == "__main__":
    drone = DroneMonitor(drone_name="Тест-Дрон", safe_battery_level=25)

    tests = [
        ("Критична батарея", 10, 300, 90, (50.40, 30.50)),
        ("Слабкий сигнал (warning)", 60, 300, 25, (50.41, 30.51)),
        ("Слабкий сигнал (severe)", 60, 300, 12, (50.41, 30.51)),
        ("Все OK", 70, 500, 80, (50.42, 30.52)),
        ("Дуже слабкий (critical)", 70, 500, 3, (50.43, 30.53)),
    ]

    for title, b, a, s, gps in tests:
        print(f"\n=== Тест: {title} ===")
        code, msg = drone.check_telemetry(b, a, s, gps)
        print(f"Результат: code={code}, msg={msg}")
