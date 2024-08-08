from quantum_bell_api.decoherence import depolarize_rate
from quantum_bell_api.swapping import swap
from quantum_bell_api.utility import epr_pair, get_werner_state
from omnetpypy import SimpleModule, sim_log, Message
import qnum_congestion_ctrl_aqm_bidir.messages as messages
from qnum_congestion_ctrl_aqm_bidir.aqm_controller import PIController
from qnum_congestion_ctrl_aqm_bidir.congestion_controller import WindowCongestionController, \
    RateCongestionController
from qnum_congestion_ctrl_aqm_bidir.queues import RequestQueue, LLEManager
from qnum_congestion_ctrl_aqm_bidir.request_generator import RequestGenerator
from qnum_congestion_ctrl_aqm_bidir.utility import sanitize_flow_descriptors


class QuantumNode(SimpleModule):
    """
    This class models a Quantum Repeater along a repeater chain

    Parameters
    ----------
    name : str
        The name of the module
    identifier : int
        The identifier of the module
    storage_qbits_per_port : int or None, optional
        The number of  storage qubits available on each port. If None, the module will assume an infinite storage
        capacity. Default is None.
    """

    TIMEOUT_TRIGGER_MSG_HEADER = "timeout control trigger"
    # self messages to trigger the timeout control of requests in flight

    NEW_FLOW_TRIGGER_MSG_HEADER = "new flow trigger"
    # self messages to trigger the generation of new flows. Not used in this version

    NEW_TOKEN_MSG_HEADER = "new token"
    # self messages to trigger the generation of new tokens. The only field of the message is the flow_id

    INITIALIZE_REQUESTS_MSG_HEADER = "initialize requests"
    # self messages to trigger the generation of the first requests for each flow

    NEW_REQUEST_TRIGGER_MSG_HEADER = "new requests trigger"
    # self messages to trigger the generation of a new request. The only field of the message is the flow_id

    FLOW_KNOB_INCREMENT_MSG_HEADER = "increase flow rate trigger"
    # self message to trigger the increase of the congestion knob. The only field of the message is the flow_id

    AQM_UPDATE_TRIGGER_MSG_HEADER = "update AQM"
    # self message to trigger the update of the AQM controller. The only field of the message is the direction:
    # "upstream" or "downstream"


    def __init__(self, name, identifier, storage_qbits_per_port=None, decoherence_rate=0.):

        port_names = ["q0", "q1"]
        # first dilemma: do we use separate channels for classical packets  (c0, c1 ports) ?
        # rg0 is used to attach the RequestGenerator

        super().__init__(name, identifier, port_names)
        self.flows_info = None
        self.lle_manager = LLEManager(port_names=["q0", "q1"])
        self.req_queue = RequestQueue()
        self.storage_qbits_per_port = storage_qbits_per_port
        self.decoherence_rate = decoherence_rate

        ################################
        # POISSON REQUESTS GEN PARAMS  #
        ################################
        self.rates_increased = False
        ################################
        # END POISSON REQUESTS GEN PA  #
        ################################

        ################################
        # CONGESTION CONTROL VARIABLES #
        ################################
        self.congestion_controller = RateCongestionController()

        self.cur_req_ids = {}  # dictionary of current request ids, one for each flow, indexed by flow_id, used to
        # keep track of which id assign to the next generated request for each flow

        self.tokens = {}  # dictionary of tokens, one for each flow, indexed by flow_id, used to keep track of the
        """number of tokens available for each flow. The tokens are used to limit the number of requests
        in the network"""

        self.request_admittance_queues = {}
        """dictionary of request admittance queues, one for each flow, indexed by
        flow_id, used to keep track of the requests that are waiting to be admitted in the network"""

        self.admittance_queues_max_size = 1000
        """maximum size of the request admittance queues"""

        self.request_generators = {}
        """dictionary of request generators, one for each flow, indexed by flow_id, used to
        generate requests for each flow"""

        self.timeout_trigger_msg = Message(["timeout control trigger"], header=self.TIMEOUT_TRIGGER_MSG_HEADER)
        self.timeout_trigger_period = 20000  # us
        self.last_update_time = 0
        ################################
        # END OF CONGESTION CONTROL    #
        ################################

        ################################
        # ACTIVE QUEUE MGMT VARIABLES  #
        ################################
        self.aqm_controllers = None
        self.AQM_T_sampling_times = None
        self.AQM_update_msgs = None
        ################################
        # END OF AQM VARIABLES         #
        ################################

        ################################
        # NEW FLOW GENERATION          #
        ################################
        self.new_flow_trigger_msg = Message(["new flow trigger"], header=self.NEW_FLOW_TRIGGER_MSG_HEADER)
        self.new_flow_trigger_period = 8000000  # us
        self.delete_phase = False
        ################################
        # END OF NEW FLOW GENERATION    #
        ################################

        ################################
        # NEW REQUEST GENERATION       #
        ################################
        self.new_request_trigger_msgs = {}
        self.increase_request_rate_trigger_msgs = {}
        ################################
        # END OF NEW REQUEST GENERATION #
        ################################

    def initialize(self, step=0):
        if step == 0:
            # usually you can retrieve parameters by looking at self.parent attributes (parent is the compound module
            # containing this module)

            # access global parameters and get the flows information
            flow_descriptors = self.sim_context.global_params["flow_descriptors"]
            flow_descriptors = sanitize_flow_descriptors(flow_descriptors)
            # dict of flow descriptors, indexed by flow_id, each one containing the following fields (for now):
            # - flow_id
            # - source
            # - destination
            # - path (list of node names, including source and destination)
            # - success_probs (list of success probabilities for each link in the path)
            # - direction (upstream or downstream)
            # - request_rate (average, Poisson process)

            message = messages.FlowsInformationPacket(destination=self.name, flows=flow_descriptors)
            self._handle_flows_information(message)

            self.schedule_message(self.timeout_trigger_msg, delay=self.timeout_trigger_period)

            self.aqm_controllers = {
                "upstream": PIController(),
                "downstream": PIController()
            }
            aqm_params = self.sim_context.global_params["aqm_params"]
            self.AQM_T_sampling_times = {
                "upstream": (self.aqm_controllers["upstream"].set_parameters(**aqm_params))*self.sim_context.time_unit_factor,
                "downstream": (self.aqm_controllers["downstream"].set_parameters(**aqm_params))*self.sim_context.time_unit_factor
            }
            self.AQM_update_msgs = {
                "upstream": Message(["downstream"], header=self.AQM_UPDATE_TRIGGER_MSG_HEADER),
                "downstream": Message(["upstream"], header=self.AQM_UPDATE_TRIGGER_MSG_HEADER)
            }

            for direction in ["upstream", "downstream"]:
                self._schedule_aqm_update(direction)

            self.schedule_message(self.new_flow_trigger_msg, delay=self.new_flow_trigger_period)

    def _schedule_aqm_update(self, direction):
        """
        Schedule the next AQM update for the given direction
        """
        self.schedule_message(self.AQM_update_msgs[direction], delay=self.AQM_T_sampling_times[direction])

    def _get_success_prob(self, request, direction):
        """
        Get the success probability for the request to be forwarded on the given port
        """
        # get this node's position in the path
        path = self.flows_info[request.flow_id]["path"]
        # Remove elements at even indices
        path_no_link_controllers = [path[i] for i in range(len(path)) if i % 2 == 0]
        idx = path_no_link_controllers.index(self.name)
        if direction == "downstream":
            # we are going downstream
            return self.flows_info[request.flow_id]["success_probs"][idx - 1]
        elif direction == "upstream":
            # we are going upstream
            return self.flows_info[request.flow_id]["success_probs"][idx]
        else:
            raise ValueError(f"Unknown direction: {direction}")


    def handle_message(self, message, port_name):

        if isinstance(message, messages.FlowsInformationPacket) and message.destination == self.name:
            self._handle_flows_information(message)
            return

        if isinstance(message, messages.FlowDeletionPacket) and message.destination == self.name:
            self._handle_flow_deletion(message)
            return

        if "header" in message.meta and message.meta["header"] == self.INITIALIZE_REQUESTS_MSG_HEADER:
            # we generate the first requests for each flow for which we are the source or the destination
            for flow_id in self.flows_info:
                if self.name == self.flows_info[flow_id]["source"] or self.name == self.flows_info[flow_id]["destination"]:
                    if not isinstance(self.congestion_controller, RateCongestionController):
                        # create the first token
                        self._handle_new_token(flow_id=flow_id)
                    else:
                        # schedule the first token generation
                        self.schedule_message(Message([flow_id], header=self.NEW_TOKEN_MSG_HEADER),
                                              delay=self.congestion_controller.get_inter_request_gap(flow_id=flow_id))
                        # schedule the next increase in the flow rate
                        self.schedule_message(self.increase_request_rate_trigger_msgs[flow_id],
                                              delay=self.congestion_controller.estimated_rtt[flow_id])

                        # schedule the first request generation
                        self.schedule_message(self.new_request_trigger_msgs[flow_id],
                                              delay=self.request_generators[flow_id].next_request_gap())

            return

        if "header" in message.meta and message.meta["header"] == self.NEW_FLOW_TRIGGER_MSG_HEADER:
            """self._generate_new_flow()
            self.schedule_message(self.new_flow_trigger_msg, delay=self.new_flow_trigger_period)"""
            return

        if "header" in message.meta and message.meta["header"] == self.NEW_REQUEST_TRIGGER_MSG_HEADER:

            if message.fields[0] not in self.flows_info:
                # the flow has been deleted
                del self.new_request_trigger_msgs[message.fields[0]]
                return

            request_pkt = self.generate_request(flow_id=message.fields[0])
            self.fire_request_with_token(request_pkt)

            # check the increase_at parameter
            if not self.rates_increased:
                increase_at = self.sim_context.global_params["request_generation"]["increase_at"]
                increase_by = self.sim_context.global_params["request_generation"]["increase_by"]

                if increase_at <= self.sim_context.time():
                    for flow_idx in self.request_generators:
                        old_rate = self.request_generators[flow_idx].arrival_rate

                        self.request_generators[flow_idx] = RequestGenerator(arrival_rate=old_rate + increase_by,
                                                                            rng=self.sim_context.rng,
                                                                            rng_index=flow_idx)
                        self.rates_increased = True

            delay = self.request_generators[message.fields[0]].next_request_gap()

            # check if the admittance queue is full
            if message.fields[0] in self.request_admittance_queues and len(self.request_admittance_queues[message.fields[0]]) > 0:
                # in this case we increase the delay to the next request generation
                flow_arrival_rate = self.flows_info[message.fields[0]]["request_rate"]
                flow_avg_inter_request_gap = self.sim_context.time_unit_factor / flow_arrival_rate
                delay += 10 * flow_avg_inter_request_gap

            self.schedule_message(message, delay=delay)
            return

        if "header" in message.meta and message.meta["header"] == self.FLOW_KNOB_INCREMENT_MSG_HEADER:
            if not isinstance(self.congestion_controller, RateCongestionController):
                raise ValueError("The global rate increase period is set but the congestion controller"
                                 "is not a RateCongestionController")

            if message.fields[0] not in self.flows_info:
                # the flow has been deleted
                del self.increase_request_rate_trigger_msgs[message.fields[0]]
                return

            flow_id = message.fields[0]
            self.congestion_controller.increase_congestion_knob(flow_id=message.fields[0],
                                                                current_time=self.sim_context.time())
            # get estimated rtt
            rtt = self.congestion_controller.estimated_rtt[flow_id]
            # schedule the next increase for the estimated rtt

            self.schedule_message(message, delay=rtt)
            return

        if port_name is None and message.meta["header"] == self.AQM_UPDATE_TRIGGER_MSG_HEADER:
            direction = message.fields[0]
            out_port = "q0" if direction == "downstream" else "q1"
            current_q_len = self.req_queue.weighted_length(out_port=out_port)
            self.aqm_controllers[direction].update(q=current_q_len)
            self._schedule_aqm_update(direction)
            return

        if port_name is None and message.meta["header"] == self.NEW_TOKEN_MSG_HEADER:
            self._handle_new_token(flow_id=message.fields[0])
            return

        if isinstance(message, messages.RoutablePacket) and message.destination != self.name:
            # if this is not the destination, forward the packet on the other port
            self.send(message, "q1" if port_name == "q0" else "q0")
            return

        if isinstance(message, messages.EntanglementRequestPacket):
            self._handle_entanglement_request(message, port_name)
            return

        if isinstance(message, messages.EntanglementGenPacket):
            self._handle_new_lle(message, port_name)
            return

        if isinstance(message, messages.EntanglementGenAcknowledgement):
            self._handle_req_ack(message, port_name)
            return

        if "header" in message.meta and message.meta["header"] == self.TIMEOUT_TRIGGER_MSG_HEADER:
            self.collect_timeouts()
            return

        else:
            raise ValueError(f"Unknown message received: {message} at node {self.name}")

    def _handle_flows_information(self, message):
        """
        This method is called when a FlowsInformationPacket is received
        """
        # among all flows, we only keep those that are relevant to this node
        # (i.e. the flows where the current node is part of the path)
        relevant_flows = {}
        for flow in message.flows:
            if self.name in flow["path"]:
                relevant_flows[flow["flow_id"]] = flow

        flow_info = {}
        for flow_id in relevant_flows:
            flow = relevant_flows[flow_id]
            next_port = {"downstream": "q0", "upstream": "q1"}
            arrival_rate = flow["request_rate"]
            if self.name == flow["source"]:
                self.congestion_controller.setup_congestion_control(flow, current_time=self.sim_context.time())
                self.cur_req_ids[flow_id] = 0
                self.new_request_trigger_msgs[flow_id] = Message([flow_id],
                                                                 header=self.NEW_REQUEST_TRIGGER_MSG_HEADER)
                self.increase_request_rate_trigger_msgs[flow_id] = Message([flow_id],
                                                                           header=self.FLOW_KNOB_INCREMENT_MSG_HEADER)

                self.request_generators[flow_id] = RequestGenerator(arrival_rate=arrival_rate, rng=self.sim_context.rng,
                                                                    rng_index=flow_id)

                # initialize the token counter and the request admittance queue
                self.tokens[flow_id] = 0
                self.request_admittance_queues[flow_id] = []

            if self.name == flow["destination"]:
                self.congestion_controller.setup_congestion_control(flow, current_time=self.sim_context.time(),
                                                                    is_source=False)
                self.cur_req_ids[flow_id] = 1000000
                self.new_request_trigger_msgs[flow_id] = Message([flow_id],
                                                                 header=self.NEW_REQUEST_TRIGGER_MSG_HEADER)
                self.increase_request_rate_trigger_msgs[flow_id] = Message([flow_id],
                                                                           header=self.FLOW_KNOB_INCREMENT_MSG_HEADER)
                # add a request generator for the flow
                self.request_generators[flow_id] = RequestGenerator(arrival_rate=arrival_rate, rng=self.sim_context.rng,
                                                                    rng_index=flow_id)

                # initialize the token counter and the request admittance queue
                self.tokens[flow_id] = 0
                self.request_admittance_queues[flow_id] = []


            if self.name != flow["destination"]:
                next_hop_up = flow["path"][flow["path"].index(self.name) + 2]
            else:
                next_hop_up = None
            if self.name != flow["source"]:
                next_hop_down = flow["path"][flow["path"].index(self.name) - 2]
            else:
                next_hop_down = None
            # next hop in the path, +2 because the path includes the link controllers

            flow_info[flow_id] = {
                "next_port": next_port,
                "source": flow["source"],
                "destination": flow["destination"],
                "next_hop_down": next_hop_down,
                "next_hop_up": next_hop_up,
                "success_probs": flow["success_probs"],
                "path": flow["path"],
                "request_rate": flow["request_rate"]
            }

        was_init = False
        if self.flows_info is None:
            self.flows_info = flow_info
            was_init = True
        else:
            self.flows_info.update(flow_info)

        sim_log.debug(f"{self.name} received flows information with {len(relevant_flows)} relevant flows.",
                      time=self.sim_context.time())

        # we generate the first requests for each flow for which we are the source or the destination
        # but we wait for a little time to let the other nodes initialize
        if was_init:
            self.schedule_message(Message(["initialize requests"], header=self.INITIALIZE_REQUESTS_MSG_HEADER),
                                  delay=10)
        else:
            for flow_id in flow_info:
                if self.name == flow_info[flow_id]["source"] or self.name == flow_info[flow_id]["destination"]:
                    if not isinstance(self.congestion_controller, RateCongestionController):
                        # create the first token
                        self._handle_new_token(flow_id=flow_id)
                    else:
                        # schedule the first token generation
                        self.schedule_message(Message([flow_id], header=self.NEW_TOKEN_MSG_HEADER),
                                              delay=self.congestion_controller.get_inter_request_gap(flow_id=flow_id))
                        # schedule the next increase in the flow rate
                        self.schedule_message(self.increase_request_rate_trigger_msgs[flow_id],
                                              delay=self.congestion_controller.estimated_rtt[flow_id])

                        # schedule the first request generation
                        self.schedule_message(self.new_request_trigger_msgs[flow_id],
                                              delay=self.request_generators[flow_id].next_request_gap())

    def _handle_new_token(self, flow_id):
        """
        Handle the generation of a new token for the given flow_id
        """
        """if flow_id not in self.tokens:
            # the flow has been deleted
            sim_log.warning(f"Flow {flow_id} not found at node {self.name}", time=self.sim_context.time())
            return

        # check if there are requests in the admittance queue
        if flow_id in self.request_admittance_queues and len(self.request_admittance_queues[flow_id]) > 0:
            # pop the request from the queue
            request = self.request_admittance_queues[flow_id].pop(0)
            # fire the request
            self.fire_request(request)
        else:
            # generate a new token
            self.tokens[flow_id] += 1

        # schedule the next token generation using the congestion controller if it is a RateCongestionController
        if isinstance(self.congestion_controller, RateCongestionController):
            gap = self.congestion_controller.get_inter_request_gap(flow_id=flow_id)
            self.schedule_message(Message([flow_id], header=self.NEW_TOKEN_MSG_HEADER), delay=gap)"""
        self.tokens[flow_id] = 1000000


    def _handle_flow_deletion(self, message):
        """
        This method is called when a FlowDeletionPacket is received
        """
        flow_id = message.flow_id
        if flow_id in self.flows_info:

            # if we are the source of the flow, we have to delete the flow from the congestion controller
            # and cancel the scheduled messages
            if self.name == self.flows_info[flow_id]["source"] or self.name == self.flows_info[flow_id]["destination"]:
                self.congestion_controller.delete_flow(flow_id)

            # delete all requests in the queue for the flow and all the LLEs
            self.req_queue.delete_requests(flow_id)
            self.lle_manager.delete_lles(flow_id)

            # delete the flow information
            del self.flows_info[flow_id]
            del self.tokens[flow_id]
            del self.request_generators[flow_id]
            sim_log.debug(f"Flow {flow_id} deleted at node {self.name}", time=self.sim_context.time())
        else:
            sim_log.error(f"Flow {flow_id} not found at node {self.name}", time=self.sim_context.time())
            raise ValueError(f"Flow {flow_id} not found at node {self.name}")

    def generate_request(self, flow_id):
        """
        Generate a request for the given flow_id
        """
        # generate a new request
        req_id = self.cur_req_ids[flow_id]
        self.cur_req_ids[flow_id] += 1

        # determine the direction and the next hop destination depending on whether we are the source or the destination
        if self.name == self.flows_info[flow_id]["source"]:
            direction = "upstream"
            destination = self.flows_info[flow_id]["next_hop_up"]
        else:
            direction = "downstream"
            destination = self.flows_info[flow_id]["next_hop_down"]

        request_pkt = messages.EntanglementRequestPacket(destination=destination, flow_id=flow_id, req_id=req_id,
                                                         lle_id=None, gen_time=self.sim_context.time())

        # set the success probabilities as a meta field
        request_pkt.meta["success_probs"] = self.flows_info[flow_id]["success_probs"][:]
        request_pkt.meta["direction"] = direction

        return request_pkt

    def fire_request(self, request_pkt):

        flow_id = request_pkt.flow_id
        req_id = request_pkt.req_id

        # set the generation time to the admission time
        request_pkt.gen_time = self.sim_context.time()

        # send the request to ourselves
        self._handle_new_request(request_pkt)

        # let the congestion controller know that a new request has been generated
        self.congestion_controller.handle_new_request_in_flight(req_id=req_id, flow_id=flow_id,
                                                                current_time=self.sim_context.time())

    def fire_request_with_token(self, request_pkt):

        if request_pkt.flow_id not in self.tokens:
            # the flow has been deleted
            sim_log.warning(f"Flow {request_pkt.flow_id} not found at node {self.name}",
                            time=self.sim_context.time())
            return

        if self.tokens[request_pkt.flow_id] > 0:
            self.tokens[request_pkt.flow_id] -= 1
            self.fire_request(request_pkt)
        else:
            # put the request in the admittance queue
            # if it is full, drop the request
            if request_pkt.flow_id not in self.request_admittance_queues:
                self.request_admittance_queues[request_pkt.flow_id] = []
            if len(self.request_admittance_queues[request_pkt.flow_id]) < self.admittance_queues_max_size:
                self.request_admittance_queues[request_pkt.flow_id].append(request_pkt)
            else:
                sim_log.warning(f"Admittance queue for flow {request_pkt.flow_id} is full. Request dropped.",
                                time=self.sim_context.time())

    def collect_timeouts(self):
        """
        Collect the timeouts for the requests in flight and update the congestion windows for the involved flows
        """
        self.congestion_controller.collect_timeouts(self.sim_context.time())
        self.schedule_message(self.timeout_trigger_msg, delay=self.timeout_trigger_period)

        if self.last_update_time + 20000 <= self.sim_context.time():
            self.last_update_time = self.sim_context.time()
            # log some simulation updates for the user
            sim_log.debug(f"Node {self.name} has currently {len(self.req_queue)} requests in queue and"
                          f"{len(self.lle_manager)} LLEs",
                          time=self.sim_context.time())
            # for all flows of which we are the source, we log the current generation probability
            for flow_id in self.flows_info:
                if self.name == self.flows_info[flow_id]["source"] and isinstance(self.congestion_controller,
                                                                                  RateCongestionController):
                    p_gen = self.congestion_controller.get_inter_request_gap(flow_id=flow_id)
                    sim_log.debug(f"Node {self.name} has an IRG = {p_gen} us for flow {flow_id}",
                                  time=self.sim_context.time())
                if self.name == self.flows_info[flow_id]["destination"] and isinstance(self.congestion_controller,
                                                                                       RateCongestionController):
                    p_gen = self.congestion_controller.get_inter_request_gap(flow_id=flow_id)
                    sim_log.debug(f"Node {self.name} has an IRG = {p_gen} us for flow {flow_id}",
                                  time=self.sim_context.time())

    def _generate_new_flow(self, num_flows=3):
        """
        Generate a new flow by copying the first one of which this node is the source
        """
        # if total number of flows is equal or greater than 13,
        # we delete the last num_flows flows for which we are the source
        if len(self.flows_info) >= 13:
            self.delete_phase = True

        if len(self.flows_info) == 4 and self.delete_phase:
            self.delete_phase = False

        if self.delete_phase:
            flow_ids = list(self.flows_info.keys())
            # sort the flow_ids in descending order
            flow_ids.sort(reverse=True)
            to_delete = num_flows
            for f_id in flow_ids:
                if self.name == self.flows_info[f_id]["source"] and to_delete > 0:
                    # delete flow message
                    flow = self.flows_info[f_id]
                    for destination in flow["path"]:
                        del_flow_info = messages.FlowDeletionPacket(destination=destination, flow_id=f_id)
                        if destination == self.name:
                            self._handle_flow_deletion(del_flow_info)
                            continue
                        if flow["direction"] == "upstream":
                            self.send(del_flow_info, port_name="q1")
                        else:
                            self.send(del_flow_info, port_name="q0")
                    to_delete -= 1
            return


        # we just copy the first flow for which we are the source
        flow_id = None
        for f_id in self.flows_info:
            if self.name == self.flows_info[f_id]["source"]:
                flow_id = f_id
                break

        if flow_id is None:
            return

        flow = self.flows_info[flow_id]

        for _ in range(num_flows):
            new_flow = flow.copy()
            if new_flow["direction"] == "upstream":
                new_flow["flow_id"] = len(self.flows_info)
            else:
                new_flow["flow_id"] = len(self.flows_info) + num_flows
            self.flows_info[new_flow["flow_id"]] = new_flow

            # send the new flow information to the other nodes
            for destination in new_flow["path"]:
                new_flow_info = messages.FlowsInformationPacket(destination=destination, flows=[new_flow])

                if destination == self.name:
                    self._handle_flows_information(new_flow_info)
                    continue

                # it will be routed to the destination node
                if new_flow["direction"] == "upstream":
                    self.send(new_flow_info, port_name="q1")
                else:
                    self.send(new_flow_info, port_name="q0")

            sim_log.debug(f"Node {self.name} generated a new flow {new_flow['flow_id']}",
                          time=self.sim_context.time())

    def _handle_entanglement_request(self, message, port_name):
        """
        This method is called when an EntanglementRequestPacket is received
        """

        flow_id = message.flow_id

        assert flow_id in self.flows_info, f"Flow {flow_id} not found in the flows information"
        # assert port_name != self.flows_info[flow_id]["next_port"], "Received a request from the wrong port"

        """
        sim_log.debug(f"Request {message.req_id} received for flow {flow_id}. Here is node {self.name}",
                      time=self.sim_context.time())
        """

        # first of all we pop the first success probability from the request meta because it won't be used anymore
        message.meta["success_probs"].pop(0)

        # first thing: check whether the request's LLE is still available, it might have been dropped due to storage
        # qubit shortage
        lle, lle_time = self.lle_manager.peek_from_req(request=message, raise_error=False)
        if lle is None:
            # the lle has been dropped because of storage qubit shortage. We have to drop the request
            return

        # emit the queue size metric
        if self.name == "qn2":
            self.emit_metric("queue_size", self.req_queue.weighted_length(out_port="downstream"))

        elif self.name == "qn3":
            self.emit_metric("queue_size_free", self.req_queue.weighted_length(out_port="downstream"))

        direction = message.meta["direction"]

        # now let's check whether we should mark the request as congested
        if not message.is_congested():
            aqm = self.aqm_controllers[direction]
            marking_prob = aqm.get_marking_probability()
            random_number = self.sim_context.rng.random(generator=flow_id)
            # use the i-th random number generator offered by the sim_context
            # to check whether the request should be marked as congested
            if random_number < marking_prob:
                message.mark_congested()


        if ((direction == "upstream" and self.name == self.flows_info[flow_id]["destination"]) or
                (direction == "downstream" and self.name == self.flows_info[flow_id]["source"])):
            # we are the destination, we are done :)
            # pop the lle the request refers to from the available lles and emit 1
            lle, lle_time = self.lle_manager.pop_from_req(request=message, raise_error=True)

            """sim_log.warning(f"Request {message.req_id} satisfied for flow {flow_id}. Here is node {self.name}",
                          time=self.sim_context.time())"""

            # get the wait time of the lle
            wait_time = self.sim_context.time() - lle_time
            # decohere the state
            self._decohere_state(message, wait_time, get_werner_state(fidelity=1.))

            # generate and send the acknowledgement
            destination = self.flows_info[flow_id]["source"] if direction == "upstream" else self.flows_info[flow_id]["destination"]
            ack = messages.EntanglementGenAcknowledgement(req_id=message.req_id, flow_id=flow_id,
                                                          destination=destination,
                                                          congested=message.is_congested(),
                                                          gen_time=message.gen_time,
                                                          qstate=message.meta["qstate"],
                                                          ack_time=self.sim_context.time())
            self.send(ack, port_name=port_name)

            """
            sim_log.debug(f"Request {message.req_id} satisfied for flow {flow_id}. Here is node {self.name}",
                          time=self.sim_context.time())
            """

            self.emit_metric("rendezvous_node", int(self.name[2:]))

            return


        # Now, we check whether there is another request in the queue for the same flow in the opposite direction
        # if so, we swap the two requests
        """
        other_direction = "upstream" if direction == "downstream" else "downstream"
        other_port = "q0" if port_name == "q1" else "q1"
        other_request, _ = self.req_queue.pop_request(flow_id=flow_id, out_port=port_name, policy=RequestQueue.OLDEST)
        if other_request is not None:
            # there is a request in the queue for the same flow in the opposite direction
            # we swap the two requests

            # we pop the lle for the other request
            other_lle, other_lle_time = self.lle_manager.pop_from_req(request=other_request, raise_error=True)
            # we pop the lle for the current request
            lle, lle_time = self.lle_manager.pop_from_req(request=message, raise_error=True)

            wait_time = self.sim_context.time() - lle_time
            other_wait_time = self.sim_context.time() - other_lle_time

            # decohere both states
            self._decohere_state(other_request, other_wait_time, get_werner_state(fidelity=1.))
            self._decohere_state(message, wait_time, get_werner_state(fidelity=1.))

            # swap the two requests
            self._decohere_state(other_request, wait_time=0., other_pair=message.meta["qstate"])
            message.meta["qstate"] = other_request.meta["qstate"]
            # now both states have been updated and match

            # generate the acknowledgments for both requests
            destination_a = self.flows_info[flow_id]["source"] if direction == "upstream" else self.flows_info[flow_id]["destination"]
            destination_b = self.flows_info[flow_id]["source"] if other_direction == "upstream" else self.flows_info[flow_id]["destination"]

            # determine which destination is further away from this node on the path
            path = self.flows_info[flow_id]["path"]
            idx_a = path.index(destination_a)
            idx_b = path.index(destination_b)
            this_idx = path.index(self.name)
            if abs(idx_a - this_idx) < abs(idx_b - this_idx):  # to determine who collects stats
                destination_a, destination_b = destination_b, destination_a
                other_request, message = message, other_request
                other_direction, direction = direction, other_direction
                other_port, port_name = port_name, other_port



            ack_a = messages.EntanglementGenAcknowledgement(req_id=message.req_id, flow_id=flow_id,
                                                            destination=destination_a,
                                                            congested=message.is_congested(),
                                                            gen_time=message.gen_time,
                                                            qstate=message.meta["qstate"],
                                                            ack_time=self.sim_context.time())
            ack_b = messages.EntanglementGenAcknowledgement(req_id=other_request.req_id, flow_id=flow_id,
                                                            destination=destination_b,
                                                            congested=other_request.is_congested(),
                                                            gen_time=other_request.gen_time,
                                                            skip_stats=True)

            # send the acknowledgments
            self.send(ack_a, port_name=port_name)
            self.send(ack_b, port_name=other_port)

            # log a bunch of debug info about who is sending what to whom
            sim_log.debug(
                f"Request {message.req_id} swapped with request {other_request.req_id} for flow {flow_id}. Here is node {self.name}."
                f" Request {message.req_id} sent to {destination_a} through port {port_name} and request {other_request.req_id} sent to {destination_b} through port {other_port}",
                time=self.sim_context.time())

            self.emit_metric("rendezvous_node", int(self.name[2:]))

            return
        """

        # we have to check whether we have a lle to swap with the request
        # if so, we swap, update the message information and forward the request to the next node
        next_port = self.flows_info[flow_id]["next_port"][direction]
        next_hop = self.flows_info[flow_id]["next_hop_down"] if direction == "downstream" else self.flows_info[flow_id]["next_hop_up"]
        if self.lle_manager.is_empty(port_name=next_port, flow_id=flow_id):
            # just append the request to the corresponding queue
            success_prob = self._get_success_prob(message, direction=message.meta["direction"])
            self.req_queue.add_request(message, next_port, self.sim_context.time())
            return

        # there is at least a lle for this flow that can be swapped with the request
        # pop the lle for the request
        # pop the youngest suitable lle
        other_lle, other_lle_time = self.lle_manager.pop_lle(port_name=next_port, flow_id=flow_id, owner=True,
                                                             policy=LLEManager.YOUNGEST)

        if other_lle is None:
            # we don't own any lle for this flow, we just append the request to the corresponding queue
            success_prob = self._get_success_prob(message, direction=message.meta["direction"])
            self.req_queue.add_request(message, next_port, self.sim_context.time())
            return

        lle, lle_time = self.lle_manager.pop_from_req(request=message, raise_error=True)

        # update request
        wait_time = self.sim_context.time() - other_lle_time
        message.update_request(lle_id=other_lle.lle_id, wait_time=wait_time,
                               destination=next_hop)

        # decohere the quantum state described within the request
        self._decohere_state(message, wait_time)

        # send the message
        self.send(message, port_name=next_port)

        # emit queueing time for the request (only intermediate repeater)
        if self.name == "qn1":
            self.emit_metric("queuing_time", 0.0)

    def _decohere_state(self, message, wait_time, other_pair=None):
        # decohere the quantum state described within the request
        wait_time_seconds = wait_time / self.sim_context.time_unit_factor
        rate = message.meta["src_decoherence_rate"] + self.decoherence_rate
        new_state = depolarize_rate(message.meta["qstate"], rate, wait_time_seconds)
        if other_pair is None:
            other_pair = get_werner_state(fidelity=1.)
        new_state = swap(new_state, other_pair, eta=1., p_2=1.)
        message.meta["qstate"] = new_state

    def _handle_new_request(self, message):
        flow_id = message.flow_id

        # if we are not the source we ignore the request
        if (flow_id not in self.flows_info or
                (self.name != self.flows_info[flow_id]["source"] and self.name != self.flows_info[flow_id]["destination"])):
            raise ValueError(f"New request for which we are not the source: {message} at node {self.name}")


        # initialize the epr pair state that will be tracked and updated after every swap
        epr_pair_initial = get_werner_state(fidelity=1.)
        message.meta["qstate"] = epr_pair_initial
        message.meta["src_decoherence_rate"] = self.decoherence_rate

        """
        sim_log.debug(f"Request generated for flow {flow_id}. Here is node {self.name} with a queue empty? {self.req_queue.is_empty()}",
                      time=self.sim_context.time())
        """

        # now let's check whether we should mark the request as congested
        if not message.is_congested():
            direction = message.meta["direction"]
            aqm = self.aqm_controllers[direction]
            marking_prob = aqm.get_marking_probability()
            random_number = self.sim_context.rng.random(generator=flow_id)
            # use the i-th random number generator offered by the sim_context
            # to check whether the request should be marked as congested
            if random_number < marking_prob:
                message.mark_congested()


        # we are the source, we have to check whether we have a lle to associate with the request
        # if so, we associate the lle and send the request to the next node
        direction = message.meta["direction"]
        next_port = self.flows_info[flow_id]["next_port"][direction]
        next_hop = self.flows_info[flow_id]["next_hop_down"] if direction == "downstream" else self.flows_info[flow_id][
            "next_hop_up"]
        if self.lle_manager.is_empty(port_name=next_port, flow_id=flow_id):
            # just append the request to the corresponding queue

            # check that the number of requests in queue in this direction is less than 100
            if self.req_queue.weighted_length(out_port=next_port) >= 2*self.storage_qbits_per_port:
                # drop the request
                return

            self.req_queue.add_request(message, out_port=next_port, time=self.sim_context.time())
            return

        # there is at least an lle for this flow that can be assigned to the request
        # pop the lle
        lle, lle_time = self.lle_manager.pop_lle(port_name=next_port, flow_id=message.flow_id, owner=True,
                                                 policy=LLEManager.YOUNGEST)

        if lle is None:
            # we don't own any lle for this flow, we just append the request to the corresponding queue
            self.req_queue.add_request(message, out_port=next_port, time=self.sim_context.time())
            return

        # update request
        message.update_request(lle_id=lle.lle_id, wait_time=None,
                               destination=next_hop)

        # send the message
        self.send(message, port_name=next_port)


    def _handle_new_lle(self, message, port_name):
        """
        This method is called when an EntanglementGenPacket is received
        """
        flow_id = message.flow_id
        # we have to check whether there is a request to be swapped with this lle
        # if so, we swap, update the message information and forward the request to the next node

        # first of all we have to check whether the flow is still active
        if flow_id not in self.flows_info:
            # the flow has been deleted
            # do nothing
            return

        # first we check if we are the owner of the lle
        if not message.meta["owner"]:
            # we are not the owner, we just have to store the lle
            self.add_lle(message, port_name)
            return

        if self.req_queue.length(flow_id=flow_id, out_port=port_name) == 0:  # no requests for this flow :(
            # append
            self.add_lle(message, port_name)
            """# if flow is upstream and port_name is q1 we raise an error
            if self.flows_info[flow_id]["direction"] == "upstream" and port_name == "q1":
                print("Maybe About to raise error. The interested queue is", self.req_queue._requests)
                print("The LLE msg is ", message)
                raise ValueError(f"{self.name} Received a new lle for flow {flow_id} on {port_name} for which there are no requests")
            # if flow is downstream and port_name is q0 we raise an error
            if self.flows_info[flow_id]["direction"] == "downstream" and port_name == "q0":
                print("About to raise error. The interested queue is", self.req_queue._requests)
                print("The LLE msg is ", message)
                raise ValueError(f"{self.name} Received a new lle for flow {flow_id} on {port_name} for which there are no requests")"""
            return

        # now we are sure that the new lle is in the flow direction we were waiting for and there is a request for it

        # pop the request from the queue
        request, request_time = self.req_queue.pop_request(flow_id, out_port=port_name, policy=RequestQueue.OLDEST)

        # there is at least a request for this flow on this port
        direction = request.meta["direction"]
        next_port = port_name
        next_hop = self.flows_info[flow_id]["next_hop_down"] if direction == "downstream" else self.flows_info[flow_id][
            "next_hop_up"]

        # Now we have to check whether we are the source of the flow
        if ((direction == "upstream" and self.name == self.flows_info[flow_id]["source"]) or
                (direction == "downstream" and self.name == self.flows_info[flow_id]["destination"])):
            # in this case we just have to associate the new lle to the request and send it to the next node
            request.update_request(lle_id=message.lle_id, wait_time=None,
                                   destination=next_hop)

            self.send(request, port_name=next_port)
            return

        # we are not the source, we have to pop the lle associated with the request
        # pop lle associated to the popped request
        other_lle, other_lle_time = self.lle_manager.pop_from_req(request=request, raise_error=True)

        # swap the lles
        # update the request message by adding the swapped lle wait time
        wait_time = self.sim_context.time() - other_lle_time

        # update the request message
        request.update_request(lle_id=message.lle_id, wait_time=wait_time,
                               destination=next_hop)

        # decohere the quantum state described within the request
        self._decohere_state(request, wait_time)

        # send the message
        self.send(request, port_name=next_port)

        # emit queueing time for the request (only intermediate repeater)
        if self.name == "qn1":
            self.emit_metric("queuing_time", self.sim_context.time() - request_time)

    def add_lle(self, lle, port_name):
        """
        Add an LLE to the manager. If there are no free storage qubits, we try to pop the oldest lle for the same flow
        and replace it with the new one. If there are no lles for the same flow, we pop the oldest lle
        for that port and replace it with the new one.

        Parameters
        ----------
        lle : EntanglementGenPacket
            The LLE to add
        port_name : str
            The name of the port on which the LLE is available
        """

        if self.storage_qbits_per_port is not None:
            if self.lle_manager.length(port_name) >= self.storage_qbits_per_port:
                # we have to pop the oldest lle for the same flow
                # if there are no lles for the same flow, we pop the oldest lle for that port
                # if there are no lles for that port, we raise an error
                lle_to_pop, _ = self.lle_manager.pop_lle(port_name=port_name, flow_id=lle.flow_id,
                                                      policy=LLEManager.OLDEST)
                if lle_to_pop is None:
                    # we have to pop the oldest lle for that port
                    lle_to_pop, _ = self.lle_manager.pop_lle(port_name=port_name, policy=LLEManager.OLDEST)
                    if lle_to_pop is None:
                        raise ValueError("No LLEs available for popping")

                # now we have to check whether the popped lle is associated with a request
                # if so, we have to drop the request
                request, _ = self.req_queue.pop_from_lle(lle_to_pop, raise_error=False)
                if request is not None:
                    # the request has been dropped
                    sim_log.warning(f"Request {request.req_id} dropped at node {self.name} due to storage qubit shortage",
                                    time=self.sim_context.time())
                self.lle_manager.add_lle(lle, port_name, self.sim_context.time())
                return

        self.lle_manager.add_lle(lle, port_name, self.sim_context.time())

    def _handle_req_ack(self, message, port_name):
        """
        This method is called when an EntanglementGenAcknowledgement is received
        """
        flow_id = message.flow_id

        # log the request acknowledgement
        """sim_log.debug(f"Request {message.req_id} acknowledged for flow {flow_id}. Here is node {self.name}",
                      time=self.sim_context.time())"""

        if "skip_stats" not in message.meta or not message.meta["skip_stats"]:
            ack_transmission_time = self.sim_context.time() - message.meta["ack_time"]
            qstate = message.meta["qstate"]
            # decohere the quantum state described within the request
            rate = 2*self.decoherence_rate  # 2 because both end nodes will decohere the state
            ack_transmission_time_seconds = ack_transmission_time / self.sim_context.time_unit_factor
            qstate = depolarize_rate(qstate, rate, ack_transmission_time_seconds)
            fidelity = qstate.a

            # emit the fidelity metric
            self.emit_metric("fidelity", fidelity)

            self.emit_metric(name="throughput", value=1)

            self.emit_metric("latency", self.sim_context.time() - message.gen_time)

        if flow_id not in self.flows_info:
            sim_log.warning(f"Received an acknowledgement for a flow not in the flows information: {message} at node {self.name}",
                            time=self.sim_context.time())
            return

        # first we check whether we are the source of the flow, otherwise we throw an error
        if self.name != self.flows_info[flow_id]["source"] and self.name != self.flows_info[flow_id]["destination"]:
            raise ValueError(f"Received an acknowledgement for a flow for which we are not"
                             f"the source or destination: {message} at node {self.name}")

        num_new_requests = self.congestion_controller.handle_ack(req_id=message.req_id, flow_id=flow_id,
                                                                 mark_congested=message.congested,
                                                                 current_time=self.sim_context.time(),
                                                                 time_sent=message.gen_time)

        # emit the congestion window for flow 0
        if flow_id == 0 and isinstance(self.congestion_controller, WindowCongestionController):
            self.emit_metric("congestion_window", self.congestion_controller.get_congestion_window(flow_id))

        elif flow_id == 0 and isinstance(self.congestion_controller, RateCongestionController):
            self.emit_metric("IRG", self.congestion_controller.get_inter_request_gap(flow_id))

        # we generate new tokens for the flow
        for _ in range(num_new_requests):
            self._handle_new_token(flow_id)
