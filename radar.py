
from machine import Pin, SPI
import gc9a01
import socket
import vga2_8x8 as font
import network
import time
from math import radians, cos, sin, asin, sqrt, pi, atan2
import _thread

cur_lat = 50.8695727978406 # your latitude
cur_lon = 7.146051119738116 # your longitude
display_width = 240 # px
display_height = 240 # px
sector_width = display_width / 2
radar_coverage = 60 # KM


wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect('Radarstation', 'datortRadar123')


while not wlan.isconnected() and wlan.status() >= 0:
    print("Waiting to connect:")
    time.sleep(1)

    print(wlan.ifconfig())
    
    
### Active flights
flights = {}


### Display initialisation
spi = SPI(1, baudrate = 60000000, sck = Pin(14), mosi = Pin(15))
tft = gc9a01.GC9A01(
    spi,
    display_width,
    display_height,
    reset = Pin(11, Pin.OUT),
    cs = Pin(13, Pin.OUT),
    dc = Pin(12, Pin.OUT),
    backlight = Pin(10, Pin.OUT),
    rotation = 0)

tft.init()
tft.fill(0)



### Distance & Bearing Calculation Helper
def haversine(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371
    return c * r
    

def bearing(lat1, lon1, lat2, lon2):
    y = sin(lon2-lon1) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2-lon1)
    θ = atan2(y, x)
    return (θ*180/pi + 360) % 360



### Flight data handling
def merge_flight(hex_ident, data):
    if hex_ident not in flights:
        flights[hex_ident] = data
    else:
        flights[hex_ident].update(data)
        
    flights[hex_ident].update({'last_seen': int(time.time())})



def draw_aircraft(tft, target_lat, target_lon, color, label, fl):
    distance = haversine(cur_lat, cur_lon, target_lat, target_lon)
    angle = bearing(cur_lat, cur_lon, target_lat, target_lon)
    
    beta = 90 - (angle % 90)
    c = distance
    a = c * cos(radians(beta))
    b = sqrt(c**2 - a**2)
    
    if angle >= 270:
        x = sector_width - (b * sector_width / radar_coverage)
        y = sector_width - (a * sector_width / radar_coverage)
    elif angle >= 180:
        x = sector_width - (a * sector_width / radar_coverage)
        y = sector_width - (b * sector_width / radar_coverage)
    elif angle >= 90:
        x = sector_width + (b * sector_width / radar_coverage)
        y = sector_width + (a * sector_width / radar_coverage)
    else:
        x = sector_width + (a * sector_width / radar_coverage)
        y = sector_width - (b * sector_width / radar_coverage)
    
    tft.fill_rect(int(x), int(y), 4, 4, color)
    tft.text(font, label, int(x) + 10, int(y) - 2, gc9a01.WHITE, gc9a01.BLACK)
    

def remove_timed_out():
    for flight in flights:
        if flights[flight]['last_seen'] < int(time.time()) - 60:
            del flights[flight]


def render_flights(tft):
    tft.fill(0)
    
    for hex_ident in flights:
        data = flights[hex_ident]
            
        if 'latitude' in data and 'longitude' in data:
            color = gc9a01.BLUE if data['last_seen'] > int(time.time()) - 30 else gc9a01.YELLOW
            latitude = data['latitude']
            longitude = data['longitude']
            label = data['flight'] if 'flight' in data else hex_ident
            fl = str(data['altitude'])[0:2] if 'altitude' in data else 'XX' 
            draw_aircraft(tft, latitude, longitude, color, label, fl)
            
    tft.fill_rect(117, 117, 6, 6, gc9a01.RED)        



def redraw_flights():
    while True:
        remove_timed_out()
        render_flights(tft)
        time.sleep(1)


### Basestation format parsing
def process_basestation_message(message):
    chunks = message.split(',')
    
    try:
        if chunks[1] == '1':
            hex_ident = chunks[4]
            flight = chunks[10]
            
            if len(flight) > 0:
                merge_flight(hex_ident, {'flight': flight.strip()});
            
        if chunks[1] == '3':
            hex_ident = chunks[4]
            altitude = chunks[11]
            latitude = chunks[14]
            longitude = chunks[15]
            
            if hex_ident and altitude and latitude and longitude:
                merge_flight(hex_ident, {
                    'altitude': int(altitude),
                    'latitude': float(latitude),
                    'longitude': float(longitude)
                })
                
    except (IndexError, ValueError):
        print()
        
        

### Main loop for network traffic
def main():
    s = socket.socket()
    s.connect(socket.getaddrinfo('radar', 30003)[0][-1])

    while True:
        data = s.recv(500)
        process_basestation_message(str(data, 'utf8'))


### Thread for flight data processing
_thread.start_new_thread(redraw_flights, ())

main()
