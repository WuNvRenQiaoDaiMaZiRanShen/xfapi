import threading
from pysocat import socat

# 定义要转发的端口和目标地址
tcp_ports = [1985, 3000, 8000, 6006]
udp_ports = [8020]
target_host = '202.38.78.122'

# 创建TCP转发函数
def forward_tcp(local_port, remote_port):
    socat(f"TCP-LISTEN:{local_port},reuseaddr", f"TCP:{target_host}:{remote_port}")

# 创建UDP转发函数
def forward_udp(local_port, remote_port):
    socat(f"UDP-LISTEN:{local_port},reuseaddr", f"UDP:{target_host}:{remote_port}")

# 创建并启动TCP转发线程
for port in tcp_ports:
    t = threading.Thread(target=forward_tcp, args=(port, port))
    t.start()

# 创建并启动UDP转发线程
for port in udp_ports:
    t = threading.Thread(target=forward_udp, args=(port, port))
    t.start()