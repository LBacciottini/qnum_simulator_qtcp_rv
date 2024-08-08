from omnetpypy import SimpleModule, Message, sim_log
from qnum_congestion_ctrl_aqm_bidir import messages
from qnum_congestion_ctrl_aqm_bidir.messages import RoutablePacket, EntanglementGenPacket, \
    FlowsInformationPacket, FlowDeletionPacket
from qnum_congestion_ctrl_aqm_bidir.utility import sanitize_flow_descriptors


class LinkController(SimpleModule):
    """
    This class models a Link Controller, placed in the middle of a link.
    """

    def __init__(self, name, identifier, t_clock):
        port_names = ["lc0", "lc1"]

        super().__init__(name, identifier, port_names)
        self.t_clock = t_clock

        self._flow_probabilities = {}
        # dictionary of flow probabilities, one for each flow, indexed by flow_id. They must sum to 1.

        self._flow_attempt_probabilities = {}
        # dictionary of flow attempt probabilities, one for each flow, indexed by flow_id. They must NOT sum to 1.

        self._flow_directions = {}

        self._trigger_msg = Message(["trigger attempt"], header="trigger")

        self._cur_lle_id = 0

    def initialize(self, step=0):
        if step == 0:
            """
            Schedule the first attempt to entangle the flows
            """
            first_attempt_time = self.sim_context.rng.random(generator=0) * self.t_clock
            self.schedule_message(self._trigger_msg, delay=first_attempt_time)

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

            message = messages.FlowsInformationPacket(destination=self.name, flows=flow_descriptors)
            self._handle_flows_information(message)

    def _attempt_entanglement(self):

        # In this first implementation, we update the flow probabilities right before each attempt, because we have
        # perfect, real-time information on the queues at the adjacent nodes. In future implementations, we will use a
        # more realistic approach where we update the flow probabilities at regular intervals with reduced information.
        self._update_flow_probabilities()

        queues_info = self._get_queues_info()

        # check whether the queues are empty. if so, we don't attempt entanglement
        if queues_info[0].is_empty() and queues_info[1].is_empty():
            self.schedule_message(self._trigger_msg, delay=self.t_clock)
            return

        rng = self.sim_context.rng

        """# first we pick a flow to attempt entanglement for using the flow probabilities

        # now we get the flows for which queues are not empty
        flows = [flow_id for flow_id in self._flow_probabilities.keys() if not queues_info[0].is_empty(flow_id)]

        # we filter out flows whose direction is not upstream
        flows = [flow_id for flow_id in flows if self._flow_directions[flow_id] == "upstream"]

        flows_down = [flow_id for flow_id in self._flow_probabilities.keys() if not queues_info[1].is_empty(flow_id)]

        # we filter out flows whose direction is not downstream
        flows_down = [flow_id for flow_id in flows_down if self._flow_directions[flow_id] == "downstream"]

        flows += flows_down
        # remove duplicates
        assert len(list(set(flows))) == len(flows)

        # check whether flows is empty. if so, we don't attempt entanglement
        if len(flows) == 0:
            self.schedule_message(self._trigger_msg, delay=self.t_clock)
            return

        # derive the probabilities for these flows by normalizing the flow probabilities
        flows_probabilities = [self._flow_probabilities[flow_id] for flow_id in flows]
        summed = sum(flows_probabilities)
        flows_probabilities = [p / summed for p in flows_probabilities]

        # we pick the flow_id using the flow probabilities and the default rng (generator = 0)
        flow_id = rng.choices(sequence=flows,
                              weights=flows_probabilities,
                              k=1,
                              generator=0)[0]"""

        # flip a coin to decide which queue to peek
        left_is_owner = False

        # get queues length
        q0_len = queues_info[0].length()
        q1_len = queues_info[1].length()

        left_prob = q0_len / (q0_len + q1_len)

        if rng.random(generator=0) < left_prob:
            queue = 0
            req, oldest_time = queues_info[0].peek_request(out_port="q1", policy="OLDEST")
            left_is_owner = True
        else:
            queue = 1
            req, oldest_time = queues_info[1].peek_request(out_port="q0", policy="OLDEST")

        if req is None:
            # try the other queue
            queue = 1 - queue
            req, oldest_time = queues_info[queue].peek_request(out_port="q0" if queue == 1 else "q1", policy="OLDEST")
            left_is_owner = not left_is_owner

        if req is None:
            self.schedule_message(self._trigger_msg, delay=self.t_clock)
            return
        flow_id = req.flow_id

        # use a geometric distribution to determine the number of attempts needed
        attempts = rng.geometric(p=self._flow_attempt_probabilities[flow_id], generator=0)

        # create a self message
        self_msg = Message([flow_id, left_is_owner], header="entanglement ready")
        # wait for the number of attempts
        self.schedule_message(self_msg, delay=attempts * self.t_clock)

    def _handle_successful_entanglement(self, message):

        flow_id = message.fields[0]
        left_is_owner = message.fields[1]

        lle_id = self.name + "-" + str(self._cur_lle_id)
        # debug: check that the request we picked is indeed the oldest in the queue for that port name
        # print(f"Here {self.name} for {lle_id} : Request {req} is the oldest ({oldest_time}) in the queue on port q{1 - queue}")
        # print(queues_info[queue]._requests)
        self.send(EntanglementGenPacket(flow_id=flow_id, lle_id=lle_id, sender_name=self.name,
                                        owner=left_is_owner), "lc0")
        self.send(EntanglementGenPacket(flow_id=flow_id, lle_id=lle_id, sender_name=self.name,
                                        owner=not left_is_owner), "lc1")
        self._cur_lle_id += 1

        # we schedule the next attempt

        self.schedule_message(self._trigger_msg, delay=self.t_clock)

    def _get_queues_info(self):
        """
        Get the information on request queues stored on adjacent nodes available to this link controller.
        """

        # The first implementation is a magic trick where we crawl the network to find references to the adjacent
        # nodes and we directly access their queues. In future implementations, we will use a more realistic approach
        # where we send messages to the adjacent nodes asking for their queue status.
        # TODO

        # veeeeeery ugly and unsafe
        node_right = self.ports["lc1"].connected_port.parent.ports["B"].connected_port.parent
        node_left = self.ports["lc0"].connected_port.parent.ports["A"].connected_port.parent

        return node_left.req_queue, node_right.req_queue

    def _update_flow_probabilities(self):
        """
        Update the flow probabilities based on the information on the queues at the adjacent nodes.
        """
        # First implementation: use _get_queues_info to get the queues status and update the flow probabilities based
        # on the number of requests in the queues.
        # TODO
        pass

    def handle_message(self, message, port_name):

        if isinstance(message, FlowsInformationPacket) and message.destination == self.name:
            sim_log.debug(f"{self.name} received flows information with {len(message.flows)} flows.",
                          time=self.sim_context.time())
            self._handle_flows_information(message)
            return

        if isinstance(message, FlowDeletionPacket) and message.destination == self.name:
            sim_log.debug(f"{self.name} received flow deletion for flow {message.flow_id}.",
                          time=self.sim_context.time())
            self._handle_flow_deletion(message)
            return

        if port_name is not None and isinstance(message, RoutablePacket):
            # if this is not the destination, forward the packet on the other port
            if message.destination != self.name:
                # print(f"{self.name} forwarding message {message} to {port_name} at time {self.sim_context.time()}")
                self.send(message, "lc1" if port_name == "lc0" else "lc0")
                return

        elif port_name is None:  # self message, we need to attempt entanglement
            if "header" in message.meta and message.meta["header"] == self._trigger_msg.meta["header"]:
                self._attempt_entanglement()
            elif "header" in message.meta or message.meta["header"] == "entanglement ready":
                self._handle_successful_entanglement(message)
            else:
                raise ValueError("Unknown self message received")

    def _handle_flows_information(self, message):
        for flow in message.flows:
            if self.name not in flow["path"]:
                continue
            flow_id = flow["flow_id"]
            self._flow_probabilities[flow_id] = 1 / len(message.flows)  # begin with equal probabilities for all flows

            # store the flow direction
            self._flow_directions[flow_id] = flow["direction"]

            # find our position on the flow path
            path = flow["path"]
            idx = path.index(self.name)
            # the path is node0---(link_first_half)---link_controller---(link_second_half)---node1...
            # the link controller is attached to link_first_half and link_second_half
            # find link position (first + second halves are one link) on the path that this link controller controls
            link_pos = int((idx - 1) / 2)
            # get the success probability for the link
            success_prob = flow["success_probs"][link_pos]
            # update the flow probabilities
            self._flow_attempt_probabilities[flow_id] = success_prob


    def _handle_flow_deletion(self, message):
        flow_id = message.flow_id
        if flow_id in self._flow_probabilities:
            del self._flow_probabilities[flow_id]
            del self._flow_attempt_probabilities[flow_id]
            del self._flow_directions[flow_id]
        else:
            sim_log.warning(f"Flow {flow_id} not found in the flow probabilities of {self.name}.",
                            time=self.sim_context.time())
            raise ValueError(f"Flow {flow_id} not found in the flow probabilities of {self.name}.")
        return



