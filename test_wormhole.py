#!/usr/bin/env python3
"""
Wormhole Flow Control Performance Test Script
Compares three configurations:
1. VC=1, Depth=1 (baseline)
2. VC=16, Depth=1
3. VC=1, Depth=16 (wormhole)
"""

import os
import subprocess
import re
import time
import shutil


def run_simulation(config_name, extra_args=""):
    """Run a single simulation configuration"""
    print(f"\n{'='*60}")
    print(f"Running {config_name} configuration...")
    print(f"{'='*60}")

    # Base command
    base_cmd = [
        "./build/NULL/gem5.opt",
        "configs/example/garnet_synth_traffic.py",
        "--network=garnet",
        "--num-cpus=64",
        "--num-dirs=64",
        "--topology=Mesh_XY",
        "--mesh-rows=4",
        "--inj-vnet=0",
        "--synthetic=shuffle",
        "--sim-cycles=10000",
        "--injectionrate=0.7",
    ]

    # Add extra arguments
    if extra_args:
        base_cmd.extend(extra_args.split())

    print(f"Command: {' '.join(base_cmd)}")

    # Run simulation
    start_time = time.time()
    try:
        result = subprocess.run(
            base_cmd, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            print(f"ERROR: Simulation failed!")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return None
        end_time = time.time()
        print(f"Simulation completed in {end_time - start_time:.2f} seconds")

        # Move the default m5out directory to a configuration-specific name
        output_dir = f"m5out_{config_name}"
        if os.path.exists("m5out"):
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
            shutil.move("m5out", output_dir)
            return output_dir
        else:
            print("ERROR: m5out directory not found")
            return None

    except subprocess.TimeoutExpired:
        print("ERROR: Simulation timed out!")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def extract_stats(output_dir):
    """Extract network statistics from m5out/stats.txt"""
    stats_file = os.path.join(output_dir, "stats.txt")
    if not os.path.exists(stats_file):
        print(f"ERROR: Stats file not found: {stats_file}")
        return None

    stats = {}
    patterns = {
        "packets_injected": r"system\.ruby\.network\.packets_injected::total\s+(\d+)",
        "packets_received": r"system\.ruby\.network\.packets_received::total\s+(\d+)",
        "average_packet_queueing_latency": r"system\.ruby\.network\.average_packet_queueing_latency\s+([\d.]+)",
        "average_packet_network_latency": r"system\.ruby\.network\.average_packet_network_latency\s+([\d.]+)",
        "average_packet_latency": r"system\.ruby\.network\.average_packet_latency\s+([\d.]+)",
        "average_hops": r"system\.ruby\.network\.average_hops\s+([\d.]+)",
        "reception_rate": r"system\.ruby\.network\.reception_rate\s+([\d.]+)",
    }

    with open(stats_file, "r") as f:
        content = f.read()

    for stat_name, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            try:
                if stat_name in ["packets_injected", "packets_received"]:
                    stats[stat_name] = int(match.group(1))
                else:
                    stats[stat_name] = float(match.group(1))
            except ValueError:
                stats[stat_name] = match.group(1)
        else:
            print(f"WARNING: Could not find {stat_name} in stats")
            stats[stat_name] = "N/A"

    return stats


def save_detailed_stats(config_name, output_dir, results_file):
    """Save detailed stats using the provided grep commands"""
    stats_file = os.path.join(output_dir, "stats.txt")
    if not os.path.exists(stats_file):
        return

    with open(results_file, "a") as f:
        f.write(f"\n# {config_name} Configuration Stats\n")
        f.write(f"# {'='*50}\n")

    # Define the grep commands
    grep_commands = [
        (r"packets_injected::total", "packets_injected", "packets"),
        (r"packets_received::total", "packets_received", "packets"),
        (
            r"average_packet_queueing_latency",
            "average_packet_queueing_latency",
            "cycles/packet",
        ),
        (
            r"average_packet_network_latency",
            "average_packet_network_latency",
            "cycles/packet",
        ),
        (r"average_packet_latency", "average_packet_latency", "cycles/packet"),
        (r"average_hops", "average_hops", "hops/flit"),
        (r"reception_rate", "reception_rate", "packets/node/cycle"),
    ]

    for pattern, stat_name, unit in grep_commands:
        cmd = f"grep '{pattern}' {stats_file}"
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip()
                # Extract the value using regex
                match = re.search(r"(\d+\.?\d*)\s*\(.*\)?\s*$", line)
                if match:
                    value = match.group(1)
                    with open(results_file, "a") as f:
                        f.write(f"{stat_name} = {value} {unit}\n")
        except Exception as e:
            print(f"Error processing {stat_name}: {e}")


def print_comparison_table(all_stats):
    """Print a formatted comparison table"""
    print(f"\n{'='*80}")
    print("PERFORMANCE COMPARISON RESULTS")
    print(f"{'='*80}")

    configs = list(all_stats.keys())

    # Table header
    print(f"{'Metric':<30} {'Baseline':<15} {'VC=16':<15} {'Wormhole':<15}")
    print(f"{'-'*30} {'-'*15} {'-'*15} {'-'*15}")

    metrics = [
        ("packets_injected", "Packets Injected"),
        ("packets_received", "Packets Received"),
        ("average_packet_queueing_latency", "Avg Queue Latency"),
        ("average_packet_network_latency", "Avg Network Latency"),
        ("average_packet_latency", "Avg Total Latency"),
        ("average_hops", "Average Hops"),
        ("reception_rate", "Reception Rate"),
    ]

    for metric_key, metric_name in metrics:
        row = f"{metric_name:<30}"
        for config in configs:
            if config in all_stats and metric_key in all_stats[config]:
                value = all_stats[config][metric_key]
                if isinstance(value, float):
                    row += f"{value:<15.3f}"
                else:
                    row += f"{value:<15}"
            else:
                row += f"{'N/A':<15}"
        print(row)

    # Calculate improvements
    if len(configs) >= 2 and "baseline" in all_stats:
        baseline_stats = all_stats["baseline"]
        print(f"\n{'='*80}")
        print("PERFORMANCE IMPROVEMENTS vs BASELINE")
        print(f"{'='*80}")

        for config in configs:
            if config == "baseline":
                continue

            config_stats = all_stats[config]
            print(f"\n{config} vs Baseline:")

            for metric_key, metric_name in metrics:
                if (
                    metric_key in baseline_stats
                    and metric_key in config_stats
                    and isinstance(baseline_stats[metric_key], (int, float))
                    and isinstance(config_stats[metric_key], (int, float))
                    and baseline_stats[metric_key] != 0
                ):

                    baseline_val = baseline_stats[metric_key]
                    config_val = config_stats[metric_key]

                    if metric_key in [
                        "average_packet_queueing_latency",
                        "average_packet_network_latency",
                        "average_packet_latency",
                    ]:
                        # Lower is better for latency
                        improvement = (
                            (baseline_val - config_val) / baseline_val
                        ) * 100
                        print(
                            f"  {metric_name}: {improvement:+.1f}% {'(better)' if improvement > 0 else '(worse)'}"
                        )
                    else:
                        # Higher is better for throughput metrics
                        improvement = (
                            (config_val - baseline_val) / baseline_val
                        ) * 100
                        print(
                            f"  {metric_name}: {improvement:+.1f}% {'(better)' if improvement > 0 else '(worse)'}"
                        )


def main():
    """Main test function"""
    print("Wormhole Flow Control Performance Test")
    print("=" * 60)

    # Test configurations
    configurations = [
        ("baseline", "--vcs-per-vnet=1"),  # VC=1, Depth=1
        ("vc16", "--vcs-per-vnet=16"),  # VC=16, Depth=1
        (
            "wormhole",
            "--vcs-per-vnet=1 --wormhole",
        ),  # VC=1, Depth=16 (wormhole)
    ]

    all_stats = {}
    results_file = "network_comparison_results.txt"

    # Clear previous results
    if os.path.exists(results_file):
        os.remove(results_file)

    with open(results_file, "w") as f:
        f.write("Network Performance Comparison Results\n")
        f.write("=" * 50 + "\n")
        f.write(f"Test Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("Configurations:\n")
        f.write("1. Baseline: VC=1, Depth=1\n")
        f.write("2. VC16: VC=16, Depth=1\n")
        f.write("3. Wormhole: VC=1, Depth=16 (wormhole flow control)\n")
        f.write("=" * 50 + "\n")

    # Run each configuration
    for config_name, args in configurations:
        output_dir = run_simulation(config_name, args)
        if output_dir:
            stats = extract_stats(output_dir)
            if stats:
                all_stats[config_name] = stats
                save_detailed_stats(config_name, output_dir, results_file)
                print(f"✓ {config_name} completed successfully")
            else:
                print(f"✗ Failed to extract stats for {config_name}")
        else:
            print(f"✗ {config_name} simulation failed")

    # Print comparison table
    if all_stats:
        print_comparison_table(all_stats)

        # Save summary to file
        with open(results_file, "a") as f:
            f.write(f"\n\n# SUMMARY TABLE\n")
            f.write(f"# Configuration comparison\n")
            for config_name, stats in all_stats.items():
                f.write(f"\n[{config_name}]\n")
                for metric, value in stats.items():
                    f.write(f"{metric} = {value}\n")
    else:
        print("No successful simulations to compare!")

    print(f"\nDetailed results saved to: {results_file}")
    print("Test completed!")


if __name__ == "__main__":
    main()
