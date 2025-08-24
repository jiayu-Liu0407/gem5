import os
import subprocess
import csv
import matplotlib

matplotlib.use("Agg")  # 设置非交互式后端
import matplotlib.pyplot as plt
import shutil

# 定义5种流量模式
traffic_patterns = [
    "uniform_random",
    "shuffle",
    "transpose",
    "tornado",
    "neighbor",
]

# 定义参数变化实验（移除baseline，只保留3个可变参数）
parameter_experiments = [
    {
        "param_name": "vcs-per-vnet",
        "experiments": [
            {"name": "vcs-per-vnet-1", "extra_args": "--vcs-per-vnet=1"},
            {"name": "vcs-per-vnet-2", "extra_args": "--vcs-per-vnet=2"},
            {"name": "vcs-per-vnet-4", "extra_args": "--vcs-per-vnet=4"},
            {"name": "vcs-per-vnet-8", "extra_args": "--vcs-per-vnet=8"},
        ],
    },
    {
        "param_name": "router-latency",
        "experiments": [
            {"name": "router-latency-1", "extra_args": "--router-latency=1"},
            {"name": "router-latency-2", "extra_args": "--router-latency=2"},
            {"name": "router-latency-4", "extra_args": "--router-latency=4"},
            {"name": "router-latency-8", "extra_args": "--router-latency=8"},
        ],
    },
    {
        "param_name": "link-width-bits",
        "experiments": [
            {"name": "link-width-64", "extra_args": "--link-width-bits=64"},
            {"name": "link-width-128", "extra_args": "--link-width-bits=128"},
            {"name": "link-width-256", "extra_args": "--link-width-bits=256"},
            {"name": "link-width-512", "extra_args": "--link-width-bits=512"},
        ],
    },
]

# 清理所有旧的输出文件夹和文件
print("清理旧的实验结果...")
for file in ["results_summary.csv", "parameter_comparison.png"]:
    if os.path.exists(file):
        os.remove(file)

# 清理并创建图表输出文件夹
plot_dir = "run_8_experiment_plot"
if os.path.exists(plot_dir):
    shutil.rmtree(plot_dir)
os.makedirs(plot_dir)

# 清理所有 m5out 相关文件夹
for item in os.listdir("."):
    if item.startswith("m5out"):
        if os.path.isdir(item):
            shutil.rmtree(item)
        else:
            os.remove(item)


def extract_stats(stats_file):
    """从stats.txt文件中提取网络统计信息"""
    stats = {}

    with open(stats_file, "r") as f:
        content = f.read()

    # 提取关键统计信息
    metrics = {
        "average_packet_latency": "system.ruby.network.average_packet_latency",
        "reception_rate": "system.ruby.network.reception_rate",
    }

    for key, pattern in metrics.items():
        lines = [
            line
            for line in content.split("\n")
            if pattern in line and not line.strip().startswith("#")
        ]
        if lines:
            try:
                parts = lines[0].split()
                value_str = parts[-2]
                stats[key] = float(value_str)
            except (ValueError, IndexError):
                try:
                    if "=" in lines[0]:
                        value_part = lines[0].split("=")[1].strip()
                        value_str = value_part.split()[0]
                        stats[key] = float(value_str)
                    else:
                        stats[key] = 0.0
                except:
                    stats[key] = 0.0
        else:
            stats[key] = 0.0

    return stats


def run_experiment(traffic_pattern, experiment_config):
    """运行单个实验"""
    print(f"  运行: {traffic_pattern} with {experiment_config['name']}")

    # 确保删除 m5out 文件夹
    if os.path.exists("m5out"):
        shutil.rmtree("m5out")

    cmd = (
        "./build/NULL/gem5.opt configs/example/garnet_synth_traffic.py "
        "--network=garnet --num-cpus=64 --num-dirs=64 "
        "--topology=Mesh_XY --mesh-rows=8 "
        "--inj-vnet=0 --sim-cycles=10000 --injectionrate=0.01 "
        f"--synthetic={traffic_pattern} {experiment_config['extra_args']}"
    )

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            print(f"    实验失败: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        print(f"    实验超时")
        return None
    except Exception as e:
        print(f"    运行错误: {e}")
        return None

    # 创建备份文件夹
    out_dir = f"m5out_{traffic_pattern}_{experiment_config['name']}"
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree("m5out", out_dir)

    stats_path = os.path.join(out_dir, "stats.txt")
    if not os.path.exists(stats_path):
        print(f"    统计文件不存在: {stats_path}")
        return None

    try:
        stats = extract_stats(stats_path)
        print(
            f"    延迟: {stats['average_packet_latency']:.6f}, 吞吐量: {stats['reception_rate']:.6f}"
        )
        return stats
    except Exception as e:
        print(f"    统计提取错误: {e}")
        return None


# 存储所有结果
all_results = []

# 运行所有实验
for param_group in parameter_experiments:
    param_name = param_group["param_name"]
    print(f"\n=== 测试参数: {param_name} ===")

    for experiment in param_group["experiments"]:
        exp_name = experiment["name"]
        print(f"\n--- 实验配置: {exp_name} ---")

        for traffic in traffic_patterns:
            stats = run_experiment(traffic, experiment)
            if stats:
                result = {
                    "parameter": param_name,
                    "experiment": exp_name,
                    "traffic_pattern": traffic,
                    "latency": stats["average_packet_latency"],
                    "throughput": stats["reception_rate"],
                }
                all_results.append(result)

# 保存详细结果到CSV
print("\n保存结果到CSV文件...")
with open("results_summary.csv", "w", newline="") as f:
    fieldnames = [
        "parameter",
        "experiment",
        "traffic_pattern",
        "latency",
        "throughput",
    ]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_results)

# 为每个流量模式和每个参数生成单独的图表 (5 patterns × 3 parameters = 15 plots)
print("\n生成单独的参数对比图表...")

if all_results:
    param_groups = ["vcs-per-vnet", "router-latency", "link-width-bits"]
    colors = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
    ]  # 更好的颜色方案

    plot_count = 0

    for traffic in traffic_patterns:
        for param in param_groups:
            plot_count += 1

            # 获取当前流量模式和参数的所有结果
            filtered_results = [
                r
                for r in all_results
                if r["traffic_pattern"] == traffic and r["parameter"] == param
            ]

            if filtered_results:
                print(f"生成图表 {plot_count}/15: {traffic} - {param}")

                # 排序数据以确保连线正确
                def extract_param_value(exp_name):
                    """从实验名称中提取参数值用于排序"""
                    if param == "vcs-per-vnet":
                        return int(exp_name.split("-")[-1])
                    elif param == "router-latency":
                        return int(exp_name.split("-")[-1])
                    elif param == "link-width-bits":
                        return int(exp_name.split("-")[-1])
                    return 0

                filtered_results.sort(
                    key=lambda x: extract_param_value(x["experiment"])
                )

                latencies = [r["latency"] for r in filtered_results]
                throughputs = [r["throughput"] for r in filtered_results]
                param_values = [
                    extract_param_value(r["experiment"])
                    for r in filtered_results
                ]

                # 创建图表
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

                # 子图1: 延迟 vs 参数值
                ax1.plot(
                    param_values,
                    latencies,
                    "o-",
                    linewidth=3,
                    markersize=8,
                    color=colors[0],
                    markerfacecolor="white",
                    markeredgewidth=2,
                )
                ax1.set_xlabel(f'{param.replace("-", " ").title()}')
                ax1.set_ylabel("Average Packet Latency (cycles)")
                ax1.set_title(f'Latency vs {param.replace("-", " ").title()}')
                ax1.grid(True, alpha=0.3)
                ax1.set_xscale(
                    "log"
                    if param in ["vcs-per-vnet", "router-latency"]
                    else "linear"
                )

                # 添加数值标签
                for i, (x, y) in enumerate(zip(param_values, latencies)):
                    ax1.annotate(
                        f"{y:.2f}",
                        (x, y),
                        textcoords="offset points",
                        xytext=(0, 10),
                        ha="center",
                        fontsize=9,
                    )

                # 子图2: 吞吐量 vs 参数值
                ax2.plot(
                    param_values,
                    throughputs,
                    "s-",
                    linewidth=3,
                    markersize=8,
                    color=colors[1],
                    markerfacecolor="white",
                    markeredgewidth=2,
                )
                ax2.set_xlabel(f'{param.replace("-", " ").title()}')
                ax2.set_ylabel("Throughput (packets/node/cycle)")
                ax2.set_title(
                    f'Throughput vs {param.replace("-", " ").title()}'
                )
                ax2.grid(True, alpha=0.3)
                ax2.set_xscale(
                    "log"
                    if param in ["vcs-per-vnet", "router-latency"]
                    else "linear"
                )

                # 添加数值标签
                for i, (x, y) in enumerate(zip(param_values, throughputs)):
                    ax2.annotate(
                        f"{y:.4f}",
                        (x, y),
                        textcoords="offset points",
                        xytext=(0, 10),
                        ha="center",
                        fontsize=9,
                    )

                # 设置总标题
                fig.suptitle(
                    f'{traffic.replace("_", " ").title()} Traffic Pattern - {param.replace("-", " ").title()} Impact',
                    fontsize=16,
                    fontweight="bold",
                )

                plt.tight_layout()

                # 保存图表
                filename = f"{traffic}_{param}_analysis.png"
                filepath = os.path.join(plot_dir, filename)
                plt.savefig(filepath, dpi=300, bbox_inches="tight")
                plt.close()

                print(f"  保存到: {filepath}")
            else:
                print(
                    f"跳过图表 {plot_count}/15: {traffic} - {param} (无数据)"
                )

    # 生成汇总图表 (可选)
    print("\n生成汇总对比图表...")

    fig, axes = plt.subplots(3, 5, figsize=(25, 18))

    for param_idx, param in enumerate(param_groups):
        for traffic_idx, traffic in enumerate(traffic_patterns):
            ax = axes[param_idx, traffic_idx]

            filtered_results = [
                r
                for r in all_results
                if r["traffic_pattern"] == traffic and r["parameter"] == param
            ]

            if filtered_results:

                def extract_param_value(exp_name):
                    return int(exp_name.split("-")[-1])

                filtered_results.sort(
                    key=lambda x: extract_param_value(x["experiment"])
                )

                latencies = [r["latency"] for r in filtered_results]
                throughputs = [r["throughput"] for r in filtered_results]
                param_values = [
                    extract_param_value(r["experiment"])
                    for r in filtered_results
                ]

                # 绘制延迟-吞吐量曲线
                ax.plot(
                    throughputs, latencies, "o-", linewidth=2, markersize=6
                )

                # 添加参数值标签
                for i, (x, y, pv) in enumerate(
                    zip(throughputs, latencies, param_values)
                ):
                    ax.annotate(
                        str(pv),
                        (x, y),
                        xytext=(5, 5),
                        textcoords="offset points",
                        fontsize=8,
                    )

            ax.set_xlabel("Throughput")
            ax.set_ylabel("Latency")
            ax.set_title(f"{traffic}\n{param}")
            ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        os.path.join(plot_dir, "summary_all_experiments.png"),
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()

    print(f"\n总共生成了 {plot_count} 个单独图表和 1 个汇总图表")
    print(f"所有图表保存在: {plot_dir}/ 文件夹中")

    # 生成图表目录
    with open(os.path.join(plot_dir, "plot_index.txt"), "w") as f:
        f.write("图表索引 - 参数分析结果\n")
        f.write("=" * 50 + "\n\n")

        for traffic in traffic_patterns:
            f.write(f"{traffic.replace('_', ' ').title()} Traffic Pattern:\n")
            for param in param_groups:
                filename = f"{traffic}_{param}_analysis.png"
                f.write(f"  - {param.replace('-', ' ').title()}: {filename}\n")
            f.write("\n")

        f.write("汇总图表:\n")
        f.write("  - summary_all_experiments.png\n")

    # 打印汇总分析
    print("\n=== 结果分析 ===")

    for param in param_groups:
        print(f"\n{param} 参数影响:")
        param_results = [r for r in all_results if r["parameter"] == param]

        if param_results:
            # 按流量模式分组分析
            for traffic in traffic_patterns:
                traffic_results = [
                    r for r in param_results if r["traffic_pattern"] == traffic
                ]
                if len(traffic_results) > 1:
                    latencies = [r["latency"] for r in traffic_results]
                    throughputs = [r["throughput"] for r in traffic_results]

                    print(f"  {traffic}:")
                    print(
                        f"    延迟范围: {min(latencies):.6f} - {max(latencies):.6f}"
                    )
                    print(
                        f"    吞吐量范围: {min(throughputs):.6f} - {max(throughputs):.6f}"
                    )
                elif len(traffic_results) == 1:
                    r = traffic_results[0]
                    print(
                        f"  {traffic}: 延迟={r['latency']:.6f}, 吞吐量={r['throughput']:.6f}"
                    )

else:
    print("没有找到有效的统计数据，请检查gem5输出")

print("\n所有实验完成！")
print("生成的文件:")
print("- results_summary.csv: 详细结果数据")
print(f"- {plot_dir}/: 包含15个单独的参数分析图表")
print(f"- {plot_dir}/summary_all_experiments.png: 汇总对比图表")
print(f"- {plot_dir}/plot_index.txt: 图表索引文件")
