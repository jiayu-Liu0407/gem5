/*
 * Copyright (c) 2020 Inria
 * Copyright (c) 2016 Georgia Institute of Technology
 * Copyright (c) 2008 Princeton University
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


#include "mem/ruby/network/garnet/CrossbarSwitch.hh"

#include "debug/RubyNetwork.hh"
#include "mem/ruby/network/garnet/OutputUnit.hh"
#include "mem/ruby/network/garnet/Router.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

CrossbarSwitch::CrossbarSwitch(Router *router)
  : Consumer(router), m_router(router), m_num_vcs(m_router->get_num_vcs()),
    m_crossbar_activity(0), switchBuffers(0)
{
}

void
CrossbarSwitch::init()
{
    switchBuffers.resize(m_router->get_num_inports());
}

/*
 * The wakeup function of the CrossbarSwitch loops through all input ports,
 * and sends the winning flit (from SA) out of its output port on to the
 * output link. The output link is scheduled for wakeup in the next cycle.
 */

void
CrossbarSwitch::wakeup()
{
    DPRINTF(RubyNetwork, "CrossbarSwitch at Router %d woke up "
            "at time: %lld\n",
            m_router->get_id(), m_router->curCycle());

    for (auto& switch_buffer : switchBuffers) {
        if (!switch_buffer.isReady(curTick())) {
            continue;
        }

        flit *t_flit = switch_buffer.peekTopFlit();
        if (t_flit->is_stage(ST_, curTick())) {
            int outport = t_flit->get_outport();
            int outvc = t_flit->get_vc();
            // 🔥 关键添加：虫洞模式下在ST阶段消耗credit
            bool is_wormhole = m_router->get_net_ptr()->isWormholeEnabled();
            if (is_wormhole) {
                auto output_unit = m_router->getOutputUnit(outport);

                // 🔥 时效性检查：如果SA决策太旧，重新验证credit
                Tick current_time = curTick();
                Tick sa_time = t_flit->get_sa_timestamp();

                if (current_time - sa_time > 2) {
                    // SA决策超过2个周期，重新检查credit可用性
                    if (!output_unit->has_credit(outvc)) {
                        // Credit不可用，重新调度到SA阶段
                        DPRINTF(RubyNetwork,
                                "Router[%d]: Credit stale for VC %d, "
                                "rescheduling to SA\n",
                                m_router->get_id(), outvc);
                        t_flit->advance_stage(SA_,
                            m_router->clockEdge(Cycles(1)));
                        continue;
                    }
                }

                // 🔥 安全的credit消耗
                if (output_unit->can_safely_decrement_credit(outvc)) {
                    output_unit->decrement_credit(outvc);
                } else {
                    // Credit不足，重新调度到SA阶段而不是panic
                    DPRINTF(RubyNetwork,
                            "Router[%d]: Insufficient credit for VC %d, "
                            "rescheduling to SA\n",
                            m_router->get_id(), outvc);
                    t_flit->advance_stage(SA_, m_router->clockEdge(Cycles(1)));
                    continue;
                }
            }
            // 普通模式下credit已经在SA阶段消耗了，这里不需要处理

            // flit performs LT_ in the next cycle
            t_flit->advance_stage(LT_, m_router->clockEdge(Cycles(1)));
            t_flit->set_time(m_router->clockEdge(Cycles(1)));

            // This will take care of waking up the Network Link
            // in the next cycle
            m_router->getOutputUnit(outport)->insert_flit(t_flit);
            switch_buffer.getTopFlit();
            m_crossbar_activity++;
        }
    }
}

bool
CrossbarSwitch::functionalRead(Packet *pkt, WriteMask &mask)
{
    bool read = false;
    for (auto& switch_buffer : switchBuffers) {
        if (switch_buffer.functionalRead(pkt, mask))
            read = true;
   }
   return read;
}

uint32_t
CrossbarSwitch::functionalWrite(Packet *pkt)
{
   uint32_t num_functional_writes = 0;

   for (auto& switch_buffer : switchBuffers) {
       num_functional_writes += switch_buffer.functionalWrite(pkt);
   }

   return num_functional_writes;
}

void
CrossbarSwitch::resetStats()
{
    m_crossbar_activity = 0;
}

} // namespace garnet
} // namespace ruby
} // namespace gem5
