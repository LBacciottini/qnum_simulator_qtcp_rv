import abc

from omnetpypy import sim_log


class AIMDCongestionController(abc.ABC):
    """
    A simple congestion controller that uses the Additive Increase Multiplicative Decrease (AIMD) algorithm.
    """

    def __init__(self):
        pass

    @abc.abstractmethod
    def halve_congestion_knob(self, flow_id, current_time=None):
        """
        Halve the congestion metric for the given flow
        """
        pass

    @abc.abstractmethod
    def increase_congestion_knob(self, flow_id, current_time=None):
        """
        Increase the congestion metric for the given flow
        """
        pass

    @abc.abstractmethod
    def setup_congestion_control(self, flow, current_time=None):
        """
        Setup the congestion control variables for the given flow
        """
        pass

    @abc.abstractmethod
    def delete_flow(self, flow_id):
        """
        Delete the flow from the congestion controller
        """
        pass

    @abc.abstractmethod
    def collect_timeouts(self, current_time):
        """
        Collect the timeouts for the requests in flight and update the congestion metric for the involved flows
        """
        pass

    @abc.abstractmethod
    def handle_ack(self, flow_id, req_id, current_time, time_sent, mark_congested=False):
        """
        Handle the ACK for the given request

        Parameters
        ----------
        flow_id : int
            The flow id
        req_id : int
            The request id
        current_time : float
            The current time
        time_sent : float
            The time the request was sent
        mark_congested : bool, optional
            Whether the ack was marked as congested or not

        Returns
        -------
        int
            The number of new requests to generate for the flow
        """
        pass

    @abc.abstractmethod
    def handle_new_request_in_flight(self, flow_id, req_id, current_time):
        """
        Handle a new request in flight for the given flow
        """
        pass


class WindowCongestionController(AIMDCongestionController):
    """
    A simple congestion controller that uses the Additive Increase Multiplicative Decrease (AIMD) algorithm
    with a window-based approach.
    """
    def __init__(self):

        self.congestion_windows = {}  # dictionary of congestion windows, one for each flow, indexed by flow_id
        self.ssthresh = {}  # dictionary of slow start thresholds, one for each flow, indexed by flow_id
        self.is_slow_start = {}  # dictionary of flags indicating if the flow is in slow start, indexed by flow_id
        self.estimated_rtt = {}
        self.dev_rtt = {}
        self.requests_in_flight = {}  # dictionary of requests in flight, one list for each flow, indexed by flow_id
        # every element in the list is a tuple (req_id, time_sent, timeout)
        self.max_congestion_window = 1000  # maximum congestion window size
        self.consecutive_acks = {}  # dictionary of consecutive acks, one for each flow, indexed by flow_id
        self.consecutive_acks_required = 1  # number of consecutive acks to receive before increasing the congestion window

        self.other_ends = {}  # dictionary of other end identifiers, one for each flow, indexed by flow_id

        super().__init__()

    def halve_congestion_knob(self, flow_id, current_time=None):
        """
        Halve the congestion window for the given flow
        """

        self.ssthresh[flow_id] = max(self.congestion_windows[flow_id] / 2, 1)
        self.congestion_windows[flow_id] = 1.
        self.is_slow_start[flow_id] = True

    def increase_congestion_knob(self, flow_id, current_time=None):
        """
        Increase the congestion window for the given flow
        """
        # sim_log.info(f"Flow {flow_id} congestion window increased to {self.congestion_windows[flow_id]}")
        if self.is_slow_start[flow_id]:
            # if the flow is in slow start, double the congestion window
            self.congestion_windows[flow_id] = min(self.max_congestion_window, self.congestion_windows[flow_id] + 1)
            if self.congestion_windows[flow_id] >= self.ssthresh[flow_id]:
                # if the congestion window is greater than the slow start threshold, we are not in slow start anymore
                self.is_slow_start[flow_id] = False
            # sim_log.error(f"Flow {flow_id} congestion window increased to {self.congestion_windows[flow_id]}")
        else:
            # if the flow is not in slow start, increase the congestion window linearly
            increment = 1/self.congestion_windows[flow_id]
            old_congestion_window = self.congestion_windows[flow_id]
            self.congestion_windows[flow_id] = min(self.max_congestion_window, self.congestion_windows[flow_id] + increment)
            # sim_log.info(f"Flow {flow_id} congestion window increased from {old_congestion_window} to {self.congestion_windows[flow_id]}")

    def setup_congestion_control(self, flow, current_time=None):
        """
        Setup the congestion control variables for the given flow
        """
        self.congestion_windows[flow["flow_id"]] = 1.  # initial congestion window size
        self.estimated_rtt[flow["flow_id"]] = 300 * (len(flow["path"]) - 1) * 10  # 3000 us per hop is the initial value
        self.dev_rtt[flow["flow_id"]] = 0.05 * self.estimated_rtt[flow["flow_id"]]  # 5% of the estimated RTT
        self.requests_in_flight[flow["flow_id"]] = []
        self.other_ends[flow["flow_id"]] = flow["destination"]
        self.consecutive_acks[flow["flow_id"]] = 0  # number of consecutive acks to receive before increasing the congestion window
        self.ssthresh[flow["flow_id"]] = float("inf")  # slow start threshold
        self.is_slow_start[flow["flow_id"]] = True  # flag indicating if the flow is in slow start

    def delete_flow(self, flow_id):
        """
        Delete the flow from the congestion controller
        """
        del self.congestion_windows[flow_id]
        del self.estimated_rtt[flow_id]
        del self.dev_rtt[flow_id]
        del self.requests_in_flight[flow_id]
        del self.other_ends[flow_id]
        del self.consecutive_acks[flow_id]
        del self.ssthresh[flow_id]
        del self.is_slow_start[flow_id]

    def collect_timeouts(self, current_time):
        """
        Collect the timeouts for the requests in flight and update the congestion windows for the involved flows
        """
        for flow_id in self.requests_in_flight:
            timed_out = False
            requests = self.requests_in_flight[flow_id]
            new_requests = []
            for req_id, time_sent, timeout in requests:
                if current_time - time_sent > timeout:
                    # the request has timed out
                    # we have to halve the congestion window
                    timed_out = True
                else:
                    new_requests.append((req_id, time_sent, timeout))
            self.requests_in_flight[flow_id] = new_requests
            if timed_out:
                """
                sim_log.info(
                f"Flow {flow_id} timed out {len(requests) - len(new_requests)} times, halving congestion window {self.congestion_windows[flow_id]}")
                """
                self.halve_congestion_knob(flow_id)
                pass

    def handle_ack(self, flow_id, req_id, current_time, time_sent, mark_congested=False):
        """
        Handle the ACK for the given request

        Parameters
        ----------
        flow_id : int
            The flow id
        req_id : int
            The request id
        current_time : float
            The current time
        time_sent : float
            The time the request was sent
        mark_congested : bool, optional
            Whether the ack was marked as congested or not

        Returns
        -------
        int
            The number of new requests to generate for the flow
        """
        num_skipped = 0

        found = False

        # update the estimated RTT
        sample_rtt = current_time - time_sent
        self.estimated_rtt[flow_id] = 0.875 * self.estimated_rtt[flow_id] + 0.125 * sample_rtt
        self.dev_rtt[flow_id] = 0.75 * self.dev_rtt[flow_id] + 0.25 * abs(sample_rtt - self.estimated_rtt[flow_id])
        # print(f"Estimated RTT for flow {flow_id} is {self.estimated_rtt[flow_id]}, dev RTT is {self.dev_rtt[flow_id]}")

        for req, time_sent, timeout in self.requests_in_flight[flow_id]:
            if req < req_id:
                num_skipped += 1
                # if we receive an ACK for a request, we can remove all the requests with lower req_id
                # because they have been surely dropped due to congestion
            elif req == req_id:
                # we found the request for which we received the ACK
                # remove it from the list
                found = True

        if found:
            # remove the tuples from the list
            self.requests_in_flight[flow_id] = self.requests_in_flight[flow_id][num_skipped + 1:]

        else:
            self.requests_in_flight[flow_id] = self.requests_in_flight[flow_id][num_skipped:]
            """
            print(f"Flow {flow_id} received an ACK for a request that was not in flight, num_skipped={num_skipped}, "
                  f"req_id={req_id}, requests_in_flight={self.requests_in_flight[flow_id]}")
            """

        if mark_congested:
            sim_log.warning(f"Flow {flow_id} marked as congested")
            self.halve_congestion_knob(flow_id)

        elif num_skipped > 0:
            # sim_log.error(f"Flow {flow_id} marked as congested due to losses")
            self.halve_congestion_knob(flow_id)

        if num_skipped > 0 or mark_congested:
            self.consecutive_acks[flow_id] = 0

        # we increase the congestion window
        if found:
            self.consecutive_acks[flow_id] += 1
        if self.consecutive_acks[flow_id] == self.consecutive_acks_required:
            self.increase_congestion_knob(flow_id)
            self.consecutive_acks[flow_id] = 0

        # return the number of new requests to generate
        return max(int(self.congestion_windows[flow_id]) - len(self.requests_in_flight[flow_id]), 0)

    def handle_new_request_in_flight(self, flow_id, req_id, current_time):
        """
        Handle a new request in flight for the given flow
        """
        timeout = max(self.estimated_rtt[flow_id] + 4 * self.dev_rtt[flow_id], 0.1)
        self.requests_in_flight[flow_id].append((req_id, current_time, timeout))

    def get_congestion_window(self, flow_id):
        """
        Get the congestion window for the given flow

        Returns
        -------
        int
            The congestion window size
        """
        return self.congestion_windows[flow_id]


class RateCongestionController(AIMDCongestionController):
    """
    A simple congestion controller that uses the Additive Increase Multiplicative Decrease (AIMD) algorithm
    with a rate-based approach. The knob is the new request generation probability, which is used as input
    to a geometric process to generate new requests.

    Additive Increase: increase the rate with a constant slope over time
    Multiplicative Decrease: halve the rate when a congestion event is detected
    """

    def __init__(self, C=50000000):
        self.congestion_knobs = {}  # dictionary of congestion knobs, one for each flow, indexed by flow_id
        self.ssthresh = {}  # dictionary of slow start thresholds, one for each flow, indexed by flow_id
        self.is_slow_start = {}  # dictionary of flags indicating if the flow is in slow start, indexed by flow_id
        self.last_update = {}  # dictionary of last update times, one for each flow, indexed by flow_id
        self.last_halved = {}  # dictionary of last halved times, one for each flow, indexed by flow_id
        self.other_ends = {}  # dictionary of other end identifiers, one for each flow, indexed by flow_id
        self.C = {}  # dictionary of C values, one for each flow, indexed by flow_id
        self.default_C = C  # default C value

        self.initial_congestion_knob = 48000  # initial congestion knob (IRG), (us)
        self.max_ssthresh = 1024000  # maximum slow start threshold

        self.estimated_rtt = {}
        self.dev_rtt = {}
        self.requests_in_flight = {}  # dictionary of requests in flight, one list for each flow, indexed by flow_id
        # every element in the list is a tuple (req_id, time_sent, timeout)

        super().__init__()

    def halve_congestion_knob(self, flow_id, current_time=None):
        """
        Halve the congestion knob (rate in this case) for the given flow
        """

        # if last half was less than 3RTT ago, do not halve again
        if current_time - self.last_halved[flow_id] < 3*self.estimated_rtt[flow_id]:
            sim_log.debug(f"Flow {flow_id} congestion knob halved ({current_time - self.last_update[flow_id]}) less than an RTT ({self.estimated_rtt[flow_id]}) ago ), not halving again")
            return

        self.ssthresh[flow_id] = min(self.congestion_knobs[flow_id] * 4, self.max_ssthresh)
        self.congestion_knobs[flow_id] = max(self.initial_congestion_knob,
                                             self.ssthresh[flow_id] * 4)
        self.last_update[flow_id] = current_time
        self.last_halved[flow_id] = current_time
        self.is_slow_start[flow_id] = True

        sim_log.info(f"Flow {flow_id} congestion knob halved to {self.congestion_knobs[flow_id]} with ss thresh {self.ssthresh[flow_id]}")
        if current_time is None:
            raise ValueError("Current time must be provided with the rate based controller")

    def increase_congestion_knob(self, flow_id, current_time=None):
        """
        Increase the congestion knob for the given flow
        """
        if current_time is None:
            raise ValueError("Current time must be provided with the rate based controller")
        # elapsed_time = current_time - self.last_update[flow_id]  # us
        if flow_id not in self.is_slow_start:
            raise ValueError(f"Flow {flow_id} not in the congestion controller")
        if not self.is_slow_start[flow_id]:
            new_IRG = (self.C[flow_id] * self.congestion_knobs[flow_id]) / (self.C[flow_id] + self.congestion_knobs[flow_id])
            self.congestion_knobs[flow_id] = new_IRG
        else:
            new_IRG = self.congestion_knobs[flow_id] / 1.1
            self.congestion_knobs[flow_id] = new_IRG
            if new_IRG <= self.ssthresh[flow_id]:
                # print(self.ssthresh[flow_id])
                self.is_slow_start[flow_id] = False

        self.last_update[flow_id] = current_time

        # print(f"Flow {flow_id} congestion knob increased to {self.congestion_knobs[flow_id]}")
        # print(f"Flow {flow_id} congestion knob increased by {increase}")

    def setup_congestion_control(self, flow, current_time=None, is_source=True):
        """
        Setup the congestion control variables for the given flow
        """
        if current_time is None:
            raise ValueError("Current time must be provided with the rate based controller")
        self.congestion_knobs[flow["flow_id"]] = self.initial_congestion_knob  # initial congestion knob (IPG), (us)
        self.last_update[flow["flow_id"]] = current_time
        self.last_halved[flow["flow_id"]] = current_time
        self.other_ends[flow["flow_id"]] = flow["destination"] if is_source else flow["source"]
        self.ssthresh[flow["flow_id"]] = 1200.  # initial slow start threshold
        self.is_slow_start[flow["flow_id"]] = True

        self.estimated_rtt[flow["flow_id"]] = 300 * (len(flow["path"]) - 1) * 10  # 3000 us per hop is the initial value
        self.dev_rtt[flow["flow_id"]] = 0.05 * self.estimated_rtt[flow["flow_id"]]  # 5% of the estimated RTT
        self.requests_in_flight[flow["flow_id"]] = []
        self.C[flow["flow_id"]] = self.default_C

    def delete_flow(self, flow_id):
        """
        Delete the flow from the congestion controller
        """
        del self.congestion_knobs[flow_id]
        del self.estimated_rtt[flow_id]
        del self.dev_rtt[flow_id]
        del self.requests_in_flight[flow_id]
        del self.other_ends[flow_id]
        del self.last_update[flow_id]
        del self.last_halved[flow_id]
        del self.ssthresh[flow_id]
        del self.is_slow_start[flow_id]

    def collect_timeouts(self, current_time):
        """
        Collect the timeouts for the requests in flight and update the congestion knobs for the involved flows
        """
        for flow_id in self.last_update:
            timed_out = False
            requests = self.requests_in_flight[flow_id]
            new_requests = []
            for req_id, time_sent, timeout in requests:
                if current_time - time_sent > timeout:
                    # the request has timed out
                    # we have to halve the congestion knob
                    timed_out = True
                else:
                    new_requests.append((req_id, time_sent, timeout))
            self.requests_in_flight[flow_id] = new_requests
            if timed_out:
                # sim_log.info(f"Flow {flow_id} timed out {len(requests) - len(new_requests)} times, halving congestion knob {self.congestion_knobs[flow_id]}")
                # self.halve_congestion_knob(flow_id, current_time)
                pass

    def handle_ack(self, flow_id, req_id, current_time, time_sent, mark_congested=False):
        """
        Handle the ACK for the given request

        Parameters
        ----------
        flow_id : int
            The flow id
        req_id : int
            The request id
        current_time : float
            The current time
        time_sent : float
            The time the request was sent
        mark_congested : bool, optional
            Whether the ack was marked as congested or not

        Returns
        -------
        int
            The number of new requests to generate for the flow
        """

        num_skipped = 0

        found = False

        # update the estimated RTT
        sample_rtt = current_time - time_sent
        self.estimated_rtt[flow_id] = 0.875 * self.estimated_rtt[flow_id] + 0.125 * sample_rtt
        self.dev_rtt[flow_id] = 0.75 * self.dev_rtt[flow_id] + 0.25 * abs(sample_rtt - self.estimated_rtt[flow_id])
        self.C[flow_id] = self.estimated_rtt[flow_id]*4000
        # print(f"Estimated RTT for flow {flow_id} is {self.estimated_rtt[flow_id]}, dev RTT is {self.dev_rtt[flow_id]}, C is {self.C}")

        for req, time_sent, timeout in self.requests_in_flight[flow_id]:
            if req < req_id:
                num_skipped += 1
                # if we receive an ACK for a request, we can remove all the requests with lower req_id
                # because they have been surely dropped due to congestion
            elif req == req_id:
                # we found the request for which we received the ACK
                # remove it from the list
                found = True

        if found:
            # remove the tuples from the list
            self.requests_in_flight[flow_id] = self.requests_in_flight[flow_id][num_skipped + 1:]

        else:
            self.requests_in_flight[flow_id] = self.requests_in_flight[flow_id][num_skipped:]
            """
            print(f"Flow {flow_id} received an ACK for a request that was not in flight, num_skipped={num_skipped}, "
                  f"req_id={req_id}, requests_in_flight={self.requests_in_flight[flow_id]}")
            """

        if mark_congested:
            sim_log.warning(f"Flow {flow_id} marked as congested")
            self.halve_congestion_knob(flow_id, current_time)

        elif num_skipped > 0:
            sim_log.error(f"Flow {flow_id} marked as congested due to losses")
            self.halve_congestion_knob(flow_id, current_time)

        # return the number of new requests to generate. 0 with a rate-based controller
        return 0

    def get_inter_request_gap(self, flow_id):
        """
        Get the inter-request gap (us) for the given flow
        """
        return self.congestion_knobs[flow_id]

    def handle_new_request_in_flight(self, flow_id, req_id, current_time):
        """
        Handle a new request in flight for the given flow
        """
        timeout = max(self.estimated_rtt[flow_id] + 4 * self.dev_rtt[flow_id], 0.1)
        self.requests_in_flight[flow_id].append((req_id, current_time, timeout))

    def increase_all_knobs(self, current_time):
        for flow_id in self.last_update:
            self.increase_congestion_knob(flow_id, current_time)

