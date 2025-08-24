#!/usr/bin/env python3

import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# 实验配置
traffic_patterns = [
    "uniform_random",
    "shuffle",
    "transpose",
    "tornado",
    "neighbor",
]
injection_rates = [0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]

# 基础gem5命令
base_cmd = [
    "./build/NULL/gem5.opt",
    "configs/example/garnet_synth_traffic.py",
    "--network=garnet",
    "--num-cpus=64",
    "--num-dirs=64",
    "--topology=Mesh_XY",
    "--mesh-rows=8",
    "--inj-vnet=0",
    "--sim-cycles=10000",
]


def extract_stats(stats_file):
    """从stats.txt文件中提取网络统计信息"""
    stats = {}

    with open(stats_file, "r") as f:
        content = f.read()

    # 提取关键统计信息
    metrics = {
        "packets_injected": "system.ruby.network.packets_injected::total",
        "packets_received": "system.ruby.network.packets_received::total",
        "average_packet_queueing_latency": "system.ruby.network.average_packet_queueing_latency",
        "average_packet_network_latency": "system.ruby.network.average_packet_network_latency",
        "average_packet_latency": "system.ruby.network.average_packet_latency",
        "average_hops": "system.ruby.network.average_hops",
        "reception_rate": "system.ruby.network.reception_rate",
    }

    for key, pattern in metrics.items():
        lines = [line for line in content.split("\n") if pattern in line]
        if lines:
            # 提取数值部分
            value_str = lines[0].split()[-2]  # 倒数第二个元素通常是数值
            try:
                stats[key] = float(value_str)
            except ValueError:
                stats[key] = 0.0
        else:
            stats[key] = 0.0

    return stats


def run_experiment(traffic_pattern, injection_rate):
    """运行单个实验"""
    print(
        f"Running experiment: {traffic_pattern}, injection_rate={injection_rate}"
    )

    # 构建命令
    cmd = base_cmd + [
        f"--synthetic={traffic_pattern}",
        f"--injectionrate={injection_rate}",
    ]

    # 创建输出目录
    output_dir = f"results/{traffic_pattern}_ir{injection_rate}"
    os.makedirs(output_dir, exist_ok=True)

    # 运行gem5
    try:
        result = subprocess.run(
            cmd, cwd=".", capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            print(f"Error running experiment: {result.stderr}")
            return None

        # 移动输出文件
        os.rename("m5out/stats.txt", f"{output_dir}/stats.txt")
        if os.path.exists("m5out/config.ini"):
            os.rename("m5out/config.ini", f"{output_dir}/config.ini")

        # 提取统计信息
        stats = extract_stats(f"{output_dir}/stats.txt")
        stats["traffic_pattern"] = traffic_pattern
        stats["injection_rate"] = injection_rate

        return stats

    except subprocess.TimeoutExpired:
        print(
            f"Experiment timed out: {traffic_pattern}, injection_rate={injection_rate}"
        )
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def plot_results(results_df):
    """绘制结果图表 - Task 1 专门分析"""

    # 创建图表目录
    os.makedirs("plots", exist_ok=True)

    # 设置图表样式
    plt.style.use("seaborn-v0_8")
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    # ===== Task 1 问题1: 延迟-吞吐量曲线 (Latency vs Throughput) =====
    plt.figure(figsize=(12, 8))
    for i, pattern in enumerate(traffic_patterns):
        pattern_data = results_df[results_df["traffic_pattern"] == pattern]
        plt.plot(
            pattern_data["reception_rate"],
            pattern_data["average_packet_latency"],
            "o-",
            label=pattern,
            color=colors[i % len(colors)],
            linewidth=2,
            markersize=6,
        )

    plt.xlabel("Throughput (packets/node/cycle)", fontsize=12)
    plt.ylabel("Average Packet Latency (cycles)", fontsize=12)
    plt.title(
        "Task 1.1: Latency vs Throughput Curve Analysis",
        fontsize=14,
        fontweight="bold",
    )
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("plots/task1_1_latency_throughput_curve.png", dpi=300)
    plt.show()

    # ===== Task 1 问题2: 低负载延迟分析 (Low-load Latency vs Injection Rate) =====
    plt.figure(figsize=(12, 8))
    # 只显示低负载部分 (injection_rate <= 0.2)
    low_load_data = results_df[results_df["injection_rate"] <= 0.2]
    for i, pattern in enumerate(traffic_patterns):
        pattern_data = low_load_data[
            low_load_data["traffic_pattern"] == pattern
        ]
        plt.plot(
            pattern_data["injection_rate"],
            pattern_data["average_packet_latency"],
            "o-",
            label=pattern,
            color=colors[i % len(colors)],
            linewidth=2,
            markersize=8,
        )

    plt.xlabel("Injection Rate (packets/node/cycle)", fontsize=12)
    plt.ylabel("Average Packet Latency (cycles)", fontsize=12)
    plt.title(
        "Task 1.2: Low-Load Latency Analysis (Injection Rate ≤ 0.2)",
        fontsize=14,
        fontweight="bold",
    )
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.xlim(0, 0.22)
    plt.tight_layout()
    plt.savefig("plots/task1_2_low_load_latency.png", dpi=300)
    plt.show()

    # ===== Task 1 问题3: 最大吞吐量分析 (Maximum Throughput Comparison) =====
    plt.figure(figsize=(10, 6))
    patterns = results_df["traffic_pattern"].unique()
    max_throughput = [
        results_df[results_df["traffic_pattern"] == p]["reception_rate"].max()
        for p in patterns
    ]

    bars = plt.bar(
        patterns,
        max_throughput,
        color=colors[: len(patterns)],
        alpha=0.8,
        edgecolor="black",
    )
    plt.xlabel("Traffic Pattern", fontsize=12)
    plt.ylabel("Maximum Throughput (packets/node/cycle)", fontsize=12)
    plt.title(
        "Task 1.3: Maximum Throughput Analysis", fontsize=14, fontweight="bold"
    )
    plt.xticks(rotation=45)

    # 添加数值标签
    for bar, throughput in zip(bars, max_throughput):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.005,
            f"{throughput:.4f}",
            ha="center",
            va="bottom",
            fontweight="bold",
        )

    plt.ylim(0, max(max_throughput) * 1.15)
    plt.tight_layout()
    plt.savefig("plots/task1_3_max_throughput.png", dpi=300)
    plt.show()

    # ===== Task 1 问题4: 跳数效率分析 (Hop Count vs Performance) =====
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 子图1: 平均跳数对比
    patterns = results_df["traffic_pattern"].unique()
    avg_hops = [
        results_df[results_df["traffic_pattern"] == p]["average_hops"].mean()
        for p in patterns
    ]

    bars1 = ax1.bar(
        patterns,
        avg_hops,
        color=colors[: len(patterns)],
        alpha=0.8,
        edgecolor="black",
    )
    ax1.set_xlabel("Traffic Pattern", fontsize=12)
    ax1.set_ylabel("Average Hops", fontsize=12)
    ax1.set_title(
        "Average Hop Count by Pattern", fontsize=12, fontweight="bold"
    )
    ax1.tick_params(axis="x", rotation=45)

    # 添加数值标签
    for bar, hop in zip(bars1, avg_hops):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.05,
            f"{hop:.2f}",
            ha="center",
            va="bottom",
            fontweight="bold",
        )

    # 子图2: 跳数 vs 低负载延迟散点图
    low_load_latency = []
    for pattern in patterns:
        pattern_low_load = results_df[
            (results_df["traffic_pattern"] == pattern)
            & (results_df["injection_rate"] <= 0.1)
        ]
        avg_latency = pattern_low_load["average_packet_latency"].mean()
        low_load_latency.append(avg_latency)

    scatter = ax2.scatter(
        avg_hops,
        low_load_latency,
        c=colors[: len(patterns)],
        s=150,
        alpha=0.8,
        edgecolors="black",
    )
    ax2.set_xlabel("Average Hops", fontsize=12)
    ax2.set_ylabel("Low-Load Latency (cycles)", fontsize=12)
    ax2.set_title(
        "Hop Count vs Low-Load Latency", fontsize=12, fontweight="bold"
    )
    ax2.grid(True, alpha=0.3)

    # 添加模式标签
    for i, pattern in enumerate(patterns):
        ax2.annotate(
            pattern,
            (avg_hops[i], low_load_latency[i]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=9,
        )

    plt.suptitle(
        "Task 1.4: Hop Count Efficiency Analysis",
        fontsize=14,
        fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig(
        "plots/task1_4_hop_count_analysis.png", dpi=300, bbox_inches="tight"
    )
    plt.show()

    # ===== 额外分析: 延迟成分分解 (Latency Breakdown) =====
    plt.figure(figsize=(12, 8))
    for i, pattern in enumerate(traffic_patterns):
        pattern_data = results_df[results_df["traffic_pattern"] == pattern]
        plt.plot(
            pattern_data["injection_rate"],
            pattern_data["average_packet_queueing_latency"],
            "o-",
            label=f"{pattern} (queueing)",
            color=colors[i % len(colors)],
            linestyle="-",
            alpha=0.7,
        )
        plt.plot(
            pattern_data["injection_rate"],
            pattern_data["average_packet_network_latency"],
            "s--",
            label=f"{pattern} (network)",
            color=colors[i % len(colors)],
            linestyle="--",
            alpha=0.9,
        )

    plt.xlabel("Injection Rate (packets/node/cycle)", fontsize=12)
    plt.ylabel("Latency (cycles)", fontsize=12)
    plt.title(
        "Task 1 Extra: Latency Breakdown Analysis (Queueing vs Network)",
        fontsize=14,
        fontweight="bold",
    )
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)
    plt.grid(True, alpha=0.3)
    plt.yscale("log")  # 使用对数刻度以便更好地观察差异
    plt.tight_layout()
    plt.savefig(
        "plots/task1_extra_latency_breakdown.png", dpi=300, bbox_inches="tight"
    )
    plt.show()


def analyze_results(results_df):
    """分析实验结果 - Task 1 详细分析"""
    print("\n" + "=" * 60)
    print("TASK 1 实验结果详细分析")
    print("=" * 60)

    # ===== 问题1: 延迟-吞吐量曲线分析 =====
    print("\n【问题1】延迟-吞吐量曲线分析:")
    print("-" * 40)
    for pattern in traffic_patterns:
        pattern_data = results_df[results_df["traffic_pattern"] == pattern]
        min_latency = pattern_data["average_packet_latency"].min()
        max_throughput = pattern_data["reception_rate"].max()
        print(
            f"{pattern:15}: 最低延迟={min_latency:6.2f} cycles, 最大吞吐量={max_throughput:.6f} pkt/node/cyc"
        )

    # ===== 问题2: 低负载延迟分析 =====
    print("\n【问题2】低负载延迟分析 (injection_rate ≤ 0.1):")
    print("-" * 40)
    low_load = results_df[results_df["injection_rate"] <= 0.1]
    low_load_latency = (
        low_load.groupby("traffic_pattern")["average_packet_latency"]
        .mean()
        .sort_values()
    )
    for pattern, latency in low_load_latency.items():
        print(f"{pattern:15}: {latency:8.3f} cycles")

    # ===== 问题3: 最大吞吐量分析 =====
    print("\n【问题3】最大吞吐量分析:")
    print("-" * 40)
    max_throughput = (
        results_df.groupby("traffic_pattern")["reception_rate"]
        .max()
        .sort_values(ascending=False)
    )
    for pattern, throughput in max_throughput.items():
        print(f"{pattern:15}: {throughput:.6f} packets/node/cycle")

    # ===== 问题4: 跳数分析 =====
    print("\n【问题4】跳数效率分析:")
    print("-" * 40)
    avg_hops = (
        results_df.groupby("traffic_pattern")["average_hops"]
        .mean()
        .sort_values()
    )
    for pattern, hops in avg_hops.items():
        low_latency = low_load_latency[pattern]
        print(
            f"{pattern:15}: {hops:5.2f} hops, 低负载延迟={low_latency:6.2f} cycles"
        )

    # ===== 性能排名总结 =====
    print("\n【总结】性能排名:")
    print("-" * 40)
    print("低负载延迟排名 (越小越好):")
    for i, (pattern, latency) in enumerate(low_load_latency.items(), 1):
        print(f"  {i}. {pattern:15}: {latency:6.2f} cycles")

    print("\n最大吞吐量排名 (越大越好):")
    for i, (pattern, throughput) in enumerate(max_throughput.items(), 1):
        print(f"  {i}. {pattern:15}: {throughput:.6f} pkt/node/cyc")

    print("\n跳数效率排名 (越小越好):")
    for i, (pattern, hops) in enumerate(avg_hops.items(), 1):
        print(f"  {i}. {pattern:15}: {hops:5.2f} hops")

    # ===== 关键发现 =====
    print("\n【关键发现】:")
    print("-" * 40)
    best_low_latency = low_load_latency.index[0]
    best_throughput = max_throughput.index[0]
    best_hops = avg_hops.index[0]

    print(
        f"• 最佳低负载延迟: {best_low_latency} ({low_load_latency[best_low_latency]:.2f} cycles)"
    )
    print(
        f"• 最佳吞吐量性能: {best_throughput} ({max_throughput[best_throughput]:.6f} pkt/node/cyc)"
    )
    print(f"• 最佳跳数效率: {best_hops} ({avg_hops[best_hops]:.2f} hops)")

    if best_low_latency == best_hops:
        print(f"• {best_low_latency} 在低延迟和跳数效率方面都表现最佳")

    print("\n" + "=" * 60)


def main():
    """主函数"""
    print("开始运行网络性能实验...")

    # 确保输出目录存在
    os.makedirs("results", exist_ok=True)

    # 运行所有实验
    all_results = []
    total_experiments = len(traffic_patterns) * len(injection_rates)
    current_exp = 0

    for pattern in traffic_patterns:
        for rate in injection_rates:
            current_exp += 1
            print(f"\n进度: {current_exp}/{total_experiments}")

            result = run_experiment(pattern, rate)
            if result:
                all_results.append(result)

    # 保存结果
    results_df = pd.DataFrame(all_results)
    results_df.to_csv("results/experiment_results.csv", index=False)
    print(f"\n实验完成！共完成 {len(all_results)} 个实验")

    # 绘制图表
    if len(all_results) > 0:
        plot_results(results_df)
        analyze_results(results_df)
    else:
        print("没有成功的实验结果")


if __name__ == "__main__":
    main()
