/*
 * Copyright (c) 2008 Princeton University
 * Copyright (c) 2016 Georgia Institute of Technology
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */


#include "mem/ruby/network/garnet/RoutingUnit.hh"

#include "base/cast.hh"
#include "base/compiler.hh"
#include "debug/RubyNetwork.hh"
#include "mem/ruby/network/garnet/InputUnit.hh"
#include "mem/ruby/network/garnet/Router.hh"
#include "mem/ruby/slicc_interface/Message.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

RoutingUnit::RoutingUnit(Router *router)
{
    m_router = router;
    m_routing_table.clear();
    m_weight_table.clear();
}

void
RoutingUnit::addRoute(std::vector<NetDest>& routing_table_entry)
{
    if (routing_table_entry.size() > m_routing_table.size()) {
        m_routing_table.resize(routing_table_entry.size());
    }
    for (int v = 0; v < routing_table_entry.size(); v++) {
        m_routing_table[v].push_back(routing_table_entry[v]);
    }
}

void
RoutingUnit::addWeight(int link_weight)
{
    m_weight_table.push_back(link_weight);
}

bool
RoutingUnit::supportsVnet(int vnet, std::vector<int> sVnets)
{
    // If all vnets are supported, return true
    if (sVnets.size() == 0) {
        return true;
    }

    // Find the vnet in the vector, return true
    if (std::find(sVnets.begin(), sVnets.end(), vnet) != sVnets.end()) {
        return true;
    }

    // Not supported vnet
    return false;
}

/*
 * This is the default routing algorithm in garnet.
 * The routing table is populated during topology creation.
 * Routes can be biased via weight assignments in the topology file.
 * Correct weight assignments are critical to provide deadlock avoidance.
 */
int
RoutingUnit::lookupRoutingTable(int vnet, NetDest msg_destination)
{
    // First find all possible output link candidates
    // For ordered vnet, just choose the first
    // (to make sure different packets don't choose different routes)
    // For unordered vnet, randomly choose any of the links
    // To have a strict ordering between links, they should be given
    // different weights in the topology file

    int output_link = -1;
    int min_weight = INFINITE_;
    std::vector<int> output_link_candidates;
    int num_candidates = 0;

    // Identify the minimum weight among the candidate output links
    for (int link = 0; link < m_routing_table[vnet].size(); link++) {
        if (msg_destination.intersectionIsNotEmpty(
            m_routing_table[vnet][link])) {

        if (m_weight_table[link] <= min_weight)
            min_weight = m_weight_table[link];
        }
    }

    // Collect all candidate output links with this minimum weight
    for (int link = 0; link < m_routing_table[vnet].size(); link++) {
        if (msg_destination.intersectionIsNotEmpty(
            m_routing_table[vnet][link])) {

            if (m_weight_table[link] == min_weight) {
                num_candidates++;
                output_link_candidates.push_back(link);
            }
        }
    }

    if (output_link_candidates.size() == 0) {
        fatal("Fatal Error:: No Route exists from this Router.");
        exit(0);
    }

    // Randomly select any candidate output link
    int candidate = 0;
    if (!(m_router->get_net_ptr())->isVNetOrdered(vnet))
        candidate = rand() % num_candidates;

    output_link = output_link_candidates.at(candidate);
    return output_link;
}


void
RoutingUnit::addInDirection(PortDirection inport_dirn, int inport_idx)
{
    m_inports_dirn2idx[inport_dirn] = inport_idx;
    m_inports_idx2dirn[inport_idx]  = inport_dirn;
}

void
RoutingUnit::addOutDirection(PortDirection outport_dirn, int outport_idx)
{
    m_outports_dirn2idx[outport_dirn] = outport_idx;
    m_outports_idx2dirn[outport_idx]  = outport_dirn;
}

// outportCompute() is called by the InputUnit
// It calls the routing table by default.
// A template for adaptive topology-specific routing algorithm
// implementations using port directions rather than a static routing
// table is provided here.

int
RoutingUnit::outportCompute(RouteInfo route, int inport,
                            PortDirection inport_dirn)
{
    int outport = -1;

    if (route.dest_router == m_router->get_id()) {

        // Multiple NIs may be connected to this router,
        // all with output port direction = "Local"
        // Get exact outport id from table
        outport = lookupRoutingTable(route.vnet, route.net_dest);
        return outport;
    }

    // Routing Algorithm set in GarnetNetwork.py
    // Can be over-ridden from command line using --routing-algorithm = 1
    RoutingAlgorithm routing_algorithm =
        (RoutingAlgorithm) m_router->get_net_ptr()->getRoutingAlgorithm();

    switch (routing_algorithm) {
        case TABLE_:  outport =
            lookupRoutingTable(route.vnet, route.net_dest); break;
        case XY_:     outport =
            outportComputeXY(route, inport, inport_dirn); break;
        // any custom algorithm
        case CUSTOM_: outport =
            outportComputeCustom(route, inport, inport_dirn); break;
        case RING_: outport =
            outportComputeRing(route, inport, inport_dirn); break;
        case XY_BYPASS_: outport =
            outportComputeXYBypass(route, inport, inport_dirn); break;
        case BIT_TREE_: outport =
            outportCompute2BitTree(route, inport, inport_dirn); break;
        case THREE_BIT_TREE_: outport =
            outportCompute3BitTree(route, inport, inport_dirn); break;
        default: outport =
            lookupRoutingTable(route.vnet, route.net_dest); break;
    }

    assert(outport != -1);
    return outport;
}

// XY routing implemented using port directions
// Only for reference purpose in a Mesh
// By default Garnet uses the routing table
int
RoutingUnit::outportComputeXY(RouteInfo route,
                              int inport,
                              PortDirection inport_dirn)
{
    PortDirection outport_dirn = "Unknown";

    [[maybe_unused]] int num_rows = m_router->get_net_ptr()->getNumRows();
    int num_cols = m_router->get_net_ptr()->getNumCols();
    assert(num_rows > 0 && num_cols > 0);

    int my_id = m_router->get_id();
    int my_x = my_id % num_cols;
    int my_y = my_id / num_cols;

    int dest_id = route.dest_router;
    int dest_x = dest_id % num_cols;
    int dest_y = dest_id / num_cols;

    int x_hops = abs(dest_x - my_x);
    int y_hops = abs(dest_y - my_y);

    bool x_dirn = (dest_x >= my_x);
    bool y_dirn = (dest_y >= my_y);

    // already checked that in outportCompute() function
    assert(!(x_hops == 0 && y_hops == 0));

    if (x_hops > 0) {
        if (x_dirn) {
            assert(inport_dirn == "Local" || inport_dirn == "West");
            outport_dirn = "East";
        } else {
            assert(inport_dirn == "Local" || inport_dirn == "East");
            outport_dirn = "West";
        }
    } else if (y_hops > 0) {
        if (y_dirn) {
            // "Local" or "South" or "West" or "East"
            assert(inport_dirn != "North");
            outport_dirn = "North";
        } else {
            // "Local" or "North" or "West" or "East"
            assert(inport_dirn != "South");
            outport_dirn = "South";
        }
    } else {
        // x_hops == 0 and y_hops == 0
        // this is not possible
        // already checked that in outportCompute() function
        panic("x_hops == y_hops == 0");
    }

    return m_outports_dirn2idx[outport_dirn];
}

// Template for implementing custom routing algorithm
// using port directions. (Example adaptive)
int
RoutingUnit::outportComputeCustom(RouteInfo route,
                                 int inport,
                                 PortDirection inport_dirn)
{
    panic("%s placeholder executed", __FUNCTION__);
}

int
RoutingUnit::outportComputeRing(RouteInfo route, int inport,
                                PortDirection inport_dirn)
{
    int src = m_router->get_id();
    int dest = route.dest_router;

    // 获取实际的路由器数量，而不是硬编码16
    int num_routers = m_router->get_net_ptr()->getNumRouters();

    // 计算顺时针和逆时针距离
    int clockwise_dist = (dest - src + num_routers) % num_routers;
    int counter_clockwise_dist = (src - dest + num_routers) % num_routers;

    // 选择较短路径
    if (clockwise_dist <= counter_clockwise_dist) {
        return m_outports_dirn2idx["East"];  // 顺时针
    } else {
        return m_outports_dirn2idx["West"];  // 逆时针
    }
}

int
RoutingUnit::outportComputeXYBypass(RouteInfo route,
                                   int inport,
                                   PortDirection inport_dirn)
{
    PortDirection outport_dirn = "Unknown";

    int num_rows = m_router->get_net_ptr()->getNumRows();
    int num_cols = m_router->get_net_ptr()->getNumCols();
    assert(num_rows > 0 && num_cols > 0);

    int my_id = m_router->get_id();
    int my_x = my_id % num_cols;
    int my_y = my_id / num_cols;

    int dest_id = route.dest_router;
    int dest_x = dest_id % num_cols;
    int dest_y = dest_id / num_cols;

    int x_hops = dest_x - my_x;
    int y_hops = dest_y - my_y;

    bool use_bypass = false;
    
    // 只要同方向且至少有1跳就采用对角线
    if (x_hops >= 1 && y_hops >= 1) {
        if (m_outports_dirn2idx.find("Southeast") != m_outports_dirn2idx.end()) {
            outport_dirn = "Southeast";
            use_bypass = true;
            DPRINTF(RubyNetwork, "Using Southeast bypass from router %d to %d (hops=%d,%d)\n", 
                    my_id, dest_id, x_hops, y_hops);
        }
    } else if (x_hops >= 1 && y_hops <= -1) {
        if (m_outports_dirn2idx.find("Northeast") != m_outports_dirn2idx.end()) {
            outport_dirn = "Northeast";
            use_bypass = true;
            DPRINTF(RubyNetwork, "Using Northeast bypass from router %d to %d (hops=%d,%d)\n", 
                    my_id, dest_id, x_hops, y_hops);
        }
    } else if (x_hops <= -1 && y_hops >= 1) {
        // 西南方向
        if (m_outports_dirn2idx.find("Southwest") != m_outports_dirn2idx.end()) {
            outport_dirn = "Southwest";
            use_bypass = true;
            DPRINTF(RubyNetwork, "Using Southwest bypass from router %d to %d (hops=%d,%d)\n", 
                    my_id, dest_id, x_hops, y_hops);
        }
    } else if (x_hops <= -1 && y_hops <= -1) {
        if (m_outports_dirn2idx.find("Northwest") != m_outports_dirn2idx.end()) {
            outport_dirn = "Northwest";
            use_bypass = true;
            DPRINTF(RubyNetwork, "Using Northwest bypass from router %d to %d (hops=%d,%d)\n", 
                    my_id, dest_id, x_hops, y_hops);
        }
    }
    
    // 不能使用bypass就用标准XY路由
    if (!use_bypass) {
        if (x_hops > 0) {
            outport_dirn = "East";
        } else if (x_hops < 0) {
            outport_dirn = "West";
        } else if (y_hops > 0) {
            outport_dirn = "South";
        } else if (y_hops < 0) {
            outport_dirn = "North";
        } else {
            outport_dirn = "Local";
        }
        
        DPRINTF(RubyNetwork, "Using standard XY routing: %s from router %d to %d\n",
                outport_dirn.c_str(), my_id, dest_id);
    }

    if (m_outports_dirn2idx.find(outport_dirn) == m_outports_dirn2idx.end()) {
        fatal("Output port direction %s not found in router %d\n", 
              outport_dirn.c_str(), my_id);
    }

    return m_outports_dirn2idx[outport_dirn];
}

int
RoutingUnit::outportCompute2BitTree(RouteInfo route,
                                   int inport,
                                   PortDirection inport_dirn)
{
    int num_routers = m_router->get_net_ptr()->getNumRouters();
    int n = (int)ceil(log2(num_routers)); // 确定需要的位数
    
    int my_id = m_router->get_id();
    int dest_id = route.dest_router;
    
    // 如果目标就是当前路由器，使用Local端口
    if (dest_id == my_id) {
        return m_outports_dirn2idx["Local"];
    }
    
    // 计算当前路由器与目标路由器的差值
    int diff = (dest_id - my_id + num_routers) % num_routers;
    
    // 查找差值中最高位的1
    for (int t = n-1; t >= 0; t--) {
        int bit_mask = 1 << t;
        if (diff & bit_mask) {
            // 找到置位的最高位，尝试使用对应的链接
            // 构造与TwoBitTree.py中相同格式的端口名称
            std::string port_name = "Bit_" + std::to_string(t) + "_" + 
                                    std::to_string(my_id) + "_" + 
                                    std::to_string((my_id + bit_mask) % num_routers);
            
            // 检查是否有此端口
            if (m_outports_dirn2idx.find(port_name) != m_outports_dirn2idx.end()) {
                return m_outports_dirn2idx[port_name];
            }
            
            // 如果没有直接链接，考虑其他可能的路径
            for (int other_router = 0; other_router < num_routers; other_router++) {
                port_name = "Bit_" + std::to_string(t) + "_" + 
                            std::to_string(my_id) + "_" + 
                            std::to_string(other_router);
                if (m_outports_dirn2idx.find(port_name) != m_outports_dirn2idx.end()) {
                    return m_outports_dirn2idx[port_name];
                }
            }
        }
    }
    
    // 如果无法确定输出端口，使用查表路由
    DPRINTF(RubyNetwork, "Could not determine BitTree port, falling back to table lookup\n");
    return lookupRoutingTable(route.vnet, route.net_dest);
}

// 添加3BitTree路由算法实现

int
RoutingUnit::outportCompute3BitTree(RouteInfo route,
                                   int inport,
                                   PortDirection inport_dirn)
{
    int num_routers = m_router->get_net_ptr()->getNumRouters();
    int n = (int)ceil(log(num_routers) / log(3)); // 确定3进制需要的位数
    
    int my_id = m_router->get_id();
    int dest_id = route.dest_router;
    
    // 如果目标就是当前路由器，使用Local端口
    if (dest_id == my_id) {
        return m_outports_dirn2idx["Local"];
    }
    
    // 计算当前路由器与目标路由器的距离
    int diff = (dest_id - my_id + num_routers) % num_routers;
    
    // 计算3进制表示，找到最佳路径
    for (int t = n-1; t >= 0; t--) {
        int power_3t = (int)pow(3, t);
        
        // 计算余数 (0, 1, 2)
        int remainder = diff / power_3t % 3;
        
        if (remainder == 1) {
            // 需要加上 3^t，使用正向链接
            std::string port_name = "Tri_" + std::to_string(t) + "_" + 
                                    std::to_string(my_id) + "_" + 
                                    std::to_string((my_id + power_3t) % num_routers);
            
            if (m_outports_dirn2idx.find(port_name) != m_outports_dirn2idx.end()) {
                return m_outports_dirn2idx[port_name];
            }
        } 
        else if (remainder == 2) {
            // 需要加上 2*3^t，使用负向链接
            std::string port_name = "TriNeg_" + std::to_string(t) + "_" + 
                                    std::to_string(my_id) + "_" + 
                                    std::to_string((my_id + 2 * power_3t) % num_routers);
            
            if (m_outports_dirn2idx.find(port_name) != m_outports_dirn2idx.end()) {
                return m_outports_dirn2idx[port_name];
            }
        }
    }
    
    // 如果无法通过3BitTree路由找到路径，尝试查找任何可能的连接
    for (int t = n-1; t >= 0; t--) {
        for (int other_router = 0; other_router < num_routers; other_router++) {
            // 尝试正向链接
            std::string port_name = "Tri_" + std::to_string(t) + "_" + 
                                    std::to_string(my_id) + "_" + 
                                    std::to_string(other_router);
            if (m_outports_dirn2idx.find(port_name) != m_outports_dirn2idx.end()) {
                return m_outports_dirn2idx[port_name];
            }
            
            // 尝试负向链接
            port_name = "TriNeg_" + std::to_string(t) + "_" + 
                        std::to_string(my_id) + "_" + 
                        std::to_string(other_router);
            if (m_outports_dirn2idx.find(port_name) != m_outports_dirn2idx.end()) {
                return m_outports_dirn2idx[port_name];
            }
        }
    }
    
    // 如果仍然无法找到路径，使用查表路由
    DPRINTF(RubyNetwork, "Could not determine ThreeBitTree port, falling back to table lookup\n");
    return lookupRoutingTable(route.vnet, route.net_dest);
}

} // namespace garnet
} // namespace ruby
} // namespace gem5
