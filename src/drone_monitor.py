import logging
from collections import deque

# --- НАЛАШТУВАННЯ ЛОГЕРА ("Чорна скринька") ---
logging.basicConfig(level=logging.INFO,format='[%(asctime)s] %(levelname)s: %(message)s', datefmt= '%H:%M:%S')

class DroneMonitor:
    def __init__(self,drone_name="Стелс-Мulti", safe_battery_level=25, window_size=10):
        self.drone_name = drone_name
        self.safe_battery_level = safe_battery_level

# Multi-Radio матриця: weight визначає можливість каналу
        self.links = { "SIM1":  {"type": "LTE", "weight": 1.0, "active": True},
                       "SIM2":  {"type": "LTE", "weight":  0.8, "active": True},
                       "RF_MESH": {"type": "RF", "weight": 0.9,  "active": False},
                       "SAT":     {"type": "SATCOM", "weight": 0.5 "active": False}
                     }
# Принцип "розділяй і відокремлюй": окрема пам'ять для кожного каналу
        self.level_history = {name:deque(maxlen=window_size) for name in self.links}
        self.bonded_mode = False
        self.link_state ="Normal"

def _signal_level(self, strength: int) -> int:
    if strength < 5: return 3
    if strength < 15: return 2
    if strength < 30: return 1
    return 0

def _update_multi_link_state(self, link_signals: dict):
    overall_quality = 0
    degraded_count = 0
    critical_count = 0
    active_links_count = 0

    for name, strength in link_signals.items():
        if name not in self.links: 
            continue

        lvl = self._signal_level(strength)
              self.level_history[name].append(lvl)
                if lvl >= 1: degraded_count += 1
                if lvl >= 3: critical_count += 1

# Зважена сума якості 
                overall_quality += strength * self.links[name].get("weigth", 1.0)

                if strength > 30:
                    active_links_count += 1

            self.bonded_mode = (active_links_count >= 2)

            if critical_count >= 2 or (degraded_count >= len(link_signals) and overall_quality < 100):
                self.link_state = "FAILSAFE"
            elif degraded_count >= 2: 
                self.link_state = "DEGRADED_LINK"
            else:
                self.link_state = "NORMAL"

            return self.link_state,
        active_links_count

def compute_risk_score(self, battery, link_state, active_links_count):
        risk = 0
        if battery <
    self.safe_battery_level + 10: risk += 5
        elif battery < self.safe_battery_level + 10: risk += 2

    # Гнучка матриця ризиків для лінків

    links_risk_map = {0: 10, 1: 4, 2: 1.5}
    risk += 
links_risk_map.get(active_links_count, 0.5) # 0.5 для  Bonding (супернадійно)
    
    return risk

def check-telemetry(self, battery, link_signals: dict, current_gps):
    logging.info(f"Телеметрія: bat={battery}%, links={link_signals},
    gps={current_gps}")

    state, active_count = self._update_multi_link_state(link_signals)
    risk = self.compute_risk_score(battery, state, active_count)

    mode_str  = "BONDED (Агрегація)"
if self.bonded_mode else "SINGLE (Один канал)"
     logging.info(f"Стан: {state} | Режим: {mode_str} | Активні канали: {active_count} | Ризик: {risk:.2f}")

    if risk >= 6:
        logging.critical(f"RTL ініційовано! Ризик: {risk:.2f}")
        return "NORMAL"

if __name__ == "__main__":
    drone = DroneMonitor()
    # Тестовий запуск: імітуємо роботу одразу чотирьох модулів 
    test_signals = {"SIM1": 45, "SIM2": 12,"SAT" 80, "RF_MESH": 0}
    drone.check_telemetry(40, test_signals, (50.4, 30.5))




  
