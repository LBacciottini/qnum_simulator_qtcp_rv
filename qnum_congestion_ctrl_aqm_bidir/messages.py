from omnetpypy import Message


class RoutablePacket(Message):
    """
    This class models a classical packet that can be routed through a network.

    The only constraint to the packet is that it must have a specified destination in its meta.
    """

    def __init__(self, destination, fields, **meta):
        meta["destination"] = destination
        super().__init__(fields, **meta)

    @property
    def destination(self):
        return self.meta["destination"]

    @destination.setter
    def destination(self, value):
        self.meta["destination"] = value


class FlowsInformationPacket(RoutablePacket):
    r"""
    This class models a message that carries information about the flows in the network.

    Parameters
    ----------

    flows : list
        Flow descriptors, each one containing the following fields:
        <ul>
            <li>flow_id</li>
            <li>source</li>
            <li>destination</li>
            <li>path (list of node names, including link controllers)</li>
            <li>success_probs (list of success probabilities for each link in the path)</li>
            <li>request_rate (average, Poisson process)</li>
            <li>direction (upstream or downstream)</li>
        </ul>
    """

    HEADER = "FLOWS INFORMATION"

    def __init__(self, flows, destination, **meta):
        meta["header"] = FlowsInformationPacket.HEADER
        fields = [flows]
        super().__init__(destination, fields, **meta)

    @property
    def flows(self):
        return self.fields[0]

    def __copy__(self):
        new_meta = self.meta.copy()
        flows_cpy = [desc.copy() for desc in self.flows]
        return FlowsInformationPacket(flows=flows_cpy, **new_meta)


class FlowDeletionPacket(RoutablePacket):
    """
    This class models a message that carries information about a flow deletion in the network.

    Parameters
    ----------

    flow_id : int
        The identifier of the flow to be deleted
    """

    HEADER = "FLOW DELETION"

    def __init__(self, flow_id, destination, **meta):
        meta["header"] = FlowDeletionPacket.HEADER
        fields = [flow_id]
        super().__init__(destination, fields, **meta)

    @property
    def flow_id(self):
        return self.fields[0]

class EntanglementRequestPacket(RoutablePacket):

    HEADER = "ENTANGLEMENT REQUEST"

    def __init__(self, req_id, destination, flow_id, lle_id, gen_time, wait_times=None, **meta):
        if wait_times is None:
            wait_times = []
        super().__init__(destination, fields=[req_id, flow_id, lle_id, gen_time, wait_times],
                         header=EntanglementRequestPacket.HEADER, congested_ECN=False, **meta)

    @property
    def req_id(self):
        return self.fields[0]

    @property
    def flow_id(self):
        return self.fields[1]

    @property
    def lle_id(self):
        return self.fields[2]

    @lle_id.setter
    def lle_id(self, value):
        self.fields[2] = value

    @property
    def gen_time(self):
        return self.fields[3]

    @gen_time.setter
    def gen_time(self, value):
        self.fields[3] = value

    @property
    def wait_times(self):
        return self.fields[4]

    @property
    def direction(self):
        if "direction" not in self.meta:
            return None
        return self.meta["direction"]

    def is_congested(self):
        """
        Whether the request has been marked with an Explicit Congestion Notification (ECN) or not.

        Returns
        -------
        bool
            True if the request has been marked as congested, False otherwise.
        """
        return self.meta["congested_ECN"]

    def mark_congested(self):
        """
        Mark the request as congested, using an Explicit Congestion Notification (ECN).
        """
        self.meta["congested_ECN"] = True

    def append_wait_time(self, wait_time):
        self.wait_times.append(wait_time)

    def __copy__(self):
        new_meta = self.meta.copy()
        del new_meta["destination"]
        del new_meta["header"]
        del new_meta["congested_ECN"]
        fields_cpy = self.fields[:]
        ret = EntanglementRequestPacket(req_id=fields_cpy[0], destination=self.destination,
                                         flow_id=fields_cpy[1], lle_id=fields_cpy[2], wait_times=fields_cpy[3][:],
                                         **new_meta)
        if self.is_congested():
            ret.mark_congested()

        return ret

    def update_request(self, lle_id=None, wait_time=None, destination=None):
        """
        Update the request with the new lle_id, wait_time and destination. Usually done right before forwarding the
        request to the next node.

        Parameters
        ----------
        lle_id : int or None, optional
            The new lle_id
        wait_time : float or None, optional
            The wait time for the last swapped lle, appended to the wait_times list
        destination : str or None, optional
            The new destination for the request (next hop)
        """
        if lle_id is not None:
            self.lle_id = lle_id
        if wait_time is not None:
            self.append_wait_time(wait_time)
        if destination is not None:
            self.destination = destination


class EntanglementGenPacket(Message):
    """
    This class models the message sent by link controllers to nodes, encapsulating the entanglement generation
    for a given flow
    """

    HEADER = "ENTANGLEMENT GENERATION"

    def __init__(self, flow_id, lle_id, sender_name, **meta):
        meta["header"] = EntanglementGenPacket.HEADER
        fields = [flow_id, lle_id, sender_name]
        super().__init__(fields, **meta)

    @property
    def flow_id(self):
        return self.fields[0]

    @property
    def lle_id(self):
        return self.fields[1]

    @property
    def sender_name(self):
        return self.fields[2]


class EntanglementGenAcknowledgement(RoutablePacket):
    """
    This class models the message sent by nodes to link controllers, acknowledging the entanglement generation
    for a given flow
    """

    HEADER = "ENTANGLEMENT GEN ACK"

    def __init__(self, destination, flow_id, req_id, gen_time, congested=False, **meta):
        fields = [flow_id, req_id, gen_time, congested]
        super().__init__(fields=fields, destination=destination, header=EntanglementGenAcknowledgement.HEADER,
                         **meta)

    @property
    def flow_id(self):
        return self.fields[0]

    @property
    def req_id(self):
        return self.fields[1]

    @property
    def gen_time(self):
        return self.fields[2]

    @property
    def congested(self):
        return self.fields[3]

    @congested.setter
    def congested(self, value):
        self.fields[3] = value

