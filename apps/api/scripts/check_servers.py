"""
Скрипт для проверки статуса всех серверов.
"""
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import asyncio
from loguru import logger


def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Проверяет, открыт ли порт."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


async def check_http_endpoint(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Проверяет доступность HTTP endpoint."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return True, f"HTTP {response.status_code}"
    except httpx.TimeoutException:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)[:50]


def get_process_info(port: int) -> str:
    """Получает информацию о процессе, занимающем порт."""
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                # Берем первую строку с процессом (пропускаем заголовок)
                parts = lines[1].split()
                if len(parts) >= 2:
                    return f"{parts[0]} (PID: {parts[1]})"
        return "Не найден"
    except Exception:
        return "Ошибка проверки"


async def main():
    """Проверяет статус всех серверов."""
    print("🔍 Проверка серверов...\n")
    
    servers = [
        ("FastAPI Backend", "localhost", 8000, "http://localhost:8000/health"),
        ("Next.js Frontend", "localhost", 3000, "http://localhost:3000"),
        ("Ollama", "localhost", 11434, "http://localhost:11434/api/tags"),
    ]
    
    results = []
    
    for name, host, port, url in servers:
        print(f"📡 {name} (порт {port}):")
        
        # Проверка порта
        port_open = check_port(host, port)
        process = get_process_info(port) if port_open else "Не запущен"
        
        print(f"   Порт: {'✅ Открыт' if port_open else '❌ Закрыт'}")
        print(f"   Процесс: {process}")
        
        # Проверка HTTP
        if port_open:
            http_ok, http_msg = await check_http_endpoint(url)
            print(f"   HTTP: {'✅ ' + http_msg if http_ok else '❌ ' + http_msg}")
        else:
            http_ok = False
            http_msg = "Порт закрыт"
            print(f"   HTTP: ❌ Недоступен")
        
        results.append({
            "name": name,
            "port": port,
            "port_open": port_open,
            "http_ok": http_ok,
            "process": process,
            "http_msg": http_msg
        })
        print()
    
    # Итоговая сводка
    print("=" * 50)
    print("📊 Итоговая сводка:")
    print("=" * 50)
    
    all_ok = True
    for result in results:
        status = "✅" if result["port_open"] and result["http_ok"] else "❌"
        print(f"{status} {result['name']}: порт {result['port']} - {result['process']}")
        if not (result["port_open"] and result["http_ok"]):
            all_ok = False
    
    if all_ok:
        print("\n✅ Все серверы работают!")
    else:
        print("\n⚠️ Некоторые серверы не работают. Проверьте логи выше.")
    
    return 0 if all_ok else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
