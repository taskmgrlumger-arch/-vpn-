import os
import sys
import csv
import base64
import re
import ssl
import socket
import time
import threading
import json
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# Disable SSL context verification for compatibility with raw IP HTTP/HTTPS endpoints
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

class VPNNode:
    def __init__(self, country, country_code, ip, score, ping, speed, openvpn_b64, source="VPNGate", port=1194, proto="udp"):
        self.country = country or "Unknown"
        self.country_code = country_code or "UN"
        self.ip = ip
        self.score = int(score) if str(score).isdigit() else 0
        self.ping = int(ping) if str(ping).isdigit() else 999
        self.speed = float(speed) if str(speed).replace('.', '', 1).isdigit() else 0.0
        self.openvpn_b64 = openvpn_b64
        self.source = source
        self.port = port
        self.proto = proto
        self.real_latency = -1  # Real tested latency via socket

class VPNDataFetcher:
    """
    Fetches free unlimited VPN servers from VPNGate and IPSpeed endpoints
    without using any external third-party python modules.
    """
    
    VPNGATE_API_URL = "http://www.vpngate.net/api/iphone/"
    IPSPEED_INFO_URL = "https://ipspeed.info/freevpn.php"

    @staticmethod
    def _safe_urlopen(url, timeout=12):
        """Helper to handle HTTP vs HTTPS context safely without protocol errors"""
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        if url.startswith('https://'):
            return urllib.request.urlopen(req, timeout=timeout, context=ssl_context)
        else:
            return urllib.request.urlopen(req, timeout=timeout)

    @staticmethod
    def safe_b64decode(b64_str):
        """Safely decode base64 string with automatic padding fix"""
        if not b64_str:
            return ""
        b64_str = b64_str.strip()
        missing_padding = len(b64_str) % 4
        if missing_padding:
            b64_str += '=' * (4 - missing_padding)
        try:
            return base64.b64decode(b64_str).decode('utf-8', errors='ignore')
        except Exception:
            return ""

    @staticmethod
    def fetch_vpngate_nodes():
        nodes = []
        try:
            with VPNDataFetcher._safe_urlopen(VPNDataFetcher.VPNGATE_API_URL, timeout=12) as response:
                content = response.read().decode('utf-8', errors='ignore')
                
            lines = content.splitlines()
            # Skip VPNGate header comments
            csv_lines = [line for line in lines if not line.startswith('*') and not line.startswith('#')]
            reader = csv.reader(csv_lines)
            
            for row in reader:
                # Row format: HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,NumVpnSessions,Uptime,TotalUsers,TotalTraffic,LogType,Operator,Message,OpenVPN_ConfigData_Base64
                if len(row) >= 15 and row[1].strip():
                    ip = row[1].strip()
                    score = row[2].strip()
                    ping = row[3].strip()
                    speed_bps = row[4].strip()
                    country = row[5].strip()
                    country_code = row[6].strip()
                    ovpn_b64 = row[14].strip()
                    
                    # Convert speed from bps to Mbps
                    speed_mbps = round(float(speed_bps) / (1024 * 1024), 2) if speed_bps.isdigit() else 0.0
                    
                    node = VPNNode(
                        country=country,
                        country_code=country_code,
                        ip=ip,
                        score=score,
                        ping=ping,
                        speed=speed_mbps,
                        openvpn_b64=ovpn_b64,
                        source="VPNGate.net"
                    )
                    nodes.append(node)
        except Exception as e:
            print(f"[Warning] Failed to fetch VPNGate nodes: {e}")
            
        return nodes

    @staticmethod
    def fetch_ipspeed_nodes():
        """
        Parses IP nodes and proxy endpoints from ipspeed.info
        """
        nodes = []
        try:
            with VPNDataFetcher._safe_urlopen(VPNDataFetcher.IPSPEED_INFO_URL, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
            # Regex parse IP address patterns and port
            ip_matches = re.findall(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', html)
            unique_ips = list(set(ip_matches))[:30]  # Take top 30 unique IPs
            
            for ip in unique_ips:
                # Construct standard node
                node = VPNNode(
                    country="IPSpeed Node",
                    country_code="Global",
                    ip=ip,
                    score=888,
                    ping=80,
                    speed=10.0,
                    openvpn_b64="",
                    source="IPSpeed.info"
                )
                nodes.append(node)
        except Exception as e:
            print(f"[Warning] Failed to fetch IPSpeed nodes: {e}")
            
        return nodes

class VPNApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VPNGate & IPSpeed 纯净免费 VPN 汇聚引擎 v2.0 (无依赖版)")
        self.root.geometry("1080x680")  # Fixed format without spaces around 'x'
        self.root.minsize(880, 580)
        
        # Application Theme Colors
        self.bg_color = "#111827"       # Dark Gray/Slate
        self.card_color = "#1f2937"     # Card Panel
        self.accent_color = "#06b6d4"   # Cyan Theme
        self.text_color = "#f9fafb"     # White
        self.subtext_color = "#9ca3af"  # Muted Text
        
        self.root.configure(bg=self.bg_color)
        
        self.all_nodes = []
        self.filtered_nodes = []
        self.is_fetching = False
        self.is_testing = False

        # Apply ttk styles
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()

        # Build UI Components
        self.build_header()
        self.build_filter_bar()
        self.build_node_table()
        self.build_log_and_actions()
        
        # Load data on launch
        self.root.after(300, self.refresh_all_nodes)

    def configure_styles(self):
        # Configure Tableview (Treeview) colors
        self.style.configure("Treeview",
                             background=self.card_color,
                             foreground=self.text_color,
                             fieldbackground=self.card_color,
                             rowheight=28,
                             font=("Segoe UI", 10))
        
        self.style.configure("Treeview.Heading",
                             background="#374151",
                             foreground="#38bdf8",
                             font=("Segoe UI", 10, "bold"))
        
        self.style.map("Treeview",
                       background=[('selected', '#0284c7')],
                       foreground=[('selected', '#ffffff')])

    def build_header(self):
        header_frame = tk.Frame(self.root, bg=self.card_color, height=60, padx=15, pady=10)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        title_label = tk.Label(
            header_frame, 
            text="🌐 全网免费 VPN & 优选 IP 汇聚中心", 
            font=("Segoe UI", 14, "bold"), 
            bg=self.card_color, 
            fg=self.accent_color
        )
        title_label.pack(side=tk.LEFT)

        sub_label = tk.Label(
            header_frame, 
            text="| 数据源: VPNGate.net & IPSpeed.info (不限流量 · 不限速度 · 纯粹开源)", 
            font=("Segoe UI", 9), 
            bg=self.card_color, 
            fg=self.subtext_color
        )
        sub_label.pack(side=tk.LEFT, padx=10)

        self.btn_refresh = tk.Button(
            header_frame, 
            text="🔄 刷新节点列表", 
            command=self.refresh_all_nodes,
            bg="#0284c7", fg="white", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=12, pady=4, cursor="hand2"
        )
        self.btn_refresh.pack(side=tk.RIGHT)

    def build_filter_bar(self):
        filter_frame = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=8)
        filter_frame.pack(fill=tk.X, side=tk.TOP)

        # Search Keyword Filter
        tk.Label(filter_frame, text="🔍 搜索国家/IP:", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.entry_search = tk.Entry(filter_frame, bg=self.card_color, fg=self.text_color, insertbackground="white", width=18, font=("Segoe UI", 9), relief=tk.SOLID)
        self.entry_search.pack(side=tk.LEFT, padx=(0, 15))
        self.entry_search.bind("<KeyRelease>", lambda e: self.apply_filters())

        # Source Filter
        tk.Label(filter_frame, text="数据源:", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.combo_source = ttk.Combobox(filter_frame, values=["全部数据源", "VPNGate.net", "IPSpeed.info"], state="readonly", width=14)
        self.combo_source.current(0)
        self.combo_source.pack(side=tk.LEFT, padx=(0, 15))
        self.combo_source.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        # Speed Threshold Filter
        tk.Label(filter_frame, text="最低速度(Mbps):", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.entry_min_speed = tk.Entry(filter_frame, bg=self.card_color, fg=self.text_color, insertbackground="white", width=8, font=("Segoe UI", 9), relief=tk.SOLID)
        self.entry_min_speed.insert(0, "0")
        self.entry_min_speed.pack(side=tk.LEFT, padx=(0, 15))
        self.entry_min_speed.bind("<KeyRelease>", lambda e: self.apply_filters())

        # Test Latency Button
        self.btn_ping_test = tk.Button(
            filter_frame, 
            text="⚡ 真测实测 Ping 延迟", 
            command=self.start_latency_test,
            bg="#10b981", fg="white", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=10, pady=3, cursor="hand2"
        )
        self.btn_ping_test.pack(side=tk.RIGHT)

    def build_node_table(self):
        table_frame = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=5)
        table_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        columns = ("country", "ip", "source", "speed", "ping", "real_latency", "score")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        # Define column headings & layout
        self.tree.heading("country", text="国家 / 地区", command=lambda: self.sort_by_column("country", False))
        self.tree.heading("ip", text="IP 地址", command=lambda: self.sort_by_column("ip", False))
        self.tree.heading("source", text="节点来源", command=lambda: self.sort_by_column("source", False))
        self.tree.heading("speed", text="带宽速度 (Mbps)", command=lambda: self.sort_by_column("speed", True))
        self.tree.heading("ping", text="节点标称 Ping", command=lambda: self.sort_by_column("ping", False))
        self.tree.heading("real_latency", text="本地实测延迟", command=lambda: self.sort_by_column("real_latency", False))
        self.tree.heading("score", text="综合评分", command=lambda: self.sort_by_column("score", True))

        self.tree.column("country", width=180, anchor=tk.W)
        self.tree.column("ip", width=140, anchor=tk.CENTER)
        self.tree.column("source", width=120, anchor=tk.CENTER)
        self.tree.column("speed", width=120, anchor=tk.E)
        self.tree.column("ping", width=110, anchor=tk.E)
        self.tree.column("real_latency", width=110, anchor=tk.E)
        self.tree.column("score", width=100, anchor=tk.E)

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def build_log_and_actions(self):
        bottom_frame = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=10)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Action Buttons Frame
        btn_box = tk.Frame(bottom_frame, bg=self.bg_color)
        btn_box.pack(fill=tk.X, side=tk.TOP, pady=(0, 8))

        btn_export = tk.Button(
            btn_box, 
            text="💾 导出选中的 OpenVPN (.ovpn)", 
            command=self.export_selected_ovpn,
            bg="#8b5cf6", fg="white", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        btn_export.pack(side=tk.LEFT, padx=(0, 10))

        btn_copy_ip = tk.Button(
            btn_box, 
            text="📋 复制选中 IP", 
            command=self.copy_selected_ip,
            bg="#3b82f6", fg="white", font=("Segoe UI", 9),
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        btn_copy_ip.pack(side=tk.LEFT, padx=(0, 10))

        btn_connect = tk.Button(
            btn_box, 
            text="🚀 启动 OpenVPN 客户端连接", 
            command=self.launch_openvpn_client,
            bg="#f59e0b", fg="black", font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        btn_connect.pack(side=tk.RIGHT)

        # Log Console Window
        self.log_text = scrolledtext.ScrolledText(
            bottom_frame, 
            height=4, 
            bg=self.card_color, 
            fg="#a7f3d0", 
            font=("Consolas", 9),
            relief=tk.SOLID
        )
        self.log_text.pack(fill=tk.X, side=tk.BOTTOM)
        self.log_msg("软件已成功启动。点击 '刷新节点列表' 即可拉取最新免费 VPN 节点。")

    def log_msg(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)

    def refresh_all_nodes(self):
        if self.is_fetching:
            return
        
        self.is_fetching = True
        self.btn_refresh.config(state=tk.DISABLED, text="⏳ 正在加载...")
        self.log_msg("正在从 www.vpngate.net 与 ipspeed.info 抓取最新免费节点...")

        def thread_target():
            vg_nodes = VPNDataFetcher.fetch_vpngate_nodes()
            ip_nodes = VPNDataFetcher.fetch_ipspeed_nodes()
            combined = vg_nodes + ip_nodes

            def update_ui():
                self.all_nodes = combined
                self.apply_filters()
                self.is_fetching = False
                self.btn_refresh.config(state=tk.NORMAL, text="🔄 刷新节点列表")
                self.log_msg(f"数据抓取完成！共获取 {len(combined)} 个免费可连接 VPN 节点。")

            self.root.after(0, update_ui)

        threading.Thread(target=thread_target, daemon=True).start()

    def apply_filters(self):
        search_kw = self.entry_search.get().strip().lower()
        source_filter = self.combo_source.get()
        min_speed_val = 0.0
        
        try:
            min_speed_val = float(self.entry_min_speed.get().strip())
        except ValueError:
            min_speed_val = 0.0

        filtered = []
        for node in self.all_nodes:
            # Source Check
            if source_filter != "全部数据源" and node.source != source_filter:
                continue
            
            # Speed Check
            if node.speed < min_speed_val:
                continue
            
            # Search Keyword
            if search_kw:
                match_country = search_kw in node.country.lower()
                match_ip = search_kw in node.ip.lower()
                if not (match_country or match_ip):
                    continue

            filtered.append(node)

        self.filtered_nodes = filtered
        self.render_table()

    def render_table(self):
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, node in enumerate(self.filtered_nodes):
            real_lat_str = f"{node.real_latency} ms" if node.real_latency > 0 else "未测试"
            ping_str = f"{node.ping} ms" if node.ping < 999 else "--"
            speed_str = f"{node.speed} Mbps"

            item_id = self.tree.insert(
                "", 
                tk.END, 
                values=(
                    f"🏳️ {node.country}",
                    node.ip,
                    node.source,
                    speed_str,
                    ping_str,
                    real_lat_str,
                    node.score
                ),
                tags=(str(idx),)
            )

    def sort_by_column(self, col, reverse):
        if col == "speed":
            self.filtered_nodes.sort(key=lambda x: x.speed, reverse=reverse)
        elif col == "ping":
            self.filtered_nodes.sort(key=lambda x: x.ping, reverse=reverse)
        elif col == "real_latency":
            self.filtered_nodes.sort(key=lambda x: (x.real_latency if x.real_latency > 0 else 99999), reverse=reverse)
        elif col == "score":
            self.filtered_nodes.sort(key=lambda x: x.score, reverse=reverse)
        elif col == "ip":
            self.filtered_nodes.sort(key=lambda x: x.ip, reverse=reverse)
        elif col == "country":
            self.filtered_nodes.sort(key=lambda x: x.country, reverse=reverse)
            
        self.render_table()

    def start_latency_test(self):
        if self.is_testing or not self.filtered_nodes:
            return

        self.is_testing = True
        self.btn_ping_test.config(state=tk.DISABLED, text="⏳ 正在测速...")
        self.log_msg("开始并发测试节点 Socket 实际延迟...")

        def test_worker(nodes_subset):
            for node in nodes_subset:
                try:
                    start_time = time.time()
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect((node.ip, 443))  # Default HTTPS/VPN port test
                    s.close()
                    elapsed = int((time.time() - start_time) * 1000)
                    node.real_latency = elapsed
                except Exception:
                    node.real_latency = 999  # Timeout or unreachable

        def manager_thread():
            threads = []
            # Batch size for socket testing
            chunk_size = max(1, len(self.filtered_nodes) // 10)
            for i in range(0, len(self.filtered_nodes), chunk_size):
                subset = self.filtered_nodes[i:i + chunk_size]
                t = threading.Thread(target=test_worker, args=(subset,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            def finish_ui():
                self.filtered_nodes.sort(key=lambda x: (x.real_latency if x.real_latency > 0 else 99999))
                self.render_table()
                self.is_testing = False
                self.btn_ping_test.config(state=tk.NORMAL, text="⚡ 真测实测 Ping 延迟")
                self.log_msg("延迟真测完成！已自动按最低延迟重新排序节点。")

            self.root.after(0, finish_ui)

        threading.Thread(target=manager_thread, daemon=True).start()

    def get_selected_node(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("未选中节点", "请先在表格中点击选择一个 VPN 节点！")
            return None
        
        item_vals = self.tree.item(selected_item[0])["values"]
        selected_ip = item_vals[1]
        
        for node in self.filtered_nodes:
            if node.ip == selected_ip:
                return node
        return None

    def copy_selected_ip(self):
        node = self.get_selected_node()
        if node:
            self.root.clipboard_clear()
            self.root.clipboard_append(node.ip)
            self.log_msg(f"已成功复制 IP 地址: {node.ip}")
            messagebox.showinfo("复制成功", f"IP 地址 {node.ip} 已复制到剪贴板！")

    def export_selected_ovpn(self):
        node = self.get_selected_node()
        if not node:
            return

        ovpn_content = ""
        if node.openvpn_b64:
            ovpn_content = VPNDataFetcher.safe_b64decode(node.openvpn_b64)

        # Fallback generated standard OpenVPN configuration template if Base64 unavailable
        if not ovpn_content:
            ovpn_content = f"""client
dev tun
proto udp
remote {node.ip} 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-128-CBC
auth SHA1
comp-lzo
verb 3
"""

        file_path = filedialog.asksaveasfilename(
            defaultextension=".ovpn",
            filetypes=[("OpenVPN Config", "*.ovpn"), ("All Files", "*.*")],
            initialfile=f"VPNGate_{node.country_code}_{node.ip}.ovpn"
        )

        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(ovpn_content)
            self.log_msg(f"已导出 .ovpn 配置文件至: {file_path}")
            messagebox.showinfo("导出成功", f"配置文件已保存！\n路径: {file_path}")

    def launch_openvpn_client(self):
        node = self.get_selected_node()
        if not node:
            return

        # Export temporary ovpn file
        temp_ovpn = os.path.join(os.getcwd(), "temp_vpn.ovpn")
        if node.openvpn_b64:
            ovpn_content = VPNDataFetcher.safe_b64decode(node.openvpn_b64)
        else:
            ovpn_content = f"client\ndev tun\nproto udp\nremote {node.ip} 1194\nnobind\n"

        with open(temp_ovpn, "w", encoding="utf-8") as f:
            f.write(ovpn_content)

        self.log_msg(f"尝试通过系统 OpenVPN 可执行文件启动节点 [{node.ip}]...")
        
        # Check standard installation paths
        possible_paths = [
            r"C:\Program Files\OpenVPN\bin\openvpn.exe",
            r"C:\Program Files (x86)\OpenVPN\bin\openvpn.exe",
            "/usr/bin/openvpn",
            "/usr/local/bin/openvpn"
        ]
        
        found_bin = None
        for path in possible_paths:
            if os.path.exists(path):
                found_bin = path
                break

        if found_bin:
            try:
                import subprocess
                subprocess.Popen([found_bin, "--config", temp_ovpn])
                self.log_msg(f"已调用 OpenVPN 执行程序: {found_bin}")
            except Exception as e:
                messagebox.showerror("启动失败", f"启动 OpenVPN 进程失败: {e}")
        else:
            messagebox.showinfo(
                "配置文件已就绪", 
                f"已生成临时连接文件: {temp_ovpn}\n\n未找到系统内置 openvpn.exe。建议使用小火箭、v2rayN、Clash 或 OpenVPN GUI 导入该 .ovpn 文件直接连接。"
            )

if __name__ == "__main__":
    root = tk.Tk()
    app = VPNApp(root)
    root.mainloop()