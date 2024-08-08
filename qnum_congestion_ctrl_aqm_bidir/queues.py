"""
In this module we implement the RequestQueue class, which is a simple wrapper around a list of requests. It is used to
store the requests that are waiting to be processed by QuantumNodes.
"""


class RequestQueue:
    """
    This class is a simple wrapper around a list of requests. It is used to store the requests that are waiting to be
    processed by QuantumNodes.
    """

    # create an enumerator for the popping policy (oldest or youngest)
    OLDEST = 0
    YOUNGEST = 1

    def __init__(self):
        self._requests = {}

    def add_request(self, request, out_port, time):
        """
        Add a request to the queue

        Parameters
        ----------
        request : EntanglementRequestPacket
            The request to add
        out_port : str
            The name of the port where the request is to be forwarded
        time : float
            The simulation time the request was added to the queue
        """
        if out_port not in self._requests:
            self._requests[out_port] = []

        self._requests[out_port].append((request, time))

    def _merged_requests(self):
        # merge all queues into a single one ordered by time
        queue = []

        """for q in self._requests.values():  # simple merge but not computationally efficient (O(nlogn))
            queue.extend(q)
        queue = sorted(queue, key=lambda x: x[1])"""

        # implement a sorted merge (O(n))
        for port, q in self._requests.items():
            if len(queue) == 0:
                queue = [(elem[0], elem[1], port) for elem in q]
            else:
                i = 0
                j = 0
                merged = []
                while i < len(queue) and j < len(q):
                    if queue[i][1] < q[j][1]:
                        merged.append((queue[i][0], queue[i][1], queue[i][2]))
                        i += 1
                    else:
                        merged.append((q[j][0], q[j][1], port))
                        j += 1
                if i < len(queue):
                    rest = [(elem[0], elem[1], elem[2]) for elem in queue[i:]]
                    merged.extend(rest)
                if j < len(q):
                    rest = [(elem[0], elem[1], port) for elem in q[j:]]
                    merged.extend(rest)
                queue = merged
        return queue

    def pop_request(self, flow_id, out_port=None, policy=OLDEST):
        """
        Remove and return the first request in the queue

        Parameters
        ----------
        flow_id : int
            The flow id of the request to pop
        out_port : str or None, optional
            The name of the port to pop the request from. If None, any port will be considered. Default is None.
        policy : int or None, optional
            The policy to use when popping the request. It can be either OLDEST (0) or YOUNGEST (1). Default is OLDEST.

        Returns
        -------
        tuple
            A tuple with the request and the time it was added to the queue, or (None, None) if no request for that flow
            id was found
        """
        queue = None
        call_again = False
        if out_port is not None:
            if out_port not in self._requests:
                return None, None
            queue = self._requests[out_port]
        else:
            queue = self._merged_requests()
            call_again = True

        ret = None
        if policy == self.OLDEST:
            # pop the oldest request
            for i, entry in enumerate(queue):
                if entry[0].flow_id == flow_id:
                    ret = queue.pop(i)
                    break
        else:
            # pop the youngest request
            for i, entry in enumerate(queue[::-1]):
                if entry[0].flow_id == flow_id:
                    ret = queue.pop(-i - 1)
                    break

        if call_again and ret is not None:
            return self.pop_request(flow_id, out_port=ret[2], policy=policy)
        elif ret is not None:
            return ret
        return None, None

    def pop_from_lle(self, lle, out_port=None, raise_error=False):
        """
        Remove and return the request in the queue associated with the LLE

        Parameters
        ----------
        lle : EntanglementGenPacket
            The LLE to satisfy
        out_port : str or None, optional
            The name of the port to pop the request from. If None, any port will be considered. Default is None.
        raise_error : bool, optional
            Whether to raise an error if no request is found. Default is False.

        Returns
        -------
        tuple
            A tuple with the request and the time it was added to the queue, or (None, None) if no request was found
            and raise_error is False
        """
        call_again = False
        if out_port is not None:
            queue = self._requests[out_port]
        else:
            queue = self._merged_requests()
            call_again = True
        target = None
        for i, entry in enumerate(queue):
            if entry[0].lle_id == lle.lle_id:
                target = queue.pop(i)
                break

        if call_again and target is not None:
            return self.pop_from_lle(target[0], out_port=target[2], raise_error=raise_error)
        elif target is not None:
            return target
        elif raise_error:
            raise ValueError("No request found for the given LLE")
        return None, None

    def peek_request(self, flow_id=None, out_port=None, policy=OLDEST):
        """
        Return the first request in the queue without removing it

        Parameters
        ----------
        flow_id : int
            The flow id of the request to peek. If None, any flow id will be considered. Default is None.
        out_port : str
            The name of the port to peek the request from. If None, any port will be considered. Default is None.
        policy : int
            The policy to use when peeking the request. It can be either OLDEST (0) or YOUNGEST (1)

        Returns
        -------
        tuple
            A tuple with the request and the time it was added to the queue, or (None, None) if no request for that flow
            id was found
        """
        queue = None
        call_again = False
        if out_port is not None:
            if out_port not in self._requests:
                return None, None
            queue = self._requests[out_port]
        else:
            queue = self._merged_requests()
            call_again = True

        ret = None
        if policy == self.OLDEST:
            # pop the oldest request
            for i, entry in enumerate(queue):
                if flow_id is None or entry[0].flow_id == flow_id:
                    ret = queue[i]
                    break
        else:
            # pop the youngest request
            for i, entry in enumerate(queue[::-1]):
                if flow_id is None or entry[0].flow_id == flow_id:
                    ret = queue[-i - 1]
                    break

        if ret is not None:
            return ret[0], ret[1]

        return None, None

    def delete_requests(self, flow_id):
        """
        Delete all requests for a given flow id

        Parameters
        ----------
        flow_id : int
            The flow id of the requests to delete
        """

        for port_name in self._requests.keys():
            self._requests[port_name] = [req for req in self._requests[port_name] if req[0].flow_id != flow_id]

    def is_empty(self, out_port=None, flow_id=None):
        """
        Check whether the queue is empty for a given (optional) flow identifier

        Parameters
        ----------
        out_port : str or None, optional
            The name of the port to check for requests. If None, all ports will be considered. Default is None.
        flow_id : int or None, optional
            The flow id to check for requests. If None, the method will check if the queue is empty. Default is None.

        Returns
        -------
        bool
            True if there are no requests for a given flow, False otherwise. If no flow id is given, return True if
            there are no requests in the queue, False otherwise.
        """
        return self.length(out_port=out_port, flow_id=flow_id) == 0

    def __len__(self):
        tot_len = 0
        for queue in self._requests.values():
            tot_len += len(queue)
        return tot_len

    def length(self, flow_id=None, out_port=None):
        """
        Return the total number of requests in the queue for a given flow id and/or port name

        Parameters
        ----------
        flow_id : int or None, optional
            The flow id of the requests to count. If None, all requests will be counted. Default is None.
        out_port : str or None, optional
            The name of the port to count the requests from. If None, all ports will be considered. Default is None.

        Returns
        -------
        int
            The total number of requests in the queue for the given flow id
        """

        if out_port is not None:
            if out_port not in self._requests:
                return 0

            if flow_id is not None:
                return len([req for req in self._requests[out_port] if req[0].flow_id == flow_id])

            return len(self._requests[out_port])
        else:
            if flow_id is not None:
                return len([req for queue in self._requests.values() for req in queue if req[0].flow_id == flow_id])

            return len(self)

    def weighted_length(self, out_port):
        """
        Get the total number of requests belonging to any flow with the specified direction.
        The weight of each request is 1/success_prob.

        Parameters
        ----------
        out_port : string
            The output port to consider

        Returns
        -------
        float
            The weighted queue length for the given output port
        """
        tot_len = 0.
        tot_len_unweighted = 0
        if out_port not in self._requests:
            return 0.
        for req, time in self._requests[out_port]:
            success_prob = 1 if "success_prob" not in req.meta else req.meta["success_prob"]
            tot_len += 1. / success_prob
            tot_len_unweighted += 1
        return tot_len_unweighted

class LLEManager:
    """
    This class is a wrapper around a list of LLEs. It is used to store the LLEs that are available to be used by
    QuantumNodes.
    """

    # create an enumerator for the popping policy (oldest or youngest)
    OLDEST = 0
    YOUNGEST = 1

    def __init__(self, port_names):
        self._lles = {port_name: [] for port_name in port_names}

    def add_lle(self, lle, port_name, time):
        """
        Add an LLE to the manager

        Parameters
        ----------
        lle : EntanglementGenPacket
            The LLE to add
        port_name : str
            The name of the port on which the LLE is available
        time : float
            The simulation time the LLE was added to the manager
        """
        self._lles[port_name].append((lle, time))

    def pop_from_req(self, request, raise_error=True):
        """
        Remove and return the LLE in the manager associated with the request

        Parameters
        ----------
        request : EntanglementRequestPacket
            The request to satisfy
        raise_error : bool, optional
            Whether to raise an error if no LLE is found. Default is True.

        Returns
        -------
        tuple
            A tuple with the LLE and the time it was added to the manager, or (None, None) if no LLE was found
        """
        for port_name, lles in self._lles.items():
            for i, (lle, time) in enumerate(lles):
                if lle.flow_id == request.flow_id and lle.lle_id == request.lle_id:
                    return self._lles[port_name].pop(i)
        if raise_error:
            raise ValueError("No LLE found for the given request")
        return None, None

    def peek_from_req(self, request, raise_error=True):
        """
        Return the LLE in the manager associated with the request

        Parameters
        ----------
        request : EntanglementRequestPacket
            The request to satisfy
        raise_error : bool, optional
            Whether to raise an error if no LLE is found. Default is True.

        Returns
        -------
        tuple
            A tuple with the LLE and the time it was added to the manager, or (None, None) if no LLE was found
        """
        for port_name, lles in self._lles.items():
            for lle, time in lles:
                if lle.flow_id == request.flow_id and lle.lle_id == request.lle_id:
                    return lle, time
        if raise_error:
            raise ValueError("No LLE found for the given request")
        return None, None

    def pop_lle(self, port_name, flow_id=None, owner=False, policy=OLDEST):
        r"""
        Pop an LLE from the manager available on the given port, according to the given policy

        Parameters
        ----------
        port_name : str
            The name of the port where the LLE is available
        flow_id : int or None, optional
            The flow id of the LLE to pop. If None, the method will pop the first LLE available on the port. Default is
            None.
        owner : bool, optional
            Whether the LLE should be owned by the QuantumNode that pops it. Default is False. If False, the LLE can either
            be owned by the QuantumNode or not.
        policy : int
            The policy to use when popping the LLE. It can be either OLDEST (0) or YOUNGEST (1)

        Returns
        -------
        tuple
            A tuple with the LLE and the time it was added to the manager, or (None, None) if no LLE was found

        """

        if policy == self.OLDEST:
            for i, (lle, time) in enumerate(self._lles[port_name]):
                if flow_id is None or lle.flow_id == flow_id:
                    if (not owner) or (owner and lle.meta["owner"]):
                        return self._lles[port_name].pop(i)
        elif policy == self.YOUNGEST:
            for i, (lle, time) in enumerate(self._lles[port_name][::-1]):
                if flow_id is None or lle.flow_id == flow_id:
                    if (not owner) or (owner and lle.meta["owner"]):
                        return self._lles[port_name].pop(-i - 1)
        else:
            raise ValueError("Invalid policy")

        return None, None

    def peek_lle(self, port_name, flow_id=None, owner=False, policy=OLDEST):
        """
        Peek at an LLE from the manager available on the given port, according to the given policy

        Parameters
        ----------
        port_name : str
            The name of the port where the LLE is available
        flow_id : int or None, optional
            The flow id of the LLE to pop. If None, the method will pop the first LLE available on the port. Default is
            None.
        owner : bool, optional
            Whether the LLE should be owned by the QuantumNode that pops it. Default is False. If False, the LLE can either
            be owned by the QuantumNode or not.
        policy : int
            The policy to use when popping the LLE. It can be either OLDEST (0) or YOUNGEST (1)

        Returns
        -------
        tuple
            A tuple with the LLE and the time it was added to the manager, or (None, None) if no LLE was found

        """

        if policy == self.OLDEST:
            for lle, time in self._lles[port_name]:
                if flow_id is None or lle.flow_id == flow_id:
                    if (not owner) or (owner and lle.meta["owner"]):
                        return lle, time
        elif policy == self.YOUNGEST:
            for lle, time in self._lles[port_name][::-1]:
                if flow_id is None or lle.flow_id == flow_id:
                    if (not owner) or (owner and lle.meta["owner"]):
                        return lle, time
        else:
            raise ValueError("Invalid policy")

        return None, None

    def delete_lles(self, flow_id):
        """
        Delete all LLEs for a given flow id

        Parameters
        ----------
        flow_id : int
            The flow id of the LLEs to delete
        """

        for port_name in self._lles.keys():
            self._lles[port_name] = [lle for lle in self._lles[port_name] if lle[0].flow_id != flow_id]


    def is_empty(self, port_name, flow_id=None):
        """
        Check whether the manager is empty for a given (optional) flow identifier

        Parameters
        ----------
        port_name : str
            The name of the port to check for LLEs
        flow_id : int or None, optional
            The flow id to check for LLEs. If None, the method will check if the manager is empty. Default is None.

        Returns
        -------
        bool
            True if there are no LLEs for a given flow, False otherwise. If no flow id is given, return True if
            there are no LLEs in the manager, False otherwise.
        """
        if flow_id is not None:
            return len([lle for lle in self._lles[port_name] if lle[0].flow_id == flow_id]) == 0
        else:
            return len(self._lles[port_name]) == 0

    def __len__(self):
        """
        Return the total number of LLEs in the manager

        Returns
        -------
        int
            The total number of LLEs in the manager
        """
        tot_len = 0
        for lles in self._lles.values():
            tot_len += len(lles)
        return tot_len

    def length(self, port_name):
        """
        Return the total number of LLEs in the manager for a given port

        Returns
        -------
        int
            The total number of LLEs in the manager for the given port
        """
        return len(self._lles[port_name])
