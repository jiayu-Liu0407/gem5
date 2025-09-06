# Copyright (c) 2010 Advanced Micro Devices, Inc.
# All rights reserved.
#
# [版权声明部分保持不变]

import math
from m5.params import *
from m5.objects import *

from common import FileSystemConfig
from topologies.BaseTopology import SimpleTopology

class TwoBitTree(SimpleTopology):
    description = "TwoBitTree"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        nodes = self.nodes

        # 计算路由器数量（确保是2的幂）
        num_routers = options.num_cpus
        n = math.ceil(math.log2(num_routers))
        actual_routers = 2**n
        
        if num_routers != actual_routers:
            print(f"警告: 2BitTree拓扑需要2的幂数量的路由器")
            print(f"调整路由器数量从 {num_routers} 到 {actual_routers}")
            num_routers = actual_routers

        # 默认链路和路由器延迟
        link_latency = options.link_latency
        router_latency = options.router_latency

        # 创建路由器
        routers = [
            Router(router_id=i, latency=router_latency)
            for i in range(num_routers)
        ]
        network.routers = routers

        # 链路ID计数器
        link_count = 0

        # 连接控制器到路由器
        ext_links = []
        cntrls_per_router, remainder = divmod(len(nodes), num_routers)
        
        for i, node in enumerate(nodes):
            if i < (len(nodes) - remainder):
                router_id = i // cntrls_per_router
            else:
                router_id = i % num_routers  # 改为循环分配而不是都连到0
                
            ext_links.append(
                ExtLink(
                    link_id=link_count,
                    ext_node=node,
                    int_node=routers[router_id],
                    latency=link_latency,
                )
            )
            link_count += 1
        network.ext_links = ext_links

        # 创建二进制树型链路
        int_links = []
        
        # 跟踪已经创建的链接，避免重复
        connected_pairs = set()
        
        # 对每个路由器，连接到 (i+2^t) mod num_routers 位置
        for i in range(num_routers):
            for t in range(n):
                # 计算目标路由器ID
                j = (i + (1 << t)) % num_routers
                
                # 确保不创建重复链接
                if (i, j) in connected_pairs or (j, i) in connected_pairs:
                    continue
                
                # 记录这对路由器已经连接
                connected_pairs.add((i, j))
                
                # 使用特定的端口名称格式：Bit_t_ij 和 Bit_t_ji
                # 这确保了每个链接使用唯一的端口名称
                src_outport = f"Bit_{t}_{i}_{j}"
                dst_inport = f"In_Bit_{t}_{i}_{j}"
                
                # 创建从i到j的链接
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[i],
                        dst_node=routers[j],
                        src_outport=src_outport,
                        dst_inport=dst_inport,
                        latency=link_latency,
                        weight=1,
                    )
                )
                link_count += 1
                
                # 创建从j到i的反向链接，使用不同的端口名称
                src_outport_rev = f"Bit_{t}_{j}_{i}"
                dst_inport_rev = f"In_Bit_{t}_{j}_{i}"
                
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[j],
                        dst_node=routers[i],
                        src_outport=src_outport_rev,
                        dst_inport=dst_inport_rev,
                        latency=link_latency,
                        weight=1,
                    )
                )
                link_count += 1

        network.int_links = int_links

    def registerTopology(self, options):
        for i in range(options.num_cpus):
            FileSystemConfig.register_node(
                [i], MemorySize(options.mem_size) // options.num_cpus, i
            )