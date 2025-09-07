#!/usr/bin/env python3
"""
对比 Ring、MeshBypass、Mesh_XY、2BitTree 和 ThreeBitTree 五种拓扑的测试脚本。
- Ring: routing-algorithm=3
- MeshBypass: routing-algorithm=4
- Mesh_XY: routing-algorithm=1
- 2BitTree: routing-algorithm=5 (二进制跳转路由)
- ThreeBitTree: routing-algorithm=6 (三进制跳转路由)
默认使用 64 CPUs/dirs，8行网格(Mesh)或64节点(BitTree/Ring)，注入率 0.8，仿真 10000 周期。
"""
import os
import re
import time
import shutil
import subprocess
import math

BASE_CMD = [
    "./build/NULL/gem5.opt",
    "configs/example/garnet_synth_traffic.py",
    "--network=garnet",
    "--num-cpus=16",
    "--num-dirs=16",
    "--inj-vnet=0",
    "--synthetic=uniform_random",
    "--sim-cycles=5000",
    "--injectionrate=0.57",
]

TIMEOUT = 900  # seconds

def run_simulation(name, extra_args):
    print(f"\n{'='*60}")
    print(f"运行 {name} 拓扑")
    print(f"{'='*60}")
    
    cmd = BASE_CMD + extra_args.split()
    print("命令:", " ".join(cmd))
    start = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        print("错误: 超时")
        return None
    duration = time.time() - start
    if res.returncode != 0:
        print("错误: 返回码", res.returncode)
        print("输出:")
        print(res.stdout)  # 输出完整stdout
        print("错误:")
        print(res.stderr)  # 输出完整stderr
        return None
    outdir = f"m5out_{name}"
    if os.path.exists("m5out"):
        if os.path.exists(outdir):
            shutil.rmtree(outdir)
        shutil.move("m5out", outdir)
        print(f"完成 ({duration:.1f}秒) -> {outdir}")
        return outdir
    else:
        print("错误: m5out不存在")
        return None

def extract_stats(output_dir):
    stats_path = os.path.join(output_dir, "stats.txt")
    if not os.path.exists(stats_path):
        print("stats.txt文件未找到:", output_dir)
        return None
    txt = open(stats_path).read()
    patterns = {
        "packets_injected": r"system\.ruby\.network\.packets_injected::total\s+(\d+)",
        "packets_received": r"system\.ruby\.network\.packets_received::total\s+(\d+)",
        "avg_queue_latency": r"system\.ruby\.network\.average_packet_queueing_latency\s+([\d.]+)",
        "avg_network_latency": r"system\.ruby\.network\.average_packet_network_latency\s+([\d.]+)",
        "avg_total_latency": r"system\.ruby\.network\.average_packet_latency\s+([\d.]+)",
        "avg_hops": r"system\.ruby\.network\.average_hops\s+([\d.]+)",
        "reception_rate": r"system\.ruby\.network\.reception_rate\s+([\d.]+)",
    }
    stats = {}
    for k, p in patterns.items():
        m = re.search(p, txt)
        if not m:
            stats[k] = "N/A"
        else:
            val = m.group(1)
            stats[k] = int(val) if val.isdigit() else float(val)
    return stats

def print_table(all_stats):
    print("\n" + "="*100)
    print("拓扑性能对比: Ring vs ThreeBitTree vs 2BitTree vs MeshBypass vs Mesh_XY")
    print("="*100)
    
    keys = ["packets_injected", "packets_received", "avg_queue_latency", 
            "avg_network_latency", "avg_total_latency", "avg_hops", "reception_rate"]
    
    # 确定所有拓扑名称并排序 - Ring放在最前面
    topo_names = []
    if "Ring" in all_stats:
        topo_names.append("Ring")
    for name in sorted(all_stats.keys()):
        if name != "Ring":
            topo_names.append(name)
    
    # 创建表头
    header = f"{'指标':<30}"
    for name in topo_names:
        header += f" {name:<16}"
    print(header)
    print("-" * len(header))
    
    # 打印每行数据
    for k in keys:
        row = f"{k:<30}"
        for name in topo_names:
            val = all_stats.get(name, {}).get(k, "N/A")
            row += f" {fmt_val(val):<16}"
        print(row)
    
    # 计算各拓扑与Mesh_XY的对比
    if "Mesh_XY" in all_stats:
        print("\n" + "-"*100)
        mesh_hops = all_stats["Mesh_XY"].get("avg_hops", 0)
        mesh_lat = all_stats["Mesh_XY"].get("avg_total_latency", 0)
        
        for name in ["Ring", "ThreeBitTree", "2BitTree", "MeshBypass"]:
            if name in all_stats:
                print(f"{name}相对Mesh_XY的改进：")
                
                topo_hops = all_stats[name].get("avg_hops", 0)
                if topo_hops and mesh_hops and topo_hops != "N/A" and mesh_hops != "N/A":
                    hop_improve = (mesh_hops - topo_hops) / mesh_hops * 100
                    print(f"  平均跳数减少: {hop_improve:.2f}%")
                
                topo_lat = all_stats[name].get("avg_total_latency", 0)
                if topo_lat and mesh_lat and topo_lat != "N/A" and mesh_lat != "N/A":
                    lat_improve = (mesh_lat - topo_lat) / mesh_lat * 100
                    print(f"  平均延迟减少: {lat_improve:.2f}%")
                print("")
        
        # Ring与其他高级拓扑的比较
        if "Ring" in all_stats:
            ring_hops = all_stats["Ring"].get("avg_hops", 0)
            ring_lat = all_stats["Ring"].get("avg_total_latency", 0)
            
            print("Ring与其他拓扑的比较：")
            for name in ["ThreeBitTree", "2BitTree", "MeshBypass"]:
                if name in all_stats:
                    topo_hops = all_stats[name].get("avg_hops", 0)
                    topo_lat = all_stats[name].get("avg_total_latency", 0)
                    
                    if ring_hops and topo_hops and ring_hops != "N/A" and topo_hops != "N/A":
                        if ring_hops < topo_hops:
                            hop_improve = (topo_hops - ring_hops) / topo_hops * 100
                            print(f"  Ring比{name}平均跳数少: {hop_improve:.2f}%")
                        else:
                            hop_worse = (ring_hops - topo_hops) / ring_hops * 100
                            print(f"  Ring比{name}平均跳数多: {hop_worse:.2f}%")
                    
                    if ring_lat and topo_lat and ring_lat != "N/A" and topo_lat != "N/A":
                        if ring_lat < topo_lat:
                            lat_improve = (topo_lat - ring_lat) / topo_lat * 100
                            print(f"  Ring比{name}平均延迟少: {lat_improve:.2f}%")
                        else:
                            lat_worse = (ring_lat - topo_lat) / ring_lat * 100
                            print(f"  Ring比{name}平均延迟多: {lat_worse:.2f}%")
            print("")
        
        # 如果有ThreeBitTree和2BitTree，比较它们
        if "ThreeBitTree" in all_stats and "2BitTree" in all_stats:
            tri_hops = all_stats["ThreeBitTree"].get("avg_hops", 0)
            bit_hops = all_stats["2BitTree"].get("avg_hops", 0)
            tri_lat = all_stats["ThreeBitTree"].get("avg_total_latency", 0)
            bit_lat = all_stats["2BitTree"].get("avg_total_latency", 0)
            
            print("ThreeBitTree相对2BitTree的改进：")
            if tri_hops and bit_hops and tri_hops != "N/A" and bit_hops != "N/A":
                hop_improve = (bit_hops - tri_hops) / bit_hops * 100
                print(f"  平均跳数减少: {hop_improve:.2f}%")
            
            if tri_lat and bit_lat and tri_lat != "N/A" and bit_lat != "N/A":
                lat_improve = (bit_lat - tri_lat) / bit_lat * 100
                print(f"  平均延迟减少: {lat_improve:.2f}%")

def fmt_val(x):
    """格式化数值以便表格显示"""
    if isinstance(x, float):
        return f"{x:.3f}"
    return str(x)

def main():
    configs = [
        ("Ring", "--topology=Ring --routing-algorithm=3"),
        ("ThreeBitTree", "--topology=ThreeBitTree --routing-algorithm=6"),
        ("2BitTree", "--topology=TwoBitTree --routing-algorithm=5"),
        ("MeshBypass", "--topology=MeshBypass --routing-algorithm=4 --mesh-rows=4"),
        ("Mesh_XY", "--topology=Mesh_XY --routing-algorithm=1 --mesh-rows=4"),
    ]
    
    results = {}
    for name, args in configs:
        out = run_simulation(name, args)
        if out:
            stats = extract_stats(out)
            if stats:
                results[name] = stats
            else:
                print(f"无法解析{name}的统计数据")
        else:
            print(f"{name}模拟失败")
    
    if results:
        print_table(results)
        
        # 保存结果到文件
        with open("topology_comparison_results.txt", "w") as f:
            f.write("拓扑结构对比: Ring vs ThreeBitTree vs 2BitTree vs MeshBypass vs Mesh_XY\n")
            f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"节点数: 64, 注入率: 0.8, 仿真周期: 10000\n\n")
            
            for n, s in results.items():
                f.write(f"[{n}]\n")
                for k, v in s.items():
                    f.write(f"{k} = {v}\n")
                f.write("\n")
            
            # 写入比较结果
            if "Mesh_XY" in results:
                mesh_hops = results["Mesh_XY"].get("avg_hops", 0)
                mesh_lat = results["Mesh_XY"].get("avg_total_latency", 0)
                
                for name in ["Ring", "ThreeBitTree", "2BitTree", "MeshBypass"]:
                    if name in results:
                        f.write(f"\n[比较: {name} vs Mesh_XY]\n")
                        
                        topo_hops = results[name].get("avg_hops", 0)
                        if topo_hops and mesh_hops and topo_hops != "N/A" and mesh_hops != "N/A":
                            hop_improve = (mesh_hops - topo_hops) / mesh_hops * 100
                            f.write(f"平均跳数减少: {hop_improve:.2f}%\n")
                        
                        topo_lat = results[name].get("avg_total_latency", 0)
                        if topo_lat and mesh_lat and topo_lat != "N/A" and mesh_lat != "N/A":
                            lat_improve = (mesh_lat - topo_lat) / mesh_lat * 100
                            f.write(f"平均延迟减少: {lat_improve:.2f}%\n")
                
                # Ring与其他拓扑的比较
                if "Ring" in results:
                    ring_hops = results["Ring"].get("avg_hops", 0)
                    ring_lat = results["Ring"].get("avg_total_latency", 0)
                    
                    f.write("\n[Ring与其他拓扑的比较]\n")
                    for name in ["ThreeBitTree", "2BitTree", "MeshBypass"]:
                        if name in results:
                            f.write(f"\nRing vs {name}:\n")
                            topo_hops = results[name].get("avg_hops", 0)
                            if ring_hops and topo_hops and ring_hops != "N/A" and topo_hops != "N/A":
                                if ring_hops < topo_hops:
                                    hop_improve = (topo_hops - ring_hops) / topo_hops * 100
                                    f.write(f"Ring平均跳数少: {hop_improve:.2f}%\n")
                                else:
                                    hop_worse = (ring_hops - topo_hops) / ring_hops * 100
                                    f.write(f"Ring平均跳数多: {hop_worse:.2f}%\n")
                            
                            topo_lat = results[name].get("avg_total_latency", 0)
                            if ring_lat and topo_lat and ring_lat != "N/A" and topo_lat != "N/A":
                                if ring_lat < topo_lat:
                                    lat_improve = (topo_lat - ring_lat) / topo_lat * 100
                                    f.write(f"Ring平均延迟少: {lat_improve:.2f}%\n")
                                else:
                                    lat_worse = (ring_lat - topo_lat) / ring_lat * 100
                                    f.write(f"Ring平均延迟多: {lat_worse:.2f}%\n")
                
                # 比较ThreeBitTree和2BitTree
                if "ThreeBitTree" in results and "2BitTree" in results:
                    f.write("\n[比较: ThreeBitTree vs 2BitTree]\n")
                    tri_hops = results["ThreeBitTree"].get("avg_hops", 0)
                    bit_hops = results["2BitTree"].get("avg_hops", 0)
                    if tri_hops and bit_hops and tri_hops != "N/A" and bit_hops != "N/A":
                        hop_improve = (bit_hops - tri_hops) / bit_hops * 100
                        f.write(f"平均跳数减少: {hop_improve:.2f}%\n")
                    
                    tri_lat = results["ThreeBitTree"].get("avg_total_latency", 0)
                    bit_lat = results["2BitTree"].get("avg_total_latency", 0)
                    if tri_lat and bit_lat and tri_lat != "N/A" and bit_lat != "N/A":
                        lat_improve = (bit_lat - tri_lat) / bit_lat * 100
                        f.write(f"平均延迟减少: {lat_improve:.2f}%\n")
        
        print("\n结果已保存到 topology_comparison_results.txt")
    else:
        print("没有成功的结果")

if __name__ == "__main__":
    main()