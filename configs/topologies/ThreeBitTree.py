# Copyright (c) 2010 Advanced Micro Devices, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.

import math
from m5.params import *
from m5.objects import *

from common import FileSystemConfig
from topologies.BaseTopology import SimpleTopology

class ThreeBitTree(SimpleTopology):
    description = "ThreeBitTree"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        nodes = self.nodes

        # 计算路由器数量和所需的3进制位数
        num_routers = options.num_cpus
        n = math.ceil(math.log(num_routers, 3))
        max_routers = 3**n
        
        if num_routers > max_routers:
            print(f"警告: ThreeBitTree拓扑需要m <= 3^n的路由器数量")
            print(f"调整路由器数量从 {num_routers} 到 {max_routers}")
            num_routers = max_routers

        # 确保路由器数量满足 3^(n-1) < m <= 3^n
        min_routers = 3**(n-1) if n > 0 else 0
        if num_routers <= min_routers:
            n = math.ceil(math.log(num_routers, 3))
            print(f"警告: 调整位数n为{n}，确保3^(n-1) < m <= 3^n")

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
                router_id = i % num_routers  # 循环分配
                
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

        # 创建三进制树型链路
        int_links = []
        
        # 跟踪已经创建的链接，避免重复
        connected_pairs = set()
        
        # 获取虚拟网络总数，用于分配不同的vnet集合
        num_vnet = 3  # 默认值
        if hasattr(options, 'vcs_per_vnet') and options.vcs_per_vnet > 0:
            num_vnet = options.num_virtual_networks if hasattr(options, 'num_virtual_networks') else 3
        
        # 对每个路由器，连接到 (i+3^t) mod num_routers 位置
        for i in range(num_routers):
            for t in range(n):
                # 计算3的t次方
                power_3t = 3**t
                
                # 连接正向链路: i -> (i+3^t) % num_routers
                j = (i + power_3t) % num_routers
                
                # 确保不创建重复链接
                if (i, j) in connected_pairs or (j, i) in connected_pairs:
                    continue
                
                # 记录这对路由器已经连接
                connected_pairs.add((i, j))
                
                # 为正向和反向链接分配不同的vnet
                forward_vnets = [t % num_vnet]
                reverse_vnets = [(t + num_vnet//2) % num_vnet]
                
                # 创建从i到j的链接
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[i],
                        dst_node=routers[j],
                        src_outport=f"Tri_{t}_{i}_{j}",
                        dst_inport=f"In_Tri_{t}_{i}_{j}",
                        latency=link_latency,
                        weight=1,
                    )
                )
                link_count += 1
                
                # 创建从j到i的反向链接
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[j],
                        dst_node=routers[i],
                        src_outport=f"Tri_{t}_{j}_{i}",
                        dst_inport=f"In_Tri_{t}_{j}_{i}",
                        latency=link_latency,
                        weight=1,
                    )
                )
                link_count += 1
                
                # 对每个3进制位，还需考虑-3^t (即加上2*3^t)
                k = (i + 2 * power_3t) % num_routers
                
                # 确保不创建重复链接
                if (i, k) in connected_pairs or (k, i) in connected_pairs:
                    continue
                
                # 记录这对路由器已经连接
                connected_pairs.add((i, k))
                
                # 为正向和反向链接分配不同的vnet
                forward_vnets_neg = [(t + 1) % num_vnet]
                reverse_vnets_neg = [(t + 1 + num_vnet//2) % num_vnet]
                
                # 创建从i到k的链接 (负向连接)
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[i],
                        dst_node=routers[k],
                        src_outport=f"TriNeg_{t}_{i}_{k}",
                        dst_inport=f"In_TriNeg_{t}_{i}_{k}",
                        latency=link_latency,
                        weight=1,
                    )
                )
                link_count += 1
                
                # 创建从k到i的反向链接
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[k],
                        dst_node=routers[i],
                        src_outport=f"TriNeg_{t}_{k}_{i}",
                        dst_inport=f"In_TriNeg_{t}_{k}_{i}",
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