#!/usr/bin/env bash
# ==========================================================
# AL-CIVIL WAREHOUSE MANAGEMENT SYSTEM
# Android & Termux High-Performance Launcher
# ==========================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

PID_FILE="$DIR/.server.pid"
LOG_FILE="$DIR/server.log"
PORT=5000

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
AMBER='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper to acquire Termux wake lock so Android doesn't kill background server
acquire_wake_lock() {
    if command -v termux-wake-lock &>/dev/null; then
        termux-wake-lock
    fi
}

# Helper to release Termux wake lock
release_wake_lock() {
    if command -v termux-wake-unlock &>/dev/null; then
        termux-wake-unlock
    fi
}

# Helper to open browser on Android
open_browser() {
    local url="http://127.0.0.1:${PORT}"
    sleep 1
    if command -v termux-open-url &>/dev/null; then
        termux-open-url "$url" 2>/dev/null
    elif command -v am &>/dev/null; then
        am start -a android.intent.action.VIEW -d "$url" &>/dev/null
    elif command -v termux-open &>/dev/null; then
        termux-open "$url" 2>/dev/null
    fi
}

# Helper to detect local Wi-Fi IP
get_local_ip() {
    local ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7}')
    if [ -z "$ip" ]; then
        ip=$(ifconfig wlan0 2>/dev/null | grep 'inet ' | awk '{print $2}' | sed 's/addr://')
    fi
    echo "${ip:-127.0.0.1}"
}

# Check if process is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    local pid=$(pgrep -f "python3.*app.py" | head -n 1)
    if [ -n "$pid" ]; then
        echo "$pid" > "$PID_FILE"
        return 0
    fi
    return 1
}

status_cmd() {
    echo -e "${BLUE}========================================================${NC}"
    echo -e "  🏗️  ${AMBER}AL-CIVIL WAREHOUSE SYSTEM (Status Perangkat)${NC}"
    echo -e "${BLUE}========================================================${NC}"
    if is_running; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        local local_ip=$(get_local_ip)
        echo -e "  Status : ${GREEN}AKTIF BERJALAN (Online)${NC}"
        echo -e "  PID    : ${pid}"
        echo -e "  Port   : ${PORT}"
        echo -e "  Akses  : http://localhost:${PORT}"
        if [ "$local_ip" != "127.0.0.1" ]; then
            echo -e "  Wi-Fi  : http://${local_ip}:${PORT}"
        fi
        echo -e "${BLUE}--------------------------------------------------------${NC}"
        echo -e "  Tip: Ketik '${AMBER}./start.sh open${NC}' untuk membuka di browser"
    else
        echo -e "  Status : ${RED}TIDAK AKTIF (Offline)${NC}"
        echo -e "${BLUE}--------------------------------------------------------${NC}"
        echo -e "  Ketik '${GREEN}./start.sh start${NC}' untuk mengaktifkan server."
    fi
    echo -e "${BLUE}========================================================${NC}"
}

stop_cmd() {
    echo -e "${AMBER}Menghentikan AL-CIVIL Warehouse...${NC}"
    if is_running; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        kill "$pid" 2>/dev/null
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
        rm -f "$PID_FILE"
        release_wake_lock
        echo -e "${GREEN}✓ Server berhasil dihentikan.${NC}"
    else
        pkill -f "python3.*app.py" 2>/dev/null
        rm -f "$PID_FILE"
        release_wake_lock
        echo -e "${GREEN}✓ Tidak ada server yang sedang berjalan.${NC}"
    fi
}

start_bg() {
    if is_running; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        echo -e "${AMBER}Server AL-CIVIL sudah berjalan di latar belakang (PID: ${pid}).${NC}"
        open_browser
        status_cmd
        return 0
    fi

    echo -e "${BLUE}========================================================${NC}"
    echo -e "  🏗️  ${AMBER}MEMULAI SERVER LOKAL: AL-CIVIL WAREHOUSE${NC}"
    echo -e "  Sistem Manajemen Logistik & Material Teknik Sipil"
    echo -e "${BLUE}========================================================${NC}"

    acquire_wake_lock
    echo -e "  [1/3] Mengaktifkan Termux Wake-Lock (Anti-Sleep Android)..."

    # Start Flask in background with battery-saving options and detached session
    export DEBUG=0
    setsid python3 app.py </dev/null > "$LOG_FILE" 2>&1 &
    local new_pid=$!
    disown "$new_pid" 2>/dev/null
    echo "$new_pid" > "$PID_FILE"

    echo -e "  [2/3] Server aktif di latar belakang (PID: ${new_pid})..."
    
    # Wait for server to respond
    local count=0
    while ! curl -s -m 1 "http://127.0.0.1:${PORT}/api/system-status" &>/dev/null && [ $count -lt 10 ]; do
        sleep 0.5
        count=$((count + 1))
    done

    local local_ip=$(get_local_ip)
    echo -e "  [3/3] Membuka browser Android..."
    open_browser

    echo -e "${BLUE}--------------------------------------------------------${NC}"
    echo -e "  ${GREEN}✓ SERVER AL-CIVIL SIAP DIGUNAKAN!${NC}"
    echo -e "  🌐 Lokal HP   : ${GREEN}http://127.0.0.1:${PORT}${NC}"
    if [ "$local_ip" != "127.0.0.1" ]; then
        echo -e "  📶 Satu WiFi  : ${GREEN}http://${local_ip}:${PORT}${NC}"
    fi
    echo -e "  📄 Log File   : ${LOG_FILE}"
    echo -e "${BLUE}========================================================${NC}"
    echo -e "  Perintah Tambahan:"
    echo -e "  - Berhenti : ${AMBER}./start.sh stop${NC}"
    echo -e "  - Status   : ${AMBER}./start.sh status${NC}"
    echo -e "  - Buka Web : ${AMBER}./start.sh open${NC}"
    echo -e "  - Lihat Log: ${AMBER}./start.sh log${NC}"
    echo -e "${BLUE}========================================================${NC}"
}

start_fg() {
    acquire_wake_lock
    echo -e "${BLUE}Memulai AL-CIVIL dalam mode foreground (Ctrl+C untuk keluar)...${NC}"
    (sleep 1 && open_browser) &
    python3 app.py
    release_wake_lock
}

log_cmd() {
    if [ -f "$LOG_FILE" ]; then
        tail -n 30 -f "$LOG_FILE"
    else
        echo "Log belum tersedia."
    fi
}

case "$1" in
    start|"")
        start_bg
        ;;
    fg|foreground)
        start_fg
        ;;
    stop)
        stop_cmd
        ;;
    restart)
        stop_cmd
        sleep 1
        start_bg
        ;;
    status)
        status_cmd
        ;;
    open)
        open_browser
        echo "Membuka browser ke http://127.0.0.1:${PORT}..."
        ;;
    log)
        log_cmd
        ;;
    *)
        echo "Penggunaan: $0 {start|stop|restart|status|open|fg|log}"
        ;;
esac
