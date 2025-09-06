from m5.params import *
from m5.objects import *

from topologies.BaseTopology import SimpleTopology

class MeshBypass(SimpleTopology):
    description = 'MeshBypass'

    def __init__(self, controllers):
        # 关键：保存 controllers 列表本身，不要取 len(...)
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        nodes = self.nodes  # 这是 controllers 列表

        num_routers = options.num_cpus
        num_rows = options.mesh_rows
        assert num_rows > 0 and num_routers % num_rows == 0
        num_columns = int(num_routers / num_rows)

        # 创建 routers
        routers = [Router(router_id=i, latency=options.router_latency)
                   for i in range(num_routers)]
        network.routers = routers

        link_count = 0

        # 连接所有 controllers 到 routers（round-robin 分配）
        ext_links = []
        for (i, node) in enumerate(nodes):
            _, router_id = divmod(i, num_routers)
            ext_links.append(ExtLink(link_id=link_count,
                                     ext_node=node,
                                     int_node=routers[router_id],
                                     latency=options.link_latency))
            link_count += 1

        # 确保至少有一个外部节点被连接
        assert len(ext_links) > 0, "No ext_links created; controllers list empty?"
        network.ext_links = ext_links

        # 内部链路：标准 Mesh 双向
        int_links = []

        # East -> West
        for row in range(num_rows):
            for col in range(num_columns - 1):
                east_out = col + (row * num_columns)
                west_in = (col + 1) + (row * num_columns)
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[east_out],
                                         dst_node=routers[west_in],
                                         src_outport="East",
                                         dst_inport="West",
                                         latency=options.link_latency,
                                         weight=1))
                link_count += 1

        # West -> East
        for row in range(num_rows):
            for col in range(num_columns - 1):
                west_out = (col + 1) + (row * num_columns)
                east_in = col + (row * num_columns)
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[west_out],
                                         dst_node=routers[east_in],
                                         src_outport="West",
                                         dst_inport="East",
                                         latency=options.link_latency,
                                         weight=1))
                link_count += 1

        # South -> North
        for row in range(num_rows - 1):
            for col in range(num_columns):
                south_out = col + ((row + 1) * num_columns)
                north_in = col + (row * num_columns)
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[south_out],
                                         dst_node=routers[north_in],
                                         src_outport="North",
                                         dst_inport="South",
                                         latency=options.link_latency,
                                         weight=2))
                link_count += 1

        # North -> South
        for row in range(num_rows - 1):
            for col in range(num_columns):
                north_out = col + (row * num_columns)         # 上方路由器
                south_in = col + ((row + 1) * num_columns)    # 下方路由器
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[north_out],  # 修正：上方为源
                                         dst_node=routers[south_in],   # 修正：下方为目的
                                         src_outport="South",          # 修正：上往下用 South 出口
                                         dst_inport="North",           # 修正：下方用 North 入口
                                         latency=options.link_latency,
                                         weight=2))
                link_count += 1

        # Bypass 对角线（Southeast / Northwest），建议双向，若你坚持单向可删除反向段
        for row in range(num_rows - 1):
            for col in range(num_columns - 1):
                src_router = col + (row * num_columns)
                dst_router = (col + 1) + ((row + 1) * num_columns)
                # Southeast
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[src_router],
                                         dst_node=routers[dst_router],
                                         src_outport="Southeast",
                                         dst_inport="Northwest",
                                         latency=options.link_latency,
                                         weight=1))
                link_count += 1
                # Northwest (反向)
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[dst_router],
                                         dst_node=routers[src_router],
                                         src_outport="Northwest",
                                         dst_inport="Southeast",
                                         latency=options.link_latency,
                                         weight=1))
                link_count += 1
                
        for row in range(1, num_rows):  # 从第1行开始，因为需要向上
            for col in range(num_columns - 1):  # 到倒数第2列，因为需要向右
                src_router = col + (row * num_columns)
                dst_router = (col + 1) + ((row - 1) * num_columns)
                # Northeast
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[src_router],
                                         dst_node=routers[dst_router],
                                         src_outport="Northeast",
                                         dst_inport="Southwest",
                                         latency=options.link_latency,
                                         weight=1))
                link_count += 1
                # Southwest (反向)
                int_links.append(IntLink(link_id=link_count,
                                         src_node=routers[dst_router],
                                         dst_node=routers[src_router],
                                         src_outport="Southwest",
                                         dst_inport="Northeast",
                                         latency=options.link_latency,
                                         weight=1))
                link_count += 1
        network.int_links = int_links