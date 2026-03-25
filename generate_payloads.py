import csv
import math
import random
from datetime import datetime, timedelta

def generate_telemetry_csv(filename, days=7):
    # Gera dados de temperatura e humidade com ciclo diário (senoidal)
    start_time = datetime(2025, 1, 1, 0, 0, 0)
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "temperature", "humidity"])
        
        # Um registo a cada 5 segundos
        current_time = start_time
        end_time = start_time + timedelta(days=days)
        
        while current_time < end_time:
            hour = current_time.hour + current_time.minute / 60.0
            
            # Temperatura varia de 15 a 25 graus, pico às 14h
            temp_base = 20 + 5 * math.sin((hour - 8) * math.pi / 12)
            temp = round(temp_base + random.uniform(-0.5, 0.5), 2)
            
            # Humidade varia inversamente à temperatura (40% a 80%)
            hum_base = 80 - 40 * ((temp - 15) / 10)
            hum = round(max(0, min(100, hum_base + random.uniform(-2, 2))), 1)
            
            writer.writerow([current_time.isoformat(), temp, hum])
            current_time += timedelta(seconds=5)
            
    print(f"[+] Gerado dataset de telemetria: {filename}")

def generate_events_csv(filename, days=7):
    # Gera eventos aleatórios (ex: deteção de movimento)
    start_time = datetime(2025, 1, 1, 0, 0, 0)
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "event_type", "burst_size"])
        
        current_time = start_time
        end_time = start_time + timedelta(days=days)
        
        while current_time < end_time:
            # Mais eventos de dia, menos de noite
            hour = current_time.hour
            if 8 <= hour <= 20:
                # Intervalo entre 30s e 5 mins
                delta = timedelta(seconds=random.randint(30, 300))
            else:
                # Intervalo entre 1h e 4h de noite
                delta = timedelta(seconds=random.randint(3600, 14400))
                
            current_time += delta
            if current_time >= end_time:
                break
                
            writer.writerow([current_time.isoformat(), "motion_detected", random.randint(2, 5)])
            
    print(f"[+] Gerado dataset de eventos: {filename}")

if __name__ == "__main__":
    generate_telemetry_csv("./data/telemetry_dataset.csv", days=3)
    generate_events_csv("./data/events_dataset.csv", days=3)
