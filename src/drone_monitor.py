import logging
import math
from collections import deque
import time
from enum import Enum

# --- НАЛАШТУВАННЯ ЛОГЕРА ("Чорна скринька") ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s', 
    datefmt='%H:%M:%S'
)

# --- СТАНИ СИСТЕМИ ---
class LinkState(Enum):
    NORMAL = 0
    DEGRADED = 1
    FAILSAFE = 2

class DroneMonitor:
    def __init__(self, drone_name="Стелс-Multi", safe_battery_level=25, window_size=10):
        self.drone_name = drone_name
        self.safe_battery_level = safe_battery_level
        
        # Просторовий модуль (Навігація)
        self.last_gps = None
        self.last_true_az = None  
        self.last_mag_az = None   
        self.magnetic_declination = 7.5  
        self.gps_epsilon = 0.00001  # Допуск для реального "шумного" GPS (зависання)
        
        # Multi-Radio матриця
        self.links = { 
            "SIM1":  {"type": "LTE", "weight": 1.0, "active": True},
            "SIM2":  {"type": "LTE", "weight": 0.8, "active": True},
            "RF_MESH": {"type": "RF", "weight": 0.9, "active": False},
            "SAT":     {"type": "SATCOM", "weight": 0.5, "active": False}
        }
        
        self.level_history = {name: deque(maxlen=window_size) for name in self.links}
        self.bonded_mode = False
        self.link_state = LinkState.NORMAL  # Використання Enum замість строк

    def _is_same_position(self, gps1, gps2):
        """
        Перевіряє, чи дрон залишається на місці, враховуючи шум GPS.
        """
        lat_diff = abs(gps1[0] - gps2[0])
        lon_diff = abs(gps1[1] - gps2[1])
        return lat_diff < self.gps_epsilon and lon_diff < self.gps_epsilon

    def _calculate_azimuth(self, current_gps):
        """
        Аналізує координати та видає Істинний та Магнітний азимути.
        Включає захист від втрати курсу при зависанні (Hover) з урахуванням дрейфу.
        """
        if self.last_gps is None:
            self.last_gps = current_gps
            logging.info("GPS ініціалізовано. Очікування другої точки для розрахунку курсу.")
            return None, None 

        # Перевірка на зависання (Hover) через допуск (epsilon)
        if self._is_same_position(self.last_gps, current_gps):
            if self.last_true_az is not None:
                return self.last_true_az, self.last_mag_az
            else:
                return None, None

        # Конвертуємо градуси в радіани
        lat1, lon1 = map(math.radians, self.last_gps)
        lat2, lon2 = map(math.radians, current_gps)
        d_lon = lon2 - lon1

        # Сферична тригонометрія
        x = math.sin(d_lon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(d_lon))

        initial_bearing = math.atan2(x, y)
        true_azimuth = (math.degrees(initial_bearing) + 360) % 360
        magnetic_azimuth = (true_azimuth - self.magnetic_declination + 360) % 360

        # Округлюємо та запам'ятовуємо значення
        self.last_true_az = round(true_azimuth, 2)
        self.last_mag_az = round(magnetic_azimuth, 2)
        self.last_gps = current_gps

        return self.last_true_az, self.last_mag_az

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

            overall_quality += strength * self.links[name].get("weight", 1.0)

            if strength > 30:
                active_links_count += 1

        self.bonded_mode = (active_links_count >= 2)

        # Типобезпечна зміна станів через Enum
        if critical_count >= 2 or (degraded_count >= len(link_signals) and overall_quality < 100):
            self.link_state = LinkState.FAILSAFE
        elif degraded_count >= 2: 
            self.link_state = LinkState.DEGRADED
        else:
            self.link_state = LinkState.NORMAL

        return self.link_state, active_links_count

    def compute_risk_score(self, battery, link_state, active_links_count):
        risk = 0
        if battery < self.safe_battery_level: 
            risk += 5
        elif battery < self.safe_battery_level + 10: 
            risk += 2

        links_risk_map = {0: 10, 1: 4, 2: 1.5}
        risk += links_risk_map.get(active_links_count, 0.5) 
        
        return risk

    def check_telemetry(self, battery, link_signals: dict, current_gps):
        true_az, mag_az = self._calculate_azimuth(current_gps)
        azimuth_str = f"Курс: {true_az}°(Іст)/{mag_az}°(Маг)" if true_az is not None else "Курс: [Ініціалізація]"

        state, active_count = self._update_multi_link_state(link_signals)
        risk = self.compute_risk_score(battery, state, active_count)

        mode_str = "BONDED" if self.bonded_mode else "SINGLE"
        
        logging.info(f"Телеметрія: bat={battery}%, links={link_signals}, gps={current_gps} | {azimuth_str}")

        # Використання Enum для перевірки логіки
        if risk >= 6 or state == LinkState.FAILSAFE:
            logging.critical(f"Стан: {state.name} | Режим: {mode_str} | Активні канали: {active_count} | Ризик: {risk:.2f} -> RTL ініційовано!")
            return "RTL"
        elif state == LinkState.DEGRADED or risk >= 3:
            logging.warning(f"Стан: {state.name} | Режим: {mode_str} | Активні канали: {active_count} | Ризик: {risk:.2f} -> Деградація.")
            return "DEGRADED"
        else:
            logging.info(f"Стан: {state.name} | Режим: {mode_str} | Активні канали: {active_count} | Ризик: {risk:.2f} -> Норма.")
            return "NORMAL"

if __name__ == "__main__":
    drone = DroneMonitor()
    
    print("--- Запуск Симуляції ---")
    
    test_scenario = [
        (40, {"SIM1": 45, "SIM2": 12, "SAT": 80, "RF_MESH": 0}, (48.28000, 37.18000)), 
        (39, {"SIM1": 40, "SIM2": 10, "SAT": 80, "RF_MESH": 0}, (48.28100, 37.18500)), 
        # Симуляція шумного GPS при зависанні (відхилення менше за epsilon)
        (38, {"SIM1": 40, "SIM2": 10, "SAT": 80, "RF_MESH": 0}, (48.281005, 37.185002)), 
        (20, {"SIM1": 15, "SIM2": 5,  "SAT": 40, "RF_MESH": 0}, (48.28200, 37.19000))  
    ]
    
    for bat, signals, gps in test_scenario:
        drone.check_telemetry(bat, signals, gps)
        time.sleep(1)

